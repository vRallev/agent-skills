---
name: git-local-branches-summary
description: Refresh a Git repository and conservatively identify local branches whose work is already present in the remote default branch, including direct ancestors and patch-equivalent rebases or cherry-picks. Use when cleaning up local branches after pull requests merge, checking branches with deleted or gone upstreams, or auditing which local branches can be removed without losing unique commits; always flag attached worktrees and never delete branches unless explicitly asked.
---

# Git Local Branches Summary

## Workflow

1. Resolve the repository from the user's path or the current directory.
2. Refresh remote refs and local `main` or `master` with the installed `git-update` skill:

   ```bash
   bash "${CODEX_HOME:-$HOME/.codex}/skills/git-update/scripts/git_update.sh" <repo>
   ```

   Preserve all staged and unstaged work. If sandboxing blocks Git metadata, rerun with approval. If temporary worktree creation fails because `git-lfs` is unavailable, rerun the same script with LFS filters disabled only for that process:

   ```bash
   GIT_CONFIG_COUNT=3 \
   GIT_CONFIG_KEY_0=filter.lfs.process GIT_CONFIG_VALUE_0= \
   GIT_CONFIG_KEY_1=filter.lfs.smudge GIT_CONFIG_VALUE_1=cat \
   GIT_CONFIG_KEY_2=filter.lfs.required GIT_CONFIG_VALUE_2=false \
   bash "${CODEX_HOME:-$HOME/.codex}/skills/git-update/scripts/git_update.sh" <repo>
   ```

3. Run the bundled read-only audit:

   ```bash
   bash scripts/summarize_local_branches.sh <repo> [base-ref]
   ```

   Omit `base-ref` to prefer `origin/HEAD`, then `origin/main`, then `origin/master`.
4. Report `direct-ancestor` and `patch-equivalent` rows as content-safe cleanup candidates. Explain the evidence for each.
5. Highlight every attached worktree, its path, and whether it is clean. A checked-out branch cannot be deleted until its worktree is removed or detached; a dirty worktree requires explicit user review.
6. Report that `retain` and `manual-review` rows are not safe automatic cleanup candidates. Include their unique-patch or merge-commit counts.

## Classification Rules

- `direct-ancestor`: the local tip is an ancestor of the refreshed base ref.
- `patch-equivalent`: the branch is not an ancestor, has no unique `git cherry` patches, and contains no merge commits outside the base. This covers ordinary rebases and cherry-picks with unchanged patches.
- `retain`: at least one patch is not represented in the base.
- `manual-review`: merge commits make patch-ID analysis insufficient.

Treat squash merges whose patch IDs changed as unproven, not safe. Never infer safety merely from a missing remote or `[gone]` upstream.

## Safety

- Do not delete branches, remove worktrees, detach worktrees, or use `git branch -D` unless the user explicitly requests it.
- Exclude local `main` and `master` from cleanup candidates.
- Distinguish content safety from deletion mechanics: Git may reject `git branch -d` for a patch-equivalent branch even though its patch is present upstream.
- If refresh fails, report the exact failure and label any subsequent audit as based on stale refs.
