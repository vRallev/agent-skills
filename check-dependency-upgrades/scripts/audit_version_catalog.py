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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog", type=Path, default=Path("gradle/libs.versions.toml"))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=32)
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


def parse_catalog(path: Path):
    with path.open("rb") as source:
        catalog = tomllib.load(source)
    versions = catalog.get("versions", {})
    rows = []
    for alias, spec in catalog.get("libraries", {}).items():
        coordinate = spec["module"] if "module" in spec else f"{spec['group']}:{spec['name']}"
        rows.append({"kind": "library", "alias": alias, "coordinate": coordinate, "current": current_version(spec, versions), "versionSource": version_source(spec)})
    for alias, spec in catalog.get("plugins", {}).items():
        if isinstance(spec, str):
            plugin_id, version = spec.rsplit(":", 1)
        else:
            plugin_id, version = spec["id"], current_version(spec, versions)
        rows.append({"kind": "plugin", "alias": alias, "coordinate": f"{plugin_id}:{plugin_id}.gradle.plugin", "current": version, "versionSource": version_source(spec)})
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


def grouped(rows, predicate):
    groups = {}
    for row in rows:
        if predicate(row):
            key = (row["versionSource"], row["current"], row["latestStable"], row["latestAvailable"])
            groups.setdefault(key, []).append(row)
    return [groups[key] for key in sorted(groups)]


def markdown(result: dict) -> str:
    rows = result["rows"]
    lines = [
        "### Stable or pinned updates",
        "",
        "| Catalog key | Current | Latest stable | Latest available | Full Maven coordinates at latest stable or pinned version |",
        "|---|---:|---:|---:|---|",
    ]
    stable_groups = grouped(rows, lambda row: bool(row["latestStable"]) or (bool(row["latestAvailable"]) and not comparable(row["current"])))
    for group in stable_groups:
        row = group[0]
        coords = "<br>".join(
            sorted(
                {
                    f"`{item['coordinate']}:{item['latestStable'] or item['latestAvailable']}`"
                    for item in group
                }
            )
        )
        lines.append(f"| `{row['versionSource']}` | `{row['current']}` | `{row['latestStable'] or '—'}` | `{row['latestAvailable']}` | {coords} |")

    lines += [
        "",
        "### Preview-only updates",
        "",
        "| Catalog key | Current | Latest available | Full Maven coordinates at latest available |",
        "|---|---:|---:|---|",
    ]
    preview_groups = grouped(rows, lambda row: bool(row["latestAvailable"]) and not row["latestStable"] and comparable(row["current"]) and not compatibility_variant(row["current"], row["latestAvailable"]))
    for group in preview_groups:
        row = group[0]
        coords = "<br>".join(sorted({f"`{item['coordinate']}:{item['latestAvailable']}`" for item in group}))
        lines.append(f"| `{row['versionSource']}` | `{row['current']}` | `{row['latestAvailable']}` | {coords} |")

    lines += [
        "",
        "### Compatibility variants—not normal upgrades",
        "",
        "| Current | Maven release | Full Maven coordinates |",
        "|---:|---:|---|",
    ]
    compatibility_groups = grouped(rows, lambda row: bool(row["latestAvailable"]) and compatibility_variant(row["current"], row["latestAvailable"]))
    for group in compatibility_groups:
        row = group[0]
        coords = "<br>".join(sorted({f"`{item['coordinate']}:{item['latestAvailable']}`" for item in group}))
        lines.append(f"| `{row['current']}` | `{row['latestAvailable']}` | {coords} |")
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
        releases, stable_versions = [], []
        for item in successes:
            candidate = item.get("release") or item.get("latest")
            if candidate and candidate != row["current"] and (not comparable(row["current"]) or version_tokens(candidate) > version_tokens(row["current"])):
                releases.append(candidate)
            if comparable(row["current"]):
                current_key = version_tokens(row["current"])
                stable_versions += [version for version in item.get("versions", []) if stable(version) and version_tokens(version) > current_key]
        row["latestAvailable"] = max(releases, key=version_tokens) if releases else ""
        row["latestStable"] = max(stable_versions, key=version_tokens) if stable_versions else ""
        row["repositoriesFound"] = [item["repository"] for item in successes]
        row["metadata"] = results

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
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        pom_results = list(executor.map(lambda job: fetch_pom(job, repositories, credentials), sorted(pom_jobs)))

    unresolved = [row for row in rows if row["current"] and not row["repositoriesFound"]]
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
            "unresolvedCoordinates": len(unresolved),
        },
        "unresolved": [{key: row[key] for key in ("kind", "alias", "coordinate", "current")} for row in unresolved],
        "candidatePomResults": pom_results,
        "rows": rows,
    }
    args.output_json.write_text(json.dumps(result, indent=2) + "\n")
    args.output_markdown.write_text(markdown(result))
    print(json.dumps(result["summary"], sort_keys=True))
    print(args.output_json)
    print(args.output_markdown)
    return 1 if result["summary"]["metadataErrors"] or result["summary"]["candidatePomFailures"] else 0


if __name__ == "__main__":
    sys.exit(main())
