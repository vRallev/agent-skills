#!/usr/bin/env python3
"""Audit a Gradle TOML version catalog through build-configured Maven repositories."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


QUALIFIERS = {
    "snapshot": -7,
    "dev": -6,
    "alpha": -5,
    "a": -5,
    "beta": -4,
    "b": -4,
    "milestone": -3,
    "m": -3,
    "rc": -2,
    "cr": -2,
    "preview": -2,
    "ea": -1,
    "eap": -1,
    "final": 0,
    "ga": 0,
    "release": 0,
    "sp": 1,
}

UPGRADE_SUPPRESSION_PATTERNS = (
    re.compile(r"\bnoinspection\s+GradleDependency\b", re.IGNORECASE),
    re.compile(
        r"\b(?:do\s+not|don['’]?t|never)\s+(?:upgrade|update|bump|merge|raise)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:avoid|skip|suppress)\s+(?:the\s+)?(?:upgrad(?:e|ing)|updat(?:e|ing)|bump(?:ing)?|merging)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:must|should)\s+not\s+be\s+(?:upgraded|updated|bumped|raised)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:keep|leave|remain|stay)\b.{0,100}\b(?:pinned|unchanged|as[- ]is|at\s+(?:this|the\s+current)\s+version)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:intentionally\s+)?(?:pinned|held\s+back)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:upgrade|updating|update|bump|bumping)\b.{0,160}\b(?:force|break|raise|increase|require)\b.{0,160}\b(?:consumer|downstream|compatibility|minimum|version)\b",
        re.IGNORECASE,
    ),
)

GRADLE_VERSIONS_URL = "https://services.gradle.org/versions/all"
SKIPPED_WRAPPER_DIRECTORIES = {".git", ".gradle", "build", "out"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog", type=Path, default=Path("gradle/libs.versions.toml"))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument(
        "--gradle-versions-url",
        default=GRADLE_VERSIONS_URL,
        help="Gradle version-service URL (defaults to the official all-versions endpoint)",
    )
    parser.add_argument(
        "--settings",
        action="append",
        default=[],
        type=Path,
        help="Additional settings.gradle[.kts] file to inspect (repeatable)",
    )
    parser.add_argument(
        "--repository",
        action="append",
        default=[],
        metavar="NAME=URL",
        help="Add or override a Maven repository that cannot be resolved statically (repeatable)",
    )
    parser.add_argument(
        "--credential-env",
        action="append",
        default=[],
        metavar="NAME=USERNAME_ENV:SECRET_ENV",
        help="Read Basic-auth credentials for a repository from named environment variables",
    )
    return parser.parse_args()


def read_properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def redacted_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def discover_gradle_wrapper_files(root: Path, settings_files: list[Path]) -> list[Path]:
    candidates = {
        directory / "gradle" / "wrapper" / "gradle-wrapper.properties"
        for directory in {root.resolve(), *(path.parent.resolve() for path in settings_files)}
    }
    for path in root.rglob("gradle-wrapper.properties"):
        if path.parent.name != "wrapper" or path.parent.parent.name != "gradle":
            continue
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            relative_parts = path.parts
        if not any(part in SKIPPED_WRAPPER_DIRECTORIES for part in relative_parts):
            candidates.add(path.resolve())
    return sorted(path for path in candidates if path.is_file())


def wrapper_distribution(path: Path, root: Path) -> dict:
    comments: list[str] = []
    distribution_url = ""
    distribution_comment = ""
    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            comments = []
            continue
        if line.startswith(("#", "!")):
            comments.append(re.sub(r"^[#!]+\s*", "", line))
            continue
        if "=" not in line:
            comments = []
            continue
        key, value = line.split("=", 1)
        if key.strip() == "distributionUrl":
            distribution_url = re.sub(r"\\([:=])", r"\1", value.strip())
            distribution_comment = " ".join(comments)
            break
        comments = []

    result = {
        "path": display_path(path, root),
        "current": "",
        "distributionType": "",
        "distributionUrl": redacted_url(distribution_url) if distribution_url else "",
        "upgradeSuppression": "",
        "latestStable": "",
        "latestAvailable": "",
        "stableDistributionUrl": "",
        "stableDistributionStatus": 0,
        "availableDistributionUrl": "",
        "availableDistributionStatus": 0,
        "error": "",
        "_distributionUrl": distribution_url,
    }
    if distribution_comment and any(
        pattern.search(distribution_comment) for pattern in UPGRADE_SUPPRESSION_PATTERNS
    ):
        result["upgradeSuppression"] = distribution_comment
    if not distribution_url:
        result["error"] = "distributionUrl is missing"
        return result
    parsed = urllib.parse.urlsplit(distribution_url)
    if parsed.scheme not in {"file", "http", "https"}:
        result["error"] = f"Unsupported distributionUrl scheme: {parsed.scheme or 'relative'}"
        return result
    filename = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
    match = re.fullmatch(r"gradle-(?P<version>.+)-(?P<type>bin|all)\.zip", filename)
    if not match:
        result["error"] = "distributionUrl does not contain a recognizable Gradle distribution version"
        return result
    result["current"] = match.group("version")
    result["distributionType"] = match.group("type")
    if not comparable(result["current"]):
        result["error"] = f"Gradle version is not comparable: {result['current']}"
    return result


def gradle_distribution_url(wrapper: dict, version: str) -> str:
    parsed = urllib.parse.urlsplit(wrapper["_distributionUrl"])
    directory = parsed.path.rsplit("/", 1)[0]
    filename = f"gradle-{version}-{wrapper['distributionType']}.zip"
    path = f"{directory}/{filename}" if directory else f"/{filename}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)
    )


def fetch_gradle_versions(url: str) -> tuple[list[dict], dict]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "check-dependency-upgrades/1"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
                status = getattr(response, "status", None) or 200
            if not isinstance(payload, list):
                raise ValueError("Gradle version service did not return a JSON list")
            return payload, {
                "url": redacted_url(url),
                "status": status,
                "versions": len(payload),
                "error": "",
            }
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                return [], {
                    "url": redacted_url(url),
                    "status": error.code,
                    "versions": 0,
                    "error": f"HTTP {error.code}",
                }
        except Exception as error:
            if attempt == 2:
                return [], {
                    "url": redacted_url(url),
                    "status": 0,
                    "versions": 0,
                    "error": str(error),
                }
        time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable")


def select_gradle_versions(entries: list[dict], current: str) -> tuple[str, str]:
    current_key = version_tokens(current)
    available: list[str] = []
    stable_versions: list[str] = []
    for entry in entries:
        version = str(entry.get("version", "")).strip()
        if (
            not version
            or entry.get("broken")
            or entry.get("snapshot")
            or entry.get("nightly")
            or entry.get("releaseNightly")
            or "snapshot" in version.lower()
            or "nightly" in version.lower()
            or not comparable(version)
            or version_tokens(version) <= current_key
        ):
            continue
        available.append(version)
        if stable(version):
            stable_versions.append(version)
    latest_stable = max(stable_versions, key=version_tokens) if stable_versions else ""
    latest_available = max(available, key=version_tokens) if available else ""
    return latest_stable, latest_available


def fetch_gradle_distribution(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme == "file":
        exists = Path(urllib.request.url2pathname(parsed.path)).is_file()
        return {
            "_requestUrl": url,
            "url": redacted_url(url),
            "status": 200 if exists else 404,
            "error": "" if exists else "HTTP 404",
        }

    request = urllib.request.Request(
        url, headers={"User-Agent": "check-dependency-upgrades/1"}, method="HEAD"
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = getattr(response, "status", None) or 200
            return {
                "_requestUrl": url,
                "url": redacted_url(url),
                "status": status,
                "error": "",
            }
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                return {
                    "_requestUrl": url,
                    "url": redacted_url(url),
                    "status": error.code,
                    "error": f"HTTP {error.code}",
                }
        except Exception as error:
            if attempt == 2:
                return {
                    "_requestUrl": url,
                    "url": redacted_url(url),
                    "status": 0,
                    "error": str(error),
                }
        time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable")


def literal_included_builds(settings: str) -> list[str]:
    patterns = (
        r"\bincludeBuild\s*\(\s*['\"]([^'\"]+)['\"]",
        r"\bincludeBuild\s+['\"]([^'\"]+)['\"]",
    )
    return [match.group(1) for pattern in patterns for match in re.finditer(pattern, settings)]


def discover_settings_files(root: Path, additional: list[Path]) -> list[Path]:
    queue = [root]
    result: list[Path] = []
    seen_directories: set[Path] = set()
    seen_files: set[Path] = set()

    while queue:
        directory = queue.pop(0).resolve()
        if directory in seen_directories:
            continue
        seen_directories.add(directory)
        for filename in ("settings.gradle.kts", "settings.gradle"):
            path = directory / filename
            if not path.is_file() or path in seen_files:
                continue
            seen_files.add(path)
            result.append(path)
            text = path.read_text(errors="replace")
            queue.extend(path.parent / included for included in literal_included_builds(text))

        build_src = directory / "buildSrc"
        if build_src.is_dir():
            queue.append(build_src)

    for configured in additional:
        path = configured if configured.is_absolute() else root / configured
        path = path.resolve()
        if not path.is_file():
            raise SystemExit(f"Settings file does not exist: {path}")
        if path not in seen_files:
            result.append(path)
            seen_files.add(path)
    return result


def repository_name(url: str, hint: str = "") -> str:
    if hint:
        value = re.sub(r"(?:Repository|Repo|Url|Uri)$", "", hint, flags=re.IGNORECASE)
        value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
        if value:
            return value
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "repository"
    path = parsed.path.strip("/")
    value = re.sub(r"[^A-Za-z0-9]+", "-", f"{host}-{path}").strip("-")
    return value or "repository"


def add_repository(repositories: dict[str, str], name: str, url: str, *, override: bool = False) -> str:
    clean = url.rstrip("/")
    for existing_name, existing_url in repositories.items():
        if existing_url == clean:
            if override and name != existing_name:
                repositories[name] = repositories.pop(existing_name)
                return name
            return existing_name
    if override or name not in repositories:
        repositories[name] = clean
        return name
    index = 2
    while f"{name}{index}" in repositories:
        index += 1
    unique_name = f"{name}{index}"
    repositories[unique_name] = clean
    return unique_name


def parse_repository_option(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise SystemExit(f"Invalid --repository value {value!r}; expected NAME=URL")
    name, url = value.split("=", 1)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", name):
        raise SystemExit(f"Invalid repository name {name!r}")
    if urllib.parse.urlparse(url).scheme not in {"http", "https", "file"}:
        raise SystemExit(f"Invalid repository URL {url!r}")
    return name, url


def variable_expressions(settings: str) -> dict[str, str]:
    lines = settings.splitlines()
    result: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = re.match(r"^(?P<indent>\s*)(?:val|var|def)\s+(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>.*)$", lines[index])
        if not match:
            index += 1
            continue
        indent = len(match.group("indent"))
        parts = [match.group("value")]
        index += 1
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue
            continuation_indent = len(line) - len(line.lstrip())
            if continuation_indent <= indent:
                break
            parts.append(line.strip())
            index += 1
        result[match.group("name")] = " ".join(parts)
    return result


def expression_candidates(
    expression: str,
    properties: dict[str, str],
    variables: dict[str, str],
    base_dir: Path,
) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    patterns = (
        (r"\bgradleProperty\(\s*['\"]([^'\"]+)['\"]\s*\)", lambda key: properties.get(key, "")),
        (r"\b(?:environmentVariable|System\.getenv)\(\s*['\"]([^'\"]+)['\"]\s*\)", lambda key: os.environ.get(key, "")),
        (r"\b(?:findProperty|property)\(\s*['\"]([^'\"]+)['\"]\s*\)", lambda key: properties.get(key, "")),
    )
    for pattern, lookup in patterns:
        for match in re.finditer(pattern, expression):
            value = lookup(match.group(1))
            if value:
                candidates.append((match.start(), value))

    for match in re.finditer(r"\borElse\(\s*([A-Za-z_]\w*)", expression):
        if value := variables.get(match.group(1), ""):
            candidates.append((match.start(), value))
    for match in re.finditer(r"\borElse\(\s*['\"]([^'\"]*)['\"]\s*\)", expression):
        if match.group(1):
            candidates.append((match.start(), match.group(1)))

    stripped = expression.strip()
    if match := re.fullmatch(r"['\"]([^'\"]*)['\"]", stripped):
        candidates.append((0, match.group(1)))
    if match := re.match(r"([A-Za-z_]\w*)", stripped):
        if value := variables.get(match.group(1), ""):
            candidates.append((0, value))
    if match := re.search(r"\bfile\(\s*['\"]([^'\"]+)['\"]\s*\)", expression):
        candidates.append((match.start(), (base_dir / match.group(1)).resolve().as_uri()))
    return sorted(candidates)


def resolve_expression(
    expression: str,
    properties: dict[str, str],
    variables: dict[str, str],
    base_dir: Path,
) -> str:
    candidates = expression_candidates(expression, properties, variables, base_dir)
    return candidates[0][1] if candidates else ""


def resolved_variables(settings: str, properties: dict[str, str], base_dir: Path) -> dict[str, str]:
    expressions = variable_expressions(settings)
    result: dict[str, str] = {}
    for _ in range(len(expressions) + 1):
        changed = False
        for name, expression in expressions.items():
            value = resolve_expression(expression, properties, result, base_dir)
            if value and result.get(name) != value:
                result[name] = value
                changed = True
        if not changed:
            break
    return result


def matching_brace(text: str, opening: int) -> int:
    depth = 0
    quote = ""
    escaped = False
    for index in range(opening, len(text)):
        character = text[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def expression_reference(text: str) -> tuple[str, str]:
    literal_patterns = (
        r"\bmaven\s*\(\s*(?:url\s*=\s*)?['\"](?P<value>https?://[^'\"\s]+)['\"]",
        r"\burl\s*=\s*(?:uri|URI)\(\s*['\"](?P<value>https?://[^'\"\s]+)['\"]",
        r"\burl\s*=\s*['\"](?P<value>https?://[^'\"\s]+)['\"]",
        r"\burl\s+(?:uri\(\s*)?['\"](?P<value>https?://[^'\"\s]+)['\"]",
        r"\bsetUrl\s*\(\s*['\"](?P<value>https?://[^'\"\s]+)['\"]",
    )
    for pattern in literal_patterns:
        if match := re.search(pattern, text):
            return match.group("value"), ""

    variable_patterns = (
        r"\bmaven\s*\(\s*url\s*=\s*(?P<value>[A-Za-z_]\w*)",
        r"\burl\s*=\s*(?:uri|URI)\(\s*(?P<value>[A-Za-z_]\w*)",
        r"\burl\s*=\s*(?P<value>[A-Za-z_]\w*)",
        r"\burl\s+(?P<value>[A-Za-z_]\w*)",
        r"\bsetUrl\s*\(\s*(?P<value>[A-Za-z_]\w*)",
    )
    for pattern in variable_patterns:
        if match := re.search(pattern, text):
            return "", match.group("value")
    return "", ""


def repository_declarations(
    settings: str,
    properties: dict[str, str],
    base_dir: Path,
) -> tuple[list[tuple[int, str, str, str, str]], list[str]]:
    variables = resolved_variables(settings, properties, base_dir)
    declarations: list[tuple[int, str, str, str, str]] = []
    warnings: list[str] = []
    covered_ranges: list[tuple[int, int]] = []

    for match in re.finditer(r"\bmaven\s*\{", settings):
        opening = settings.find("{", match.start())
        closing = matching_brace(settings, opening)
        if closing < 0:
            warnings.append("Found a Maven repository block with unmatched braces")
            continue
        covered_ranges.append((match.start(), closing + 1))
        block = settings[match.start() : closing + 1]
        literal, reference = expression_reference(block)
        url = literal or variables.get(reference, "")
        if not url:
            line = settings.count("\n", 0, match.start()) + 1
            warnings.append(f"Could not resolve Maven repository URL at line {line}")
            continue
        name_match = re.search(r"\bname\s*=\s*['\"]([^'\"]+)['\"]", block)
        name = repository_name(url, name_match.group(1) if name_match else reference)
        username = ""
        secret = ""
        if credentials_match := re.search(r"\bcredentials\s*\{(?P<body>.*?)\}", block, re.DOTALL):
            body = credentials_match.group("body")
            if username_match := re.search(r"\busername\s*=\s*(?P<value>[^\n]+)", body):
                username = resolve_expression(username_match.group("value"), properties, variables, base_dir)
            if secret_match := re.search(r"\b(?:password|token)\s*=\s*(?P<value>[^\n]+)", body):
                secret = resolve_expression(secret_match.group("value"), properties, variables, base_dir)
        declarations.append((match.start(), name, url, username, secret))

    call_patterns = (
        r"\bmaven\s*\(\s*(?:url\s*=\s*)?['\"](?P<literal>https?://[^'\"\s]+)['\"]\s*\)",
        r"\bmaven\s*\(\s*url\s*=\s*(?P<reference>[A-Za-z_]\w*)(?:\.[A-Za-z_]\w*\([^)]*\))*\s*\)",
    )
    for pattern in call_patterns:
        for match in re.finditer(pattern, settings):
            if any(start <= match.start() < end for start, end in covered_ranges):
                continue
            literal = match.groupdict().get("literal", "")
            reference = match.groupdict().get("reference", "")
            url = literal or variables.get(reference, "")
            if url:
                declarations.append(
                    (match.start(), repository_name(url, reference), url, "", "")
                )
            else:
                line = settings.count("\n", 0, match.start()) + 1
                warnings.append(f"Could not resolve Maven repository URL at line {line}")
    return sorted(declarations), warnings


def configured_credentials(
    repositories: dict[str, str],
    repo_properties: dict[str, str],
    user_properties: dict[str, str],
    credential_options: list[str],
    inferred_credentials: dict[str, tuple[str, str]],
) -> dict[str, tuple[str, str]]:
    configured_env: dict[str, tuple[str, str]] = {}
    for value in credential_options:
        if "=" not in value or ":" not in value.split("=", 1)[1]:
            raise SystemExit(
                f"Invalid --credential-env value {value!r}; expected NAME=USERNAME_ENV:SECRET_ENV"
            )
        name, env_names = value.split("=", 1)
        username_env, secret_env = env_names.split(":", 1)
        if name not in repositories:
            raise SystemExit(f"Credentials refer to unknown repository {name!r}")
        configured_env[name] = (username_env, secret_env)

    properties = {**repo_properties, **user_properties}
    result = dict(inferred_credentials)
    for name in repositories:
        normalized = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
        if name in configured_env:
            username_env, secret_env = configured_env[name]
            username = os.environ.get(username_env, "")
            secret = os.environ.get(secret_env, "")
            missing = [
                env_name
                for env_name, value in ((username_env, username), (secret_env, secret))
                if not value
            ]
            if missing:
                raise SystemExit(
                    f"Credential environment variable(s) not set for {name!r}: {', '.join(missing)}"
                )
        elif name not in result:
            username = os.environ.get(f"MAVEN_REPO_{normalized}_USERNAME", "")
            secret = os.environ.get(f"MAVEN_REPO_{normalized}_TOKEN", "") or os.environ.get(
                f"MAVEN_REPO_{normalized}_PASSWORD", ""
            )
            for prefix in (name, f"maven.{name}", f"repo.{name}"):
                username = username or properties.get(f"{prefix}.username", "") or properties.get(
                    f"{prefix}Username", ""
                )
                secret = secret or properties.get(f"{prefix}.token", "") or properties.get(
                    f"{prefix}.password", ""
                ) or properties.get(f"{prefix}Password", "")
        else:
            continue
        if secret:
            result[name] = (username, secret)
    return result


def discover_repositories(
    root: Path,
    additional_settings: list[Path] | None = None,
    repository_options: list[str] | None = None,
    credential_options: list[str] | None = None,
) -> tuple[dict[str, str], dict[str, tuple[str, str]], str, list[Path], list[str]]:
    repo_properties = read_properties(root / "gradle.properties")
    user_properties = read_properties(Path.home() / ".gradle" / "gradle.properties")
    settings_files = discover_settings_files(root, additional_settings or [])
    settings_documents = [(path, path.read_text(errors="replace")) for path in settings_files]

    repositories: dict[str, str] = {}
    inferred_credentials: dict[str, tuple[str, str]] = {}
    warnings: list[str] = []
    for path, text in settings_documents:
        properties = {
            **repo_properties,
            **read_properties(path.parent / "gradle.properties"),
            **user_properties,
        }
        declarations: list[tuple[int, str, str, str, str]] = []
        declarations.extend(
            (match.start(), "google", "https://dl.google.com/dl/android/maven2", "", "")
            for match in re.finditer(r"\bgoogle\s*\(\s*\)", text)
        )
        declarations.extend(
            (
                match.start(),
                "central",
                "https://repo1.maven.org/maven2",
                "",
                "",
            )
            for match in re.finditer(r"\bmavenCentral\s*\(\s*\)", text)
        )
        declarations.extend(
            (match.start(), "pluginPortal", "https://plugins.gradle.org/m2", "", "")
            for match in re.finditer(r"\bgradlePluginPortal\s*\(\s*\)", text)
        )
        declarations.extend(
            (
                match.start(),
                "mavenLocal",
                (Path.home() / ".m2" / "repository").as_uri(),
                "",
                "",
            )
            for match in re.finditer(r"\bmavenLocal\s*\(\s*\)", text)
        )
        configured, document_warnings = repository_declarations(text, properties, path.parent)
        declarations.extend(configured)
        warnings.extend(f"{path}: {warning}" for warning in document_warnings)
        for _, name, url, username, secret in sorted(declarations, key=lambda item: item[0]):
            actual_name = add_repository(repositories, name, url)
            if secret:
                inferred_credentials[actual_name] = (username, secret)

        if re.search(r"\b(?:flatDir|ivy)\s*[({]", text):
            warnings.append(
                f"{path}: Ivy or flat-directory repositories are configured but are not Maven metadata sources"
            )

    for value in repository_options or []:
        name, url = parse_repository_option(value)
        add_repository(repositories, name, url, override=True)

    central = repositories.get("central", "")
    if not central:
        central = next(
            (
                url
                for name, url in repositories.items()
                if re.sub(r"[^a-z]", "", name.lower()) == "mavencentral"
            ),
            "",
        )

    credentials = configured_credentials(
        repositories,
        repo_properties,
        user_properties,
        credential_options or [],
        inferred_credentials,
    )
    return repositories, credentials, central, settings_files, warnings


def repository_names(kind: str, coordinate: str, repositories: dict[str, str]) -> list[str]:
    del kind, coordinate
    return list(repositories)


def headers(repository: str, credentials: dict[str, tuple[str, str]]) -> dict[str, str]:
    result = {"User-Agent": "check-dependency-upgrades/1"}
    if repository in credentials:
        username, secret = credentials[repository]
        encoded = base64.b64encode(f"{username}:{secret}".encode()).decode()
        result["Authorization"] = f"Basic {encoded}"
    return result


def fetch_metadata(job, repositories, credentials):
    kind, coordinate, repository = job
    group, artifact = coordinate.split(":", 1)
    url = f"{repositories[repository]}/{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
    request = urllib.request.Request(url, headers=headers(repository, credentials))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                root = ET.fromstring(response.read())
            versioning = root.find("versioning")
            if versioning is None:
                raise ValueError("metadata has no versioning element")
            versions = [node.text.strip() for node in versioning.findall("./versions/version") if node.text]
            def value(name: str) -> str:
                return (versioning.findtext(name) or "").strip()

            return {
                "kind": kind,
                "coordinate": coordinate,
                "repository": repository,
                "versions": versions,
                "release": value("release"),
                "latest": value("latest"),
                "lastUpdated": value("lastUpdated"),
                "error": "",
            }
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {"kind": kind, "coordinate": coordinate, "repository": repository, "error": "404"}
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                return {"kind": kind, "coordinate": coordinate, "repository": repository, "error": f"HTTP {error.code}"}
        except urllib.error.URLError as error:
            if urllib.parse.urlparse(url).scheme == "file":
                return {"kind": kind, "coordinate": coordinate, "repository": repository, "error": "404"}
            if attempt == 2:
                return {"kind": kind, "coordinate": coordinate, "repository": repository, "error": str(error)}
        except Exception as error:
            if attempt == 2:
                return {"kind": kind, "coordinate": coordinate, "repository": repository, "error": str(error)}
        time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable")


def version_tokens(version: str):
    raw = re.findall(r"[0-9]+|[A-Za-z]+", version.lower())
    result = []
    for token in raw:
        result.append((2, int(token)) if token.isdigit() else (1, QUALIFIERS.get(token, 0), token))
    if not any(token.isalpha() for token in raw):
        result.append((1, 0, ""))
    return tuple(result)


def comparable(version: str) -> bool:
    return re.fullmatch(r"[0-9]+(?:[._-][0-9A-Za-z]+)*", version) is not None


def stable(version: str) -> bool:
    upper = version.upper()
    return any(word in upper for word in ("RELEASE", "FINAL", "GA")) or re.fullmatch(r"[0-9,.v-]+(?:-r)?", version) is not None


def compatibility_variant(current: str, candidate: str) -> bool:
    lower = candidate.lower()
    return candidate.startswith(current + "-") and any(word in lower for word in ("compat", "jdk"))


def excluded_candidate(version: str) -> bool:
    lower = version.lower()
    return "snapshot" in lower or "nightly" in lower


def current_version(spec, versions: dict[str, str]) -> str:
    if isinstance(spec, str):
        return spec
    value = spec.get("version")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "ref" in value:
            return versions.get(value["ref"], "")
        return value.get("strictly", value.get("require", value.get("prefer", "")))
    return ""


def version_source(spec) -> str:
    value = spec.get("version") if isinstance(spec, dict) else None
    return value["ref"] if isinstance(value, dict) and "ref" in value else "inline"


def version_comments(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    in_versions = False
    comments: list[str] = []

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if section := re.fullmatch(r"\[\s*([^]]+)\s*]\s*(?:#.*)?", line):
            in_versions = section.group(1).strip() == "versions"
            comments = []
            continue
        if not in_versions:
            continue
        if not line:
            comments = []
            continue
        if line.startswith("#"):
            comments.append(line)
            continue

        key_match = re.match(
            r"(?:['\"](?P<quoted>[^'\"]+)['\"]|(?P<bare>[A-Za-z0-9_-]+))\s*=",
            line,
        )
        if key_match:
            key = key_match.group("quoted") or key_match.group("bare")
            if comments:
                result[key] = " ".join(
                    re.sub(r"^#+\s*", "", comment).strip() for comment in comments
                )
        comments = []

    return result


def version_suppressions(path: Path) -> dict[str, str]:
    return {
        key: comment
        for key, comment in version_comments(path).items()
        if any(pattern.search(comment) for pattern in UPGRADE_SUPPRESSION_PATTERNS)
    }


def parse_catalog(path: Path):
    with path.open("rb") as source:
        catalog = tomllib.load(source)
    versions = catalog.get("versions", {})
    comments = version_comments(path)
    suppressions = version_suppressions(path)
    rows = []
    for alias, spec in catalog.get("libraries", {}).items():
        coordinate = spec["module"] if "module" in spec else f"{spec['group']}:{spec['name']}"
        source = version_source(spec)
        rows.append(
            {
                "kind": "library",
                "alias": alias,
                "coordinate": coordinate,
                "current": current_version(spec, versions),
                "versionSource": source,
                "versionComment": comments.get(source, ""),
                "upgradeSuppression": suppressions.get(source, ""),
            }
        )
    for alias, spec in catalog.get("plugins", {}).items():
        if isinstance(spec, str):
            plugin_id, version = spec.rsplit(":", 1)
        else:
            plugin_id, version = spec["id"], current_version(spec, versions)
        source = version_source(spec)
        rows.append(
            {
                "kind": "plugin",
                "alias": alias,
                "coordinate": f"{plugin_id}:{plugin_id}.gradle.plugin",
                "current": version,
                "versionSource": source,
                "versionComment": comments.get(source, ""),
                "upgradeSuppression": suppressions.get(source, ""),
            }
        )
    return rows


def fetch_pom(job, repositories, credentials):
    kind, coordinate, version, repository = job
    group, artifact = coordinate.split(":", 1)
    group_path = "/".join(urllib.parse.quote(part, safe="") for part in group.split("."))
    artifact_path = urllib.parse.quote(artifact, safe="")
    version_path = urllib.parse.quote(version, safe="")
    url = f"{repositories[repository]}/{group_path}/{artifact_path}/{version_path}/{artifact_path}-{version_path}.pom"
    request = urllib.request.Request(url, headers=headers(repository, credentials))
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read(1)
            status = getattr(response, "status", None) or 200
        return {"kind": kind, "coordinate": coordinate, "version": version, "repository": repository, "url": url, "status": status, "error": ""}
    except urllib.error.HTTPError as error:
        return {"kind": kind, "coordinate": coordinate, "version": version, "repository": repository, "url": url, "status": error.code, "error": f"HTTP {error.code}"}
    except urllib.error.URLError as error:
        status = 404 if urllib.parse.urlparse(url).scheme == "file" else 0
        return {"kind": kind, "coordinate": coordinate, "version": version, "repository": repository, "url": url, "status": status, "error": "HTTP 404" if status == 404 else str(error)}
    except Exception as error:
        return {"kind": kind, "coordinate": coordinate, "version": version, "repository": repository, "url": url, "status": 0, "error": str(error)}


def has_update(row: dict) -> bool:
    return bool(row["latestStable"] or row["latestAvailable"])


def held_update_coordinates(rows: list[dict]) -> set[str]:
    return {
        row["coordinate"]
        for row in rows
        if row["upgradeSuppression"] and has_update(row)
    }


def action_key(row: dict) -> str:
    source = row["versionSource"]
    return f"inline:{row['alias']}" if source == "inline" else source


def action_groups(rows: list[dict]) -> list[list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row["current"]:
            groups.setdefault((action_key(row), row["current"]), []).append(row)
    return [groups[key] for key in sorted(groups)]


def action_label(group: list[dict]) -> str:
    row = group[0]
    return row["alias"] if row["versionSource"] == "inline" else row["versionSource"]


def metadata_candidate_versions(row: dict, *, stable_only: bool = False) -> set[str]:
    current = row["current"]
    if not current:
        return set()
    candidates: set[str] = set()
    for item in row.get("metadata", []):
        if item.get("error"):
            continue
        values = list(item.get("versions", []))
        values.extend(item.get(field, "") for field in ("release", "latest"))
        for version in values:
            if (
                not version
                or excluded_candidate(version)
                or not comparable(version)
                or (stable_only and not stable(version))
            ):
                continue
            if comparable(current):
                if version_tokens(version) <= version_tokens(current):
                    continue
            elif version == current:
                continue
            candidates.add(version)
    return candidates


def common_candidate(group: list[dict], *, stable_only: bool = False) -> str:
    candidate_sets = [
        metadata_candidate_versions(row, stable_only=stable_only) for row in group
    ]
    if not candidate_sets or any(not candidates for candidates in candidate_sets):
        return ""
    common = set.intersection(*candidate_sets)
    return max(common, key=version_tokens) if common else ""


def pom_statuses(pom_results: list[dict]) -> dict[tuple[str, str, str], int]:
    return {
        (item["kind"], item["coordinate"], item["version"]): item["status"]
        for item in pom_results
    }


def verified_action(
    group: list[dict], version: str, statuses: dict[tuple[str, str, str], int]
) -> bool:
    return bool(version) and all(
        statuses.get((row["kind"], row["coordinate"], version)) == 200
        for row in group
    )


def action_record(
    group: list[dict], latest_stable: str, latest_available: str, target: str
) -> dict:
    return {
        "key": action_label(group),
        "current": group[0]["current"],
        "latestStable": latest_stable,
        "latestAvailable": latest_available,
        "targetVersion": target,
        "coordinates": sorted({f"{row['coordinate']}:{target}" for row in group}),
        "aliases": sorted({row["alias"] for row in group}),
    }


def classify_catalog_actions(rows: list[dict], pom_results: list[dict]) -> dict:
    held_coordinates = held_update_coordinates(rows)
    statuses = pom_statuses(pom_results)
    actions = {
        "ready": [],
        "preview": [],
        "held": [],
        "blockedByHeldCoordinates": [],
        "compatibility": [],
        "verificationFailures": [],
    }

    for group in action_groups(rows):
        latest_stable = common_candidate(group, stable_only=True)
        latest_available = common_candidate(group)
        if not latest_stable and not latest_available:
            continue

        suppressed = [row for row in group if row["upgradeSuppression"]]
        blocked_coordinates = sorted(
            {row["coordinate"] for row in group if row["coordinate"] in held_coordinates}
        )
        pinned = not comparable(group[0]["current"])
        target = latest_stable or latest_available
        record = action_record(group, latest_stable, latest_available, target)

        if suppressed:
            record["suppression"] = " ".join(
                dict.fromkeys(row["upgradeSuppression"] for row in suppressed)
            )
            record["verified"] = verified_action(group, target, statuses)
            actions["held"].append(record)
            continue

        if blocked_coordinates:
            blocked_aliases = sorted(
                {
                    row["alias"]
                    for row in group
                    if row["coordinate"] in blocked_coordinates
                }
            )
            record["blockedCoordinates"] = blocked_coordinates
            record["reason"] = (
                "Changing this catalog key would also upgrade held coordinate(s) "
                f"{', '.join(blocked_coordinates)} through alias(es) "
                f"{', '.join(blocked_aliases)}."
            )
            record["verified"] = verified_action(group, target, statuses)
            actions["blockedByHeldCoordinates"].append(record)
            continue

        if latest_stable or pinned:
            if verified_action(group, target, statuses):
                actions["ready"].append(record)
            else:
                record["reason"] = "One or more exact candidate POM requests did not return HTTP 200."
                actions["verificationFailures"].append(record)
            continue

        if compatibility_variant(group[0]["current"], latest_available):
            if verified_action(group, target, statuses):
                actions["compatibility"].append(record)
            else:
                record["reason"] = "One or more exact candidate POM requests did not return HTTP 200."
                actions["verificationFailures"].append(record)
            continue

        if verified_action(group, target, statuses):
            actions["preview"].append(record)
        else:
            record["reason"] = "One or more exact candidate POM requests did not return HTTP 200."
            actions["verificationFailures"].append(record)

    return actions


def markdown_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")


def markdown(result: dict) -> str:
    wrappers = result.get("gradleWrappers", [])
    actions = result["catalogActions"]

    lines = [
        "### Ready stable or pinned updates",
        "",
        "Only dependencies ready to upgrade are listed here; intentionally held coordinates appear only in the third table.",
        "",
        "| Catalog key or wrapper | Current | Latest stable | Latest available | Verified Maven coordinates or Gradle distribution |",
        "|---|---:|---:|---:|---|",
    ]
    for wrapper in wrappers:
        if (
            wrapper["latestStable"]
            and not wrapper["upgradeSuppression"]
            and wrapper["stableDistributionStatus"] == 200
        ):
            label = markdown_cell(wrapper["path"])
            target = markdown_cell(wrapper["stableDistributionUrl"])
            lines.append(
                f"| `Gradle wrapper: {label}` | `{wrapper['current']}` | "
                f"`{wrapper['latestStable']}` | `{wrapper['latestAvailable'] or wrapper['latestStable']}` | "
                f"<{target}> |"
            )
    for action in actions["ready"]:
        coords = "<br>".join(f"`{coordinate}`" for coordinate in action["coordinates"])
        lines.append(
            f"| `{action['key']}` | `{action['current']}` | "
            f"`{action['latestStable'] or '—'}` | `{action['latestAvailable']}` | {coords} |"
        )
    lines += [
        "",
        "### Preview-only updates",
        "",
        "| Catalog key or wrapper | Current | Latest available | Verified Maven coordinates or Gradle distribution |",
        "|---|---:|---:|---|",
    ]
    for wrapper in wrappers:
        if (
            wrapper["latestAvailable"]
            and not wrapper["latestStable"]
            and not wrapper["upgradeSuppression"]
            and wrapper["availableDistributionStatus"] == 200
        ):
            label = markdown_cell(wrapper["path"])
            target = markdown_cell(wrapper["availableDistributionUrl"])
            lines.append(
                f"| `Gradle wrapper: {label}` | `{wrapper['current']}` | "
                f"`{wrapper['latestAvailable']}` | <{target}> |"
            )
    for action in actions["preview"]:
        coords = "<br>".join(f"`{coordinate}`" for coordinate in action["coordinates"])
        lines.append(
            f"| `{action['key']}` | `{action['current']}` | "
            f"`{action['latestAvailable']}` | {coords} |"
        )

    lines += [
        "",
        "### Intentionally held-back updates—not to merge",
        "",
        "| Catalog key or wrapper | Current | Latest stable | Latest available | Suppression | Verified Maven coordinates or Gradle distribution |",
        "|---|---:|---:|---:|---|---|",
    ]
    for wrapper in wrappers:
        if wrapper["upgradeSuppression"] and (
            wrapper["latestStable"] or wrapper["latestAvailable"]
        ):
            label = markdown_cell(wrapper["path"])
            target = markdown_cell(
                wrapper["stableDistributionUrl"]
                if wrapper["latestStable"]
                else wrapper["availableDistributionUrl"]
            )
            lines.append(
                f"| `Gradle wrapper: {label}` | `{wrapper['current']}` | "
                f"`{wrapper['latestStable'] or '—'}` | `{wrapper['latestAvailable']}` | "
                f"{markdown_cell(wrapper['upgradeSuppression'])} | <{target}> |"
            )
    for action in actions["held"]:
        coords = "<br>".join(f"`{coordinate}`" for coordinate in action["coordinates"])
        reason = markdown_cell(action["suppression"])
        lines.append(
            f"| `{action['key']}` | `{action['current']}` | "
            f"`{action['latestStable'] or '—'}` | `{action['latestAvailable']}` | "
            f"{reason} | {coords} |"
        )

    lines += [
        "",
        "### Catalog keys blocked by intentionally held coordinates",
        "",
        "These keys are not ready: changing one would also change a coordinate listed in the held-back table.",
        "",
        "| Catalog key | Current | Candidate | Blocking reason |",
        "|---|---:|---:|---|",
    ]
    for action in actions["blockedByHeldCoordinates"]:
        lines.append(
            f"| `{action['key']}` | `{action['current']}` | "
            f"`{action['targetVersion']}` | {markdown_cell(action['reason'])} |"
        )

    lines += [
        "",
        "### Compatibility variants—not normal upgrades",
        "",
        "| Current | Maven release | Full Maven coordinates |",
        "|---:|---:|---|",
    ]
    for action in actions["compatibility"]:
        coords = "<br>".join(f"`{coordinate}`" for coordinate in action["coordinates"])
        lines.append(
            f"| `{action['current']}` | `{action['latestAvailable']}` | {coords} |"
        )

    lines += [
        "",
        "### Maven candidate checks requiring attention",
        "",
        "| Catalog key | Current | Candidate | Issue |",
        "|---|---:|---:|---|",
    ]
    for action in actions["verificationFailures"]:
        lines.append(
            f"| `{action['key']}` | `{action['current']}` | "
            f"`{action['targetVersion']}` | {markdown_cell(action['reason'])} |"
        )

    lines += [
        "",
        "### Gradle wrapper checks requiring attention",
        "",
        "| Wrapper | Current | Issue |",
        "|---|---:|---|",
    ]
    for wrapper in wrappers:
        issues = [wrapper["error"]] if wrapper["error"] else []
        for label, version, status in (
            ("stable", wrapper["latestStable"], wrapper["stableDistributionStatus"]),
            (
                "available",
                wrapper["latestAvailable"],
                wrapper["availableDistributionStatus"],
            ),
        ):
            if version and status != 200:
                issues.append(f"{label} candidate {version} distribution returned status {status}")
        if issues:
            label = markdown_cell(wrapper["path"])
            issue = markdown_cell("; ".join(dict.fromkeys(issues)))
            lines.append(f"| `{label}` | `{wrapper['current'] or '—'}` | {issue} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    catalog = args.catalog if args.catalog.is_absolute() else root / args.catalog
    repositories, credentials, central, settings_files, repository_warnings = discover_repositories(
        root,
        additional_settings=args.settings,
        repository_options=args.repository,
        credential_options=args.credential_env,
    )
    if not repositories:
        raise SystemExit("No Maven repositories discovered from Gradle settings")
    rows = parse_catalog(catalog)
    queries = sorted({(row["kind"], row["coordinate"]) for row in rows if row["current"]})
    jobs = [(kind, coordinate, repository) for kind, coordinate in queries for repository in repository_names(kind, coordinate, repositories)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        metadata = list(executor.map(lambda job: fetch_metadata(job, repositories, credentials), jobs))
    by_query = {}
    for item in metadata:
        by_query.setdefault((item["kind"], item["coordinate"]), []).append(item)

    for row in rows:
        results = by_query.get((row["kind"], row["coordinate"]), [])
        successes = [item for item in results if not item.get("error")]
        row["repositoriesFound"] = [item["repository"] for item in successes]
        row["metadata"] = results
        available_versions = metadata_candidate_versions(row)
        stable_versions = metadata_candidate_versions(row, stable_only=True)
        row["latestAvailable"] = (
            max(available_versions, key=version_tokens) if available_versions else ""
        )
        row["latestStable"] = (
            max(stable_versions, key=version_tokens) if stable_versions else ""
        )

    def candidate_repository(row, version):
        for item in by_query.get((row["kind"], row["coordinate"]), []):
            if not item.get("error") and (version in item.get("versions", []) or version in {item.get("release"), item.get("latest")}):
                return item["repository"]
        return ""

    pom_jobs = set()
    for row in rows:
        for field in ("latestStable", "latestAvailable"):
            version = row[field]
            repository = candidate_repository(row, version)
            if version and repository:
                pom_jobs.add((row["kind"], row["coordinate"], version, repository))
    for group in action_groups(rows):
        for version in (
            common_candidate(group, stable_only=True),
            common_candidate(group),
        ):
            if not version:
                continue
            for row in group:
                repository = candidate_repository(row, version)
                if repository:
                    pom_jobs.add(
                        (row["kind"], row["coordinate"], version, repository)
                    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        pom_results = list(executor.map(lambda job: fetch_pom(job, repositories, credentials), sorted(pom_jobs)))

    wrapper_files = discover_gradle_wrapper_files(root, settings_files)
    wrappers = [wrapper_distribution(path, root) for path in wrapper_files]
    gradle_version_service = {
        "url": redacted_url(args.gradle_versions_url),
        "status": 0,
        "versions": 0,
        "error": "",
    }
    distribution_results: list[dict] = []
    valid_wrappers = [wrapper for wrapper in wrappers if not wrapper["error"]]
    if valid_wrappers:
        gradle_versions, gradle_version_service = fetch_gradle_versions(
            args.gradle_versions_url
        )
        if gradle_version_service["error"]:
            for wrapper in valid_wrappers:
                wrapper["error"] = (
                    "Gradle version service failed: "
                    f"{gradle_version_service['error']}"
                )
        else:
            distribution_jobs: set[str] = set()
            for wrapper in valid_wrappers:
                latest_stable, latest_available = select_gradle_versions(
                    gradle_versions, wrapper["current"]
                )
                wrapper["latestStable"] = latest_stable
                wrapper["latestAvailable"] = latest_available
                for prefix, version in (
                    ("stable", latest_stable),
                    ("available", latest_available),
                ):
                    if not version:
                        continue
                    request_url = gradle_distribution_url(wrapper, version)
                    wrapper[f"_{prefix}DistributionUrl"] = request_url
                    wrapper[f"{prefix}DistributionUrl"] = redacted_url(request_url)
                    distribution_jobs.add(request_url)

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=args.workers
            ) as executor:
                distribution_results = list(
                    executor.map(
                        fetch_gradle_distribution, sorted(distribution_jobs)
                    )
                )
            distribution_by_url = {
                result["_requestUrl"]: result for result in distribution_results
            }
            for wrapper in valid_wrappers:
                for prefix in ("stable", "available"):
                    request_url = wrapper.get(f"_{prefix}DistributionUrl", "")
                    if request_url:
                        wrapper[f"{prefix}DistributionStatus"] = distribution_by_url[
                            request_url
                        ]["status"]

    unresolved = [row for row in rows if row["current"] and not row["repositoriesFound"]]
    public_wrappers = [
        {key: value for key, value in wrapper.items() if not key.startswith("_")}
        for wrapper in wrappers
    ]
    public_distribution_results = [
        {key: value for key, value in item.items() if not key.startswith("_")}
        for item in distribution_results
    ]
    catalog_actions = classify_catalog_actions(rows, pom_results)
    result = {
        "catalog": str(catalog),
        "mavenCentralUrl": central,
        "repositories": repositories,
        "authenticatedRepositories": sorted(credentials),
        "settingsFiles": [str(path) for path in settings_files],
        "repositoryWarnings": repository_warnings,
        "summary": {
            "aliases": len(rows),
            "libraryAliases": sum(row["kind"] == "library" for row in rows),
            "pluginAliases": sum(row["kind"] == "plugin" for row in rows),
            "versionedAliases": sum(bool(row["current"]) for row in rows),
            "unversionedAliases": sum(not row["current"] for row in rows),
            "metadataRequests": len(jobs),
            "metadataErrors": sum(bool(item.get("error")) and item.get("error") != "404" for item in metadata),
            "candidatePomChecks": len(pom_results),
            "candidatePomFailures": sum(item["status"] != 200 for item in pom_results),
            "catalogReadyUpdates": len(catalog_actions["ready"]),
            "catalogPreviewUpdates": len(catalog_actions["preview"]),
            "catalogHeldUpdates": len(catalog_actions["held"]),
            "catalogBlockedByHeldCoordinates": len(
                catalog_actions["blockedByHeldCoordinates"]
            ),
            "catalogVerificationFailures": len(
                catalog_actions["verificationFailures"]
            ),
            "unresolvedCoordinates": len(unresolved),
            "suppressedUpdateAliases": sum(
                bool(row["upgradeSuppression"]) and has_update(row) for row in rows
            ),
            "gradleWrappers": len(wrappers),
            "gradleVersionRequests": int(bool(valid_wrappers)),
            "gradleVersionErrors": int(bool(gradle_version_service["error"])),
            "gradleDistributionChecks": len(distribution_results),
            "gradleDistributionFailures": sum(
                item["status"] != 200 for item in distribution_results
            ),
            "gradleWrapperReadyUpdates": sum(
                bool(wrapper["latestStable"])
                and not wrapper["upgradeSuppression"]
                and wrapper["stableDistributionStatus"] == 200
                for wrapper in wrappers
            ),
            "gradleWrapperPreviewUpdates": sum(
                bool(wrapper["latestAvailable"])
                and not wrapper["latestStable"]
                and not wrapper["upgradeSuppression"]
                and wrapper["availableDistributionStatus"] == 200
                for wrapper in wrappers
            ),
            "gradleWrapperHeldUpdates": sum(
                bool(wrapper["upgradeSuppression"])
                and bool(wrapper["latestStable"] or wrapper["latestAvailable"])
                for wrapper in wrappers
            ),
            "gradleWrapperUnresolved": sum(
                bool(wrapper["error"]) for wrapper in wrappers
            ),
        },
        "unresolved": [{key: row[key] for key in ("kind", "alias", "coordinate", "current")} for row in unresolved],
        "candidatePomResults": pom_results,
        "gradleVersionService": gradle_version_service,
        "gradleDistributionResults": public_distribution_results,
        "gradleWrappers": public_wrappers,
        "catalogActions": catalog_actions,
        "rows": rows,
    }
    args.output_json.write_text(json.dumps(result, indent=2) + "\n")
    args.output_markdown.write_text(markdown(result))
    print(json.dumps(result["summary"], sort_keys=True))
    print(args.output_json)
    print(args.output_markdown)
    return 1 if any(
        result["summary"][key]
        for key in (
            "metadataErrors",
            "candidatePomFailures",
            "gradleVersionErrors",
            "gradleDistributionFailures",
            "gradleWrapperUnresolved",
        )
    ) else 0


if __name__ == "__main__":
    sys.exit(main())
