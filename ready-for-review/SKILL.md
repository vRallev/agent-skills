---
name: ready-for-review
description: Prepare the current pull request as one commit for review. Fetch the latest default branch, rebase, squash, update the commit message, and force-push safely. Match the PR title and description to the final commit. Resolve all review conversations and preserve the PR's draft status. Use when the user invokes ready-for-review or asks to finalize a pull request into a single review-ready commit.
---

# Ready for Review

Prepare the current feature branch and its PR for review. Invoking this skill explicitly authorizes you to rewrite the current PR branch history, update its title and description, and resolve its review conversations.

## Workflow

1. Confirm the current repository, branch, upstream, and working-tree state. Before rewriting history, require a clean working tree. Do not run this workflow on `main`, `master`, or a detached `HEAD`.
2. Find the open PR for the current local branch. Record whether it is a draft. Read its title and body to retain applicable author-provided intent and invariants for the commit rewrite. Prefer GitHub connector tools. If connector coverage is insufficient, use `gh`.
3. Run `git fetch origin`.
4. Choose the rebase target:
   - If `refs/remotes/origin/main` exists, use `origin/main`.
   - Otherwise, if `refs/remotes/origin/master` exists, use `origin/master`.
   - If neither exists, stop. Report the blocker.
5. Rebase the current feature branch onto the chosen remote base. If conflicts have a clear intended resolution, resolve them carefully. If the resolution is unclear, stop. Ask the user.
6. Find the merge base between the rebased branch and the chosen remote base. Count commits in `<base>..HEAD`.
7. If more than one feature-branch commit exists, squash them into one:
   - Identify the oldest commit in `<base>..HEAD`.
   - Save its complete message, including its subject and body.
   - Run `git reset --soft <base>`.
   - Create one commit from the staged combined patch. Use the saved oldest commit message as a starting point. For `A -> B -> C (HEAD)`, start with the message from `A`. Update it in the next step.
   - Do not use `git reset --hard`.
8. Use `$update-commit-message` to update the single commit's title and description for the final combined diff. Explain the author's intent and expected invariants. Preserve applicable author-provided intent and invariants from the existing PR and conversation. Apply this step even if the branch already had only one commit. This invocation explicitly approves amending the current PR branch's commit message. Keep the committed contents unchanged.
   - Follow the skill's Markdown rules. Put backticks around code references, file paths, and Gradle module or task paths such as `:abc:def`.
   - Keep each prose paragraph or list item on one line. Preserve intentional Markdown structure. Let the renderer wrap text; do not add line breaks to limit line length.
9. Before pushing, confirm both conditions:
   - The branch contains exactly one commit over the chosen remote base.
   - The working tree is clean.
10. Force-push the rewritten branch with lease protection:

```bash
git push --force-with-lease origin HEAD:<current-branch>
```

11. After the push succeeds, use `$create-or-update-pr` to update the existing PR from the final single commit. Apply this step on every run, even if the PR has a description or needed no squash:
   - Set the PR title to the final commit subject (`git log -1 --format=%s`).
   - Set the PR description to the final commit body (`git log -1 --format=%b`). Copy it verbatim. Preserve Markdown and intentional newlines. Do not keep the old description or write a separate summary.
   - Pass the exact text through structured GitHub connector arguments. If using `gh`, write the body to a temporary file. Pass it with `gh pr edit --body-file` to preserve newlines and prevent shell expansion.
12. Fetch all PR review threads with a thread-aware GitHub connector tool. After the push, resolve every unresolved inline review conversation.
   - Top-level PR comments have no resolvable conversation state.
   - Post comments or replies only if the user asks. For every requested comment or review write, use `$github-comments`.
13. Read back the PR metadata and threads. Verify all of these:
   - The PR head SHA matches the final local commit.
   - The PR title matches the commit subject.
   - The PR description matches the commit body, ignoring only trailing newlines.
   - The PR's draft status is unchanged.
14. Report the final commit SHA, push status, verified match between PR text and commit text, number of resolved conversations, and unchanged draft status. If you drafted text without confirmed author review, identify that review as remaining work.

## Safety

- Rewrite only the current feature branch associated with the open PR.
- Use `--force-with-lease`, never an unconditional force push.
- Before the rebase and squash, require a clean working tree to preserve local work.
- Preserve the PR's draft status. Never mark a draft PR ready for review.
- A successful push alone does not complete this workflow. If the PR text update or read-back verification fails, report the pushed commit and remaining PR-text blocker. Do not claim completion.
- If the branch has no open PR, conflicts are ambiguous, or the remote branch changed unexpectedly, stop. Do not guess.
