---
name: git-local-branches-summary
description: Refresh a Git repository and conservatively identify local branches whose work is already in the remote default branch. Check direct ancestors and patch-equivalent rebases or cherry-picks. Use to clean up local branches after pull requests merge, check branches with deleted or gone upstreams, or find branches that can be removed without losing unique commits. Always flag attached worktrees. Delete branches only when the user explicitly asks.
---

# Git Local Branches Summary

## Workflow

1. Resolve the repository from the user's path or the current directory.
2. Refresh remote refs with the installed `git-update` skill:

   ```bash
   git -C <repo> fetch --prune
   ```

   Preserve all staged and unstaged work.
   If sandboxing blocks Git metadata, rerun the same command with approval.
   If the refresh fails, stop the audit. Report the exact failure.

3. Run the bundled read-only audit:

   ```bash
   bash scripts/summarize_local_branches.sh <repo> [base-ref]
   ```

   If you omit `base-ref`, prefer `origin/HEAD`, then `origin/main`, then `origin/master`.
4. Report `direct-ancestor` and `patch-equivalent` rows as cleanup candidates with no unique content. Explain the evidence for each row.
5. Highlight each attached worktree, its path, and whether it is clean. A checked-out branch cannot be deleted until its worktree is removed or detached. If a worktree is dirty, require explicit user review.
6. Report `retain` and `manual-review` rows as unsafe for automatic cleanup. Include their unique-patch or merge-commit counts.

## Classification Rules

- `direct-ancestor`: The local tip is an ancestor of the refreshed base ref.
- `patch-equivalent`: The branch is not an ancestor. It has no unique `git cherry` patches or merge commits outside the base. This includes ordinary rebases and cherry-picks with unchanged patches.
- `retain`: At least one patch is absent from the base.
- `manual-review`: Merge commits prevent a reliable decision from patch IDs alone.

If a squash merge changed patch IDs, treat its content safety as unproven. A missing remote or `[gone]` upstream does not prove safety.

## Safety

- Delete branches only when the user explicitly asks.
- Remove or detach worktrees only when the user explicitly asks.
- Use `git branch -D` only when the user explicitly asks.
- Exclude local `main` and `master` from cleanup candidates.
- Distinguish content safety from deletion mechanics. Git can reject `git branch -d` for a patch-equivalent branch even when its patch is present upstream.
- If the refresh fails, report the exact failure. Label any subsequent audit as based on stale refs.
