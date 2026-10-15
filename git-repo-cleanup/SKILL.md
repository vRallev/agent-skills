---
name: git-repo-cleanup
description: Delete worktrees for merged PRs when no unarchived Codex thread uses them, then delete local branches already integrated into origin/main. Use when asked to clean up a Git repository after PR merges or remove merged worktrees and branches.
---

# Git Repo Cleanup

Remove verified merged work without losing local changes or disrupting Codex chats.
An explicit cleanup or deletion request authorizes eligible removals. Do not ask again.
If the user asks only for a scan or preview, report candidates without deleting them.

## Inspect the repository

1. Resolve the repository and its common Git directory. Limit the scan to its worktrees and local branches.
2. Run `git fetch origin --prune`. If it fails, stop deletion and report the failure.
3. Use `origin/main` for the local branch scan unless the user specifies another base. If it is missing, ask which base to use.
4. Read `git worktree list --porcelain -z` and `git for-each-ref refs/heads`. Record paths, branch names, full tip SHAs, and worktree locks.
5. Query GitHub for candidate PRs, including merged, open, and closed PRs. Paginate as needed. Record repository identity, PR URL, head branch, head SHA, merge SHA, and target branch. A branch name alone is not a reliable match.
6. For each candidate worktree, run `git status --porcelain=v1 --untracked-files=all`. Inspect ignored file paths too. Keep dirty worktrees and worktrees with valuable or uncertain ignored files. Known disposable build output does not block removal.

Keep the primary and current checkouts, locked or permanent worktrees, and local `main`, `master`, and default branches. Keep candidates with an open PR or an operation in progress.

## Check Codex associations

Use current Codex thread and artifact tools first. Check paths, worktree attachments, repository identity, and branch associations. An idle or completed thread still blocks deletion if it is unarchived. Include subagent threads.

A recent-thread list is not a complete inventory. Absence from that list or this chat's `list_artifacts` result does not prove that a worktree is unused.

If the tools cannot establish complete coverage, inspect local Codex state read-only:

- Locate the active state database under `${CODEX_HOME:-$HOME/.codex}`. Inspect its schema; do not assume a database version.
- Open SQLite with `mode=ro`. Inspect `threads` and `thread_attachments`, where present, plus workspace mappings needed to resolve paths.
- Match canonical worktree paths and descendant working directories. Match branch names only within the same repository and host. Inspect attachment paths even when a thread's current directory is elsewhere.
- Treat `archived = 0` associations as blockers. Do not silently exclude internal thread sources.

If association data is unavailable, incomplete, or ambiguous, retain the affected candidate. Never edit Codex state or archive chats to make cleanup possible.

## Prove integration

For a worktree, require a verified merged PR. Prove that the current tip is integrated into the refreshed PR target branch. Check detached HEADs as well as named branches. A merged PR does not cover later local commits.

For other local branches, prove integration into `origin/main` or the user-selected base. These branches do not need a PR.

Use one of these proofs against the recorded tip SHA and base SHA:

- **Ancestry:** `git merge-base --is-ancestor <tip> <base>` succeeds.
- **Rebase or cherry-pick:** `git cherry <base> <tip>` reports only equivalent patches, and `git rev-list --merges <base>..<tip>` is empty. Inspect any unexplained or empty result.
- **Squash merge:** Verify that the PR merge commit is reachable from the base. Run `git merge-tree --write-tree <merge-first-parent> <tip>`. Require exit status zero and a result equal to the PR merge commit's tree. This checks the current tip, including changes after the PR head.

`git cherry` can report unique patches after a squash merge. A deleted remote branch, a `[gone]` upstream, or a merged PR label alone does not prove integration. Retain candidates with conflicts, unmatched commits, or uncertain evidence.

See the [Git merge-tree documentation](https://git-scm.com/docs/git-merge-tree) for output and exit status details.

## Remove and verify

1. Summarize eligible paths and branches with their PR and integration evidence. Continue with authorized cleanup.
2. Immediately before each removal, repeat the eligibility checks against the recorded SHAs. If anything changed, reassess that candidate.
3. Remove eligible worktrees before their branches. For supported managed worktrees, use Codex `archive_worktree` with the identity returned by `list_artifacts`. This preserves a recoverable snapshot. Otherwise, use `git worktree remove <path>` from a retained checkout. Do not bypass a Codex tool rejection with Git.
4. Delete an eligible branch only after confirming it is not checked out anywhere and has no unarchived Codex association. Start with `git branch -d -- <branch>`. If Git rejects deletion despite proven integration, the cleanup request permits `git branch -D -- <branch>` after rechecking the recorded SHA and proof.
5. Re-list worktrees and local branches. Verify each removal. Report removed items, retained items with reasons, and failures. Do not claim completion for a failed deletion.

Do not use `rm -rf`, force-remove worktrees, reset changes, or delete remote branches. If a candidate fails a check, retain it and continue with independent candidates.

Codex lifecycle behavior is described in the [worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees).
