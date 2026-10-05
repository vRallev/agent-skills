---
name: sync-custom-skills
description: Sync custom skills between a Git repository and Codex home. Generate personal AGENTS.md from shared and private instructions. Use when the user asks to install, refresh, reconcile, or sync local custom skills or personal Codex instructions.
---

# Sync Custom Skills

## Overview

Sync skill directories between a Git repository and the personal Codex skills directory. Generate personal `AGENTS.md` from the repository's shared `RALF_AGENTS.md` and the local-only `AGENTS.private.md`. Keep personal skills that have no repository counterpart.

## Workflow

1. Require the user to provide the custom skills Git repository path, for example `~/dev/agent-skills`.
2. If `CODEX_HOME` is set, use `$CODEX_HOME/skills` as the personal skills directory. Otherwise, use `~/.codex/skills`. Resolve `AGENTS.md` and `AGENTS.private.md` as siblings of that directory.
3. If the user asks to inspect changes, run a preview first:

```bash
python3 <skill-dir>/scripts/sync_custom_skills.py ~/dev/agent-skills --dry-run
```

4. Run the sync:

```bash
python3 <skill-dir>/scripts/sync_custom_skills.py ~/dev/agent-skills
```

5. If the script copies a personal skill into the repository, inspect `git status --short` and `git diff` afterward. Commit those changes only if the user asks.

## Sync Rules

- Find repository skills in directories that contain `SKILL.md`.
- Install each skill directly under the personal skills directory. If `SKILL.md` frontmatter has a name, use it.
- If the personal skill does not exist, copy the repository skill to the personal skills directory.
- If both directories have identical contents, leave them unchanged.
- If contents differ, compare timestamps:
  - For the repository skill, use the Unix timestamp of the most recent Git commit that updated its directory.
  - For the personal skill, use the newest file modification timestamp in its directory.
  - If the personal skill is newer, copy it back into the repository.
  - Otherwise, copy the repository skill into the personal skills directory.
- Ignore personal skills that have no repository counterpart.
- If the repository contains `RALF_AGENTS.md`, use it as the shared instructions. Use the sibling `AGENTS.private.md` as the optional local-only instructions.
- Join the nonempty shared and private instructions with one blank line to generate personal `AGENTS.md`. Never copy the generated file into the repository.
- If personal `AGENTS.md` has content beyond the shared instructions and `AGENTS.private.md` is missing, skip generation to preserve private content.
- If `RALF_AGENTS.md` and `AGENTS.private.md` are identical, leave personal `AGENTS.md` unchanged until the user splits these migration copies.
- If the repository has no `RALF_AGENTS.md`, leave both personal instruction files unchanged.

If a repository skill has uncommitted changes, the script refuses to overwrite it from the personal directory unless `--allow-dirty-repo-overwrite` is set.

## Script

Use `scripts/sync_custom_skills.py` to sync. It accepts:

- `repo`: required path to the custom skills repository.
- `--home-skills-dir`: optional override for the personal skills directory. Resolve personal `AGENTS.md` and `AGENTS.private.md` as siblings of this directory.
- `--dry-run`: report actions without changing files.
- `--allow-dirty-repo-overwrite`: allow a personal skill to overwrite a repository skill that has uncommitted changes.
- `--verbose`: print discovery and timestamp details.
