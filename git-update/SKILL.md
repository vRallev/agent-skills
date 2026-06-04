---
name: git-update
description: Safely update a Git repository by running fetch prune and bringing local main/master branches up to date with origin/main and origin/master without checking out those branches. Use when the user asks to update, refresh, fetch and rebase, or synchronize a local repository while preserving staged and unstaged work.
---

# Git Update

## Workflow

Use `scripts/git_update.sh` from the repository the user wants to update:

```bash
bash /Users/ralf/.codex/skills/git-update/scripts/git_update.sh
```

The script:

1. Runs `git fetch --prune`.
2. If `origin/master` exists, updates local `master`.
3. If `origin/main` exists, updates local `main`.
4. Creates a missing local branch at the matching remote branch without checking it out.
5. Rebases existing local branch commits onto the matching remote branch in a temporary detached worktree, then updates the local branch ref.

## Safety Rules

- Do not check out `main` or `master` in the caller's working tree.
- Do not stash, reset, clean, or otherwise rewrite the caller's staged or unstaged changes.
- If a rebase conflict or other error occurs, leave the caller's working tree untouched and do not move the local branch ref.
- If local commits exist that are not on the remote branch, keep them by rebasing them onto the remote branch instead of force-aligning the local branch to origin.
- In Codex sandboxed environments, `git fetch --prune` may fail when writing `.git/FETCH_HEAD` or other Git metadata. Treat that as an expected sandbox permission issue, not as working-tree risk; rerun the same script with the appropriate escalation/approval.

## Notes

- The usual result is that local `main` or `master` points at the same commit as `origin/main` or `origin/master`.
- When local commits are present, the local branch may intentionally remain ahead of origin after the rebase.
- If neither `origin/main` nor `origin/master` exists, report that there is nothing to update after the fetch.
