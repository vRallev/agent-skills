---
name: sync-custom-skills
description: Sync custom Codex skills and personal AGENTS.md instructions between a Git repository and Codex home. Use when the user asks to install, refresh, reconcile, or sync local custom skills from a repository such as `~/dev/agent-skills` into `$CODEX_HOME/skills` or `~/.codex/skills`, including bidirectional conflict resolution based on Git commit time versus personal file modification time.
---

# Sync Custom Skills

## Overview

Synchronize skill directories from a Git repository into the personal Codex skills directory. Also synchronize the repository's `RALF_AGENTS.md` with the personal Codex `AGENTS.md` file. Existing personal skills and a personal `AGENTS.md` that do not have repository counterparts are intentionally ignored and must not be deleted.

## Workflow

1. Require the user to provide the Git repository path that hosts the custom skills, for example `~/dev/agent-skills`.
2. Use `$CODEX_HOME/skills` as the personal skills directory and `$CODEX_HOME/AGENTS.md` as the personal instructions file when `CODEX_HOME` is set. Otherwise use `~/.codex/skills` and `~/.codex/AGENTS.md`.
3. Run a preview first when the user asks to inspect changes:

```bash
python3 <skill-dir>/scripts/sync_custom_skills.py ~/dev/agent-skills --dry-run
```

4. Run the sync:

```bash
python3 <skill-dir>/scripts/sync_custom_skills.py ~/dev/agent-skills
```

5. If the script copies a personal skill or personal `AGENTS.md` back into the repository, inspect `git status --short` and `git diff` afterward. Do not commit those repository changes unless the user asks.

## Sync Rules

- Discover repository skills by finding directories that contain `SKILL.md`.
- Install each repository skill as a direct child of the personal skills directory, using the skill name from `SKILL.md` frontmatter when present.
- If a personal skill does not exist, copy the repository skill into the personal skills directory.
- If both skill directories have identical file contents, do nothing.
- If contents differ, compare recency:
  - Repository recency is the Unix timestamp of the most recent Git commit that updated that skill directory.
  - Personal-skill recency is the newest file modification timestamp inside the personal skill directory.
  - If the personal skill is newer, copy it back into the repository.
  - Otherwise, copy the repository skill into the personal skills directory.
- Ignore personal skills that are not present in the repository.
- When the repository contains `RALF_AGENTS.md`, synchronize it with the personal Codex `AGENTS.md` using the same content comparison, recency, and direction rules as skill directories.
- Repository recency for `RALF_AGENTS.md` is the Unix timestamp of its most recent Git commit. Personal recency is the modification timestamp of `AGENTS.md`.
- If `RALF_AGENTS.md` is absent from the repository, leave the personal `AGENTS.md` untouched.

The script refuses to overwrite a repository skill or `RALF_AGENTS.md` from the personal directory when that repository path has uncommitted changes, unless `--allow-dirty-repo-overwrite` is passed.

## Script

Use `scripts/sync_custom_skills.py` for the actual synchronization. It accepts:

- `repo`: required path to the Git repository containing custom skills.
- `--home-skills-dir`: optional override for the personal skills directory. The personal `AGENTS.md` is resolved as a sibling of this directory.
- `--dry-run`: report actions without changing files.
- `--allow-dirty-repo-overwrite`: permit home-to-repo copies even when the repo skill is dirty.
- `--verbose`: print additional discovery and timestamp detail.
