---
name: ready-for-review
description: Prepare the current pull request for review by fetching the latest default branch, rebasing the local feature branch, squashing its commits into one, updating the commit message, force-pushing safely, synchronizing the PR title and description with the final commit, resolving all review conversations, and preserving the pull request's existing draft status. Use when the user invokes ready-for-review or asks to finalize a pull request into a single review-ready commit.
---

# Ready for Review

Prepare the current feature branch and its pull request for review. Invoking this skill explicitly authorizes rewriting the current PR branch history, updating the PR title and description, and resolving its review conversations.

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
   - Create one commit from the staged combined patch using the saved oldest commit message as a starting point. For a history of `A -> B -> C (HEAD)`, start from the message from `A`, then update it in the next step.
   - Do not use `git reset --hard`.
8. After squashing, use the `$update-commit-message` skill at `/Users/ralf/.codex/skills/update-commit-message/SKILL.md` to update the single commit's title and why-focused description to reflect the final combined diff. This step is required even when the branch already contained only one commit; the oldest commit message is only a starting point. Follow the skill's Markdown formatting rules, including backticks around code references, file paths, and Gradle module or task paths such as `:abc:def`. Do not insert line breaks to satisfy a maximum line length: keep each prose paragraph or list item on one line, preserve intentional Markdown structure, and let the rendering tool wrap text to the available width. Treat this ready-for-review invocation as explicit approval to amend the current PR branch commit message without changing its contents.
9. Confirm that the branch contains exactly one commit over the chosen remote base and that the working tree is clean.
10. Force-push the rewritten branch with lease protection:

```bash
git push --force-with-lease origin HEAD:<current-branch>
```

11. After the push succeeds, use the `$create-or-update-pr` skill at `/Users/ralf/.codex/skills/create-or-update-pr/SKILL.md` to update the existing PR from the finalized single commit. This step is required on every run, even when the PR already has a description or no squash was needed:
   - Set the PR title to the final commit subject (`git log -1 --format=%s`).
   - Set the PR description/body to the same description as the final commit body (`git log -1 --format=%b`). Copy it verbatim, preserving Markdown and intentional newlines; do not keep the old PR description or generate a separate summary.
   - Pass the exact text through structured GitHub connector arguments. If using `gh`, write the body to a temporary file and pass it with `gh pr edit --body-file` to preserve newlines and prevent shell expansion.
12. Fetch all pull-request review threads with a thread-aware GitHub connector tool. Resolve every unresolved inline review conversation after the push. Do not post replies unless the user asks for them. When the user asks for replies, every response to someone else's comment must start exactly with `**Ralf-AI:**`. This rule does not apply to commit messages or pull-request descriptions. Note that top-level PR comments do not have a resolvable conversation state.
13. Preserve the pull request's existing draft status. In particular, do not mark a draft pull request as ready for review.
14. Read back the pull request metadata and threads. Verify that its head SHA matches the final local commit, its title matches the commit subject, and its description matches the commit body, ignoring only trailing newlines. Confirm the draft status is unchanged. Report the final commit SHA, push status, verified PR title/description synchronization, number of resolved conversations, and unchanged draft status.

## Safety

- Rewrite only the current feature branch associated with the open pull request.
- Use `--force-with-lease`, never an unconditional force push.
- Preserve local work by requiring a clean working tree before the rebase and squash.
- Preserve the pull request's existing draft status. Never mark a draft pull request as ready for review.
- A successful push alone does not complete this workflow. If the PR title/description update or read-back verification fails, report the pushed commit and the remaining PR-text blocker; do not claim completion.
- Stop rather than guessing when the branch has no open pull request, conflicts are ambiguous, or the remote branch changed unexpectedly.
