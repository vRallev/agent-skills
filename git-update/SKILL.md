---
name: git-update
description: Refresh a Git repository's remote-tracking refs and prune deleted remote refs by running git fetch --prune. Use when the user asks to update, refresh, fetch, or synchronize a local Git repository without modifying local branches or the working tree.
---

# Git Update

## Workflow

From the repository the user wants to update, run:

```bash
git fetch --prune
```

## Safety Rules

- Do not check out, create, rebase, reset, or move local branches, including `main` and `master`.
- Do not stash, reset, clean, or otherwise rewrite the caller's staged or unstaged changes.
- If the fetch fails, report the failure instead of treating the remote-tracking refs as refreshed.
- In Codex sandboxed environments, `git fetch --prune` may fail when writing `.git/FETCH_HEAD` or other Git metadata. Treat that as an expected sandbox permission issue, not as working-tree risk; rerun the same command with the appropriate escalation/approval.
