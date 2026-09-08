---
name: sync-custom-skills
description: Sync custom Codex skills between a Git repository and Codex home, and generate personal AGENTS.md instructions from a tracked shared fragment plus a local private fragment. Use when the user asks to install, refresh, reconcile, or sync local custom skills or personal Codex instructions.
---

# Sync Custom Skills

## Overview

Synchronize skill directories between a Git repository and the personal Codex skills directory. Generate the active personal `AGENTS.md` from the repository's shared `RALF_AGENTS.md` and the local-only `AGENTS.private.md`. Existing personal skills that do not have repository counterparts are intentionally ignored and must not be deleted.

## Workflow

1. Require the user to provide the Git repository path that hosts the custom skills, for example `~/dev/agent-skills`.
2. Use `$CODEX_HOME/skills` as the personal skills directory when `CODEX_HOME` is set. Otherwise use `~/.codex/skills`. Resolve `AGENTS.md` and `AGENTS.private.md` as siblings of that directory.
3. Run a preview first when the user asks to inspect changes:

```bash
python3 <skill-dir>/scripts/sync_custom_skills.py ~/dev/agent-skills --dry-run
```

4. Run the sync:

```bash
python3 <skill-dir>/scripts/sync_custom_skills.py ~/dev/agent-skills
```

5. If the script copies a personal skill back into the repository, inspect `git status --short` and `git diff` afterward. Do not commit those repository changes unless the user asks.

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
- When the repository contains `RALF_AGENTS.md`, treat it as the shared instruction fragment and treat the sibling of the personal skills directory named `AGENTS.private.md` as the optional local-only fragment.
- Generate the active personal `AGENTS.md` by joining the nonempty shared and private fragments with one blank line. Never copy the generated file back into the repository.
- If an existing personal `AGENTS.md` contains content beyond the shared fragment and `AGENTS.private.md` is missing, skip generation so private content cannot be lost.
- If `RALF_AGENTS.md` and `AGENTS.private.md` are identical, treat them as unsplit migration copies and leave the active `AGENTS.md` unchanged until the user splits them.
- If `RALF_AGENTS.md` is absent from the repository, leave both personal instruction files untouched.

The script refuses to overwrite a repository skill from the personal directory when that repository path has uncommitted changes, unless `--allow-dirty-repo-overwrite` is passed.

## Script

Use `scripts/sync_custom_skills.py` for the actual synchronization. It accepts:

- `repo`: required path to the Git repository containing custom skills.
- `--home-skills-dir`: optional override for the personal skills directory. The personal `AGENTS.md` and `AGENTS.private.md` are resolved as siblings of this directory.
- `--dry-run`: report actions without changing files.
- `--allow-dirty-repo-overwrite`: permit a home-to-repo skill copy even when the repository skill is dirty.
- `--verbose`: print additional discovery and timestamp detail.
