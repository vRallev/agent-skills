---
name: git-update
description: Run git fetch --prune to refresh remote-tracking refs and remove deleted remote refs. Use when the user asks to update, refresh, fetch, or sync a local Git repository without changing local branches or the working tree.
---

# Git Update

## Workflow

In the requested repository, run:

```bash
git fetch --prune
```

## Safety Rules

- Do not check out, create, rebase, reset, or move local branches, including `main` and `master`.
- Do not stash, reset, clean, or rewrite the user's staged or unstaged changes.
- If the fetch fails, report the failure. Do not report the refs as refreshed.
- If the sandbox blocks writes to `.git/FETCH_HEAD` or other Git metadata, retry the same command with the required escalation or approval. This permission failure does not indicate a risk to the working tree.
