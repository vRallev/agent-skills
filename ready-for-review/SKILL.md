---
name: ready-for-review
description: Prepare the current pull request for review by fetching the latest default branch, rebasing the local feature branch, squashing its commits into one while preserving the oldest feature commit's message unless it is stale or inaccurate, force-pushing safely, resolving all review conversations, and preserving the pull request's existing draft status. Use when the user invokes ready-for-review or asks to finalize a pull request into a single review-ready commit.
---

# Ready for Review

Prepare the current feature branch and its pull request for review. Invoking this skill explicitly authorizes rewriting the current PR branch history and resolving its review conversations.

## Workflow

1. Confirm the current repository, branch, upstream, and working-tree state. Require a clean working tree before rewriting history. Do not run this workflow on `main`, `master`, or a detached `HEAD`.
2. Resolve the open pull request for the current local branch and record whether it is a draft. Prefer GitHub connector tools; use `gh` only when connector coverage is insufficient.
3. Run `git fetch origin`.
4. Choose the rebase target:
   - Use `origin/main` when `refs/remotes/origin/main` exists.
   - Otherwise use `origin/master` when `refs/remotes/origin/master` exists.
   - Stop and report the blocker when neither exists.
5. Rebase the current feature branch onto the chosen remote base. If conflicts occur, resolve them carefully when the intended resolution is clear. Otherwise stop and ask the user.
6. Find the merge base between the rebased branch and the chosen remote base. Count commits in `<base>..HEAD`.
7. Squash all feature-branch commits into one when more than one exists:
   - Identify the least recent (oldest) commit in `<base>..HEAD` and save its complete commit message, including its subject and body.
   - Run `git reset --soft <base>`.
   - Create one commit from the staged combined patch using the saved oldest commit message unchanged. For a history of `A -> B -> C (HEAD)`, preserve the message from `A`.
   - Do not use `git reset --hard`.
8. Inspect the single combined commit and compare its preserved message with the resulting change. Update the message only when it is out of date or does not describe the content accurately. In either case, use the `$update-commit-message` skill at `/Users/ralf/.codex/skills/update-commit-message/SKILL.md`; treat this ready-for-review invocation as explicit approval to amend the current PR branch commit. Otherwise preserve the oldest commit message exactly, even if different wording could be clearer or more detailed.
9. Confirm that the branch contains exactly one commit over the chosen remote base and that the working tree is clean.
10. Force-push the rewritten branch with lease protection:

```bash
git push --force-with-lease origin HEAD:<current-branch>
```

11. Fetch all pull-request review threads with a thread-aware GitHub connector tool. Resolve every unresolved inline review conversation after the push. Do not post replies unless the user asks for them. Note that top-level PR comments do not have a resolvable conversation state.
12. Preserve the pull request's existing draft status. In particular, do not mark a draft pull request as ready for review.
13. Read back the pull request threads and report the final commit SHA, push status, number of resolved conversations, and unchanged draft status.

## Safety

- Rewrite only the current feature branch associated with the open pull request.
- Use `--force-with-lease`, never an unconditional force push.
- Preserve local work by requiring a clean working tree before the rebase and squash.
- Preserve the pull request's existing draft status. Never mark a draft pull request as ready for review.
- Stop rather than guessing when the branch has no open pull request, conflicts are ambiguous, or the remote branch changed unexpectedly.
