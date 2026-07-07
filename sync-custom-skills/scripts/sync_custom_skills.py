#!/usr/bin/env python3
"""Sync custom Codex skills and AGENTS.md with a Git repository."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
SKIP_FILE_NAMES = {".DS_Store"}
REPO_AGENTS_FILE_NAME = "RALF_AGENTS.md"
PERSONAL_AGENTS_FILE_NAME = "AGENTS.md"


@dataclasses.dataclass(frozen=True)
class Skill:
    name: str
    path: Path
    rel_path: Path
    declared_name: str | None


def run_git(repo: Path, args: list[str], check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def git_root(path: Path) -> Path:
    output = run_git(path, ["rev-parse", "--show-toplevel"])
    return Path(output).expanduser().resolve()


def is_skipped(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in SKIP_DIR_NAMES for part in rel.parts):
        return True
    return path.name in SKIP_FILE_NAMES


def discover_skill_name(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = skill_md.read_text(errors="replace").splitlines()

    if not lines or lines[0].strip() != "---":
        return None

    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if stripped.startswith("name:"):
            value = stripped.split(":", 1)[1].strip()
            return value.strip("\"'")
    return None


def discover_repo_skills(repo: Path) -> list[Skill]:
    skills: list[Skill] = []
    seen_names: dict[str, Path] = {}

    for skill_md in sorted(repo.rglob("SKILL.md")):
        if is_skipped(skill_md, repo):
            continue
        skill_dir = skill_md.parent
        declared_name = discover_skill_name(skill_dir)
        name = declared_name or skill_dir.name
        if "/" in name or "\\" in name or not name:
            raise ValueError(f"Invalid skill name {name!r} in {skill_md}")
        if name in seen_names:
            first = seen_names[name]
            raise ValueError(
                f"Duplicate skill name {name!r}: {first} and {skill_dir}"
            )
        seen_names[name] = skill_dir
        skills.append(
            Skill(
                name=name,
                path=skill_dir,
                rel_path=skill_dir.relative_to(repo),
                declared_name=declared_name,
            )
        )
    return skills


def iter_content_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if is_skipped(path, root):
            continue
        if path.is_dir():
            continue
        if path.is_file() or path.is_symlink():
            files.append(path)
    return files


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_fingerprint(root: Path) -> dict[str, tuple[str, str]]:
    fingerprint: dict[str, tuple[str, str]] = {}
    for path in iter_content_files(root):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            fingerprint[rel] = ("symlink", os.readlink(path))
        else:
            fingerprint[rel] = ("file", file_hash(path))
    return fingerprint


def latest_file_mtime(root: Path) -> tuple[float, Path]:
    latest = root.stat().st_mtime
    latest_path = root
    for path in iter_content_files(root):
        stat = path.lstat()
        if stat.st_mtime > latest:
            latest = stat.st_mtime
            latest_path = path
    return latest, latest_path


def latest_repo_commit_ts(repo: Path, rel_path: Path) -> int | None:
    output = run_git(
        repo,
        ["log", "-1", "--format=%ct", "--", rel_path.as_posix()],
    )
    if not output:
        return None
    return int(output)


def repo_path_is_dirty(repo: Path, rel_path: Path) -> bool:
    output = run_git(
        repo,
        ["status", "--porcelain", "--", rel_path.as_posix()],
    )
    return bool(output)


def fmt_ts(timestamp: float | int | None) -> str:
    if timestamp is None:
        return "no commit"
    value = dt.datetime.fromtimestamp(timestamp).astimezone()
    return value.strftime("%Y-%m-%d %H:%M:%S %Z")


def ignore_for_copy(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in SKIP_DIR_NAMES or name in SKIP_FILE_NAMES:
            ignored.add(name)
    return ignored


def replace_tree(source: Path, target: Path, dry_run: bool) -> None:
    if dry_run:
        return

    target_parent = target.parent
    target_parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.sync-tmp-", dir=target_parent)
    )
    backup_path: Path | None = None

    try:
        tmp_path.rmdir()
        shutil.copytree(source, tmp_path, symlinks=True, ignore=ignore_for_copy)
        if os.path.lexists(target):
            backup_path = Path(
                tempfile.mkdtemp(
                    prefix=f".{target.name}.sync-backup-", dir=target_parent
                )
            )
            backup_path.rmdir()
            target.rename(backup_path)
        tmp_path.rename(target)
        if backup_path is not None:
            if backup_path.is_dir() and not backup_path.is_symlink():
                shutil.rmtree(backup_path)
            else:
                backup_path.unlink()
    except Exception:
        if os.path.lexists(target):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        if backup_path is not None and os.path.lexists(backup_path):
            backup_path.rename(target)
        raise
    finally:
        if os.path.lexists(tmp_path):
            if tmp_path.is_dir() and not tmp_path.is_symlink():
                shutil.rmtree(tmp_path)
            else:
                tmp_path.unlink()


def replace_file(source: Path, target: Path, dry_run: bool) -> None:
    if dry_run:
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.sync-tmp-", dir=target.parent
    )
    os.close(file_descriptor)
    tmp_path = Path(tmp_name)

    try:
        shutil.copy2(source, tmp_path)
        tmp_path.replace(target)
    finally:
        if os.path.lexists(tmp_path):
            tmp_path.unlink()


def default_home_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser().resolve() / "skills"
    return Path.home() / ".codex" / "skills"


def sync_agents_file(
    args: argparse.Namespace, repo: Path, home_skills_dir: Path
) -> tuple[int, int, int, int]:
    repo_agents = repo / REPO_AGENTS_FILE_NAME
    if not repo_agents.exists():
        if args.verbose:
            print(
                f"[ignore] personal {PERSONAL_AGENTS_FILE_NAME}: repository "
                f"has no {REPO_AGENTS_FILE_NAME}"
            )
        return 0, 0, 0, 0

    if not repo_agents.is_file():
        raise ValueError(f"Repository path is not a file: {repo_agents}")

    personal_agents = home_skills_dir.parent / PERSONAL_AGENTS_FILE_NAME
    rel_path = Path(REPO_AGENTS_FILE_NAME)

    if not personal_agents.exists():
        print(
            f"[copy] {PERSONAL_AGENTS_FILE_NAME}: missing in Codex home, "
            f"{REPO_AGENTS_FILE_NAME} -> {PERSONAL_AGENTS_FILE_NAME}"
        )
        replace_file(repo_agents, personal_agents, args.dry_run)
        return 1, 0, 0, 1

    if not personal_agents.is_file():
        raise ValueError(f"Personal path is not a file: {personal_agents}")

    if file_hash(repo_agents) == file_hash(personal_agents):
        print(f"[same] {PERSONAL_AGENTS_FILE_NAME}: contents match")
        return 0, 1, 0, 1

    repo_ts = latest_repo_commit_ts(repo, rel_path)
    personal_ts = personal_agents.stat().st_mtime
    repo_dirty = repo_path_is_dirty(repo, rel_path)

    if args.verbose:
        print(
            f"[info] {PERSONAL_AGENTS_FILE_NAME}: repo={fmt_ts(repo_ts)}, "
            f"personal={fmt_ts(personal_ts)} ({personal_agents})"
        )

    if repo_ts is None or personal_ts > repo_ts:
        if repo_dirty and not args.allow_dirty_repo_overwrite:
            print(
                f"[skip] {PERSONAL_AGENTS_FILE_NAME}: personal file is newer, "
                f"but repository {REPO_AGENTS_FILE_NAME} has uncommitted "
                "changes. Re-run with --allow-dirty-repo-overwrite to replace "
                "the repository copy."
            )
            return 0, 0, 1, 1
        print(
            f"[copy] {PERSONAL_AGENTS_FILE_NAME}: personal file newer "
            f"({fmt_ts(personal_ts)} > {fmt_ts(repo_ts)}), "
            f"{PERSONAL_AGENTS_FILE_NAME} -> {REPO_AGENTS_FILE_NAME}"
        )
        replace_file(personal_agents, repo_agents, args.dry_run)
        return 1, 0, 0, 1

    print(
        f"[copy] {PERSONAL_AGENTS_FILE_NAME}: repository file current "
        f"({fmt_ts(repo_ts)} >= {fmt_ts(personal_ts)}), "
        f"{REPO_AGENTS_FILE_NAME} -> {PERSONAL_AGENTS_FILE_NAME}"
    )
    replace_file(repo_agents, personal_agents, args.dry_run)
    return 1, 0, 0, 1


def sync(args: argparse.Namespace) -> int:
    input_repo = Path(args.repo).expanduser().resolve()
    repo = git_root(input_repo)
    home_skills_dir = Path(args.home_skills_dir).expanduser().resolve()
    skills = discover_repo_skills(repo)

    if args.verbose:
        print(f"Repository: {repo}")
        print(f"Personal skills: {home_skills_dir}")
        print(f"Repository skills: {len(skills)}")

    copied = 0
    unchanged = 0
    skipped = 0

    for skill in skills:
        home_skill = home_skills_dir / skill.name
        if args.verbose and skill.declared_name and skill.path.name != skill.declared_name:
            print(
                f"[warn] {skill.rel_path}: folder name differs from declared "
                f"name {skill.declared_name!r}; using {skill.name!r}"
            )

        if not home_skill.exists():
            print(f"[copy] {skill.name}: missing in personal skills, repo -> home")
            replace_tree(skill.path, home_skill, args.dry_run)
            copied += 1
            continue

        repo_fingerprint = directory_fingerprint(skill.path)
        home_fingerprint = directory_fingerprint(home_skill)
        if repo_fingerprint == home_fingerprint:
            print(f"[same] {skill.name}: contents match")
            unchanged += 1
            continue

        repo_ts = latest_repo_commit_ts(repo, skill.rel_path)
        home_ts, home_latest_path = latest_file_mtime(home_skill)
        repo_dirty = repo_path_is_dirty(repo, skill.rel_path)

        if args.verbose:
            print(
                f"[info] {skill.name}: repo={fmt_ts(repo_ts)}, "
                f"home={fmt_ts(home_ts)} ({home_latest_path})"
            )

        if repo_ts is None or home_ts > repo_ts:
            if repo_dirty and not args.allow_dirty_repo_overwrite:
                print(
                    f"[skip] {skill.name}: personal skill is newer, but repo "
                    "skill has uncommitted changes. Re-run with "
                    "--allow-dirty-repo-overwrite to replace the repo copy."
                )
                skipped += 1
                continue
            print(
                f"[copy] {skill.name}: personal skill newer "
                f"({fmt_ts(home_ts)} > {fmt_ts(repo_ts)}), home -> repo"
            )
            replace_tree(home_skill, skill.path, args.dry_run)
            copied += 1
        else:
            print(
                f"[copy] {skill.name}: repository skill current "
                f"({fmt_ts(repo_ts)} >= {fmt_ts(home_ts)}), repo -> home"
            )
            replace_tree(skill.path, home_skill, args.dry_run)
            copied += 1

    agents_copied, agents_unchanged, agents_skipped, agents_considered = (
        sync_agents_file(args, repo, home_skills_dir)
    )

    print(
        f"Summary: {copied} copied, {unchanged} unchanged, "
        f"{skipped} skipped, {len(skills)} repository skills considered."
    )
    if agents_considered:
        print(
            f"AGENTS.md summary: {agents_copied} copied, "
            f"{agents_unchanged} unchanged, {agents_skipped} skipped, "
            f"{agents_considered} repository file considered."
        )
    return 2 if skipped or agents_skipped else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync custom Codex skill directories and personal AGENTS.md "
            "between a Git repository and Codex home."
        )
    )
    parser.add_argument("repo", help="Path to the Git repository containing skills")
    parser.add_argument(
        "--home-skills-dir",
        default=str(default_home_skills_dir()),
        help=(
            "Personal skills directory. Defaults to $CODEX_HOME/skills or "
            "~/.codex/skills. AGENTS.md is resolved as a sibling."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without copying files.",
    )
    parser.add_argument(
        "--allow-dirty-repo-overwrite",
        action="store_true",
        help=(
            "Allow a newer personal skill or AGENTS.md to overwrite its dirty "
            "repository counterpart."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print discovery and timestamp detail.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        return sync(parse_args(argv))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
