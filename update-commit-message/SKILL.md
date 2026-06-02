---
name: update-commit-message
description: Inspect the current Git HEAD commit and rewrite its commit message with a clear title and why-focused description. Use when the user invokes update-commit-message or asks to improve, rewrite, or amend the most recent commit message without changing the commit contents.
---

# Update Commit Message

Rewrite the message for the current `HEAD` commit without changing its contents.

## Workflow

1. Confirm the repository, branch, and working-tree state with `git status --short --branch --untracked-files=all`.
2. Inspect the current commit with `git show --stat --summary HEAD`, `git show --format=fuller --no-patch HEAD`, and `git show --format= HEAD`.
3. Use the patch, current agent conversation, and recent repository context to understand what changed and why. Inspect nearby code or preceding commits when the commit alone is insufficient.
4. Check whether `HEAD` is already contained in an upstream or remote-tracking branch. If amending would rewrite published history, ask the user for explicit approval before changing the commit.
5. Amend only the commit message. Do not stage local changes or alter the committed contents.
6. Confirm the new commit SHA and report whether local changes remain.

## Commit Message

Write a concise imperative title followed by a description paragraph or short bullet list.

The description must:

- Explain what changed briefly.
- Emphasize why the change was needed or what behavior it enables.
- Wrap code references, file paths, command names, and identifiers in backticks for Markdown rendering.
- Omit verification details such as tests, lint, formatting, or build commands.

Use a non-interactive amend command, for example:

```bash
git commit --amend -m "Concise imperative title" -m "Explain the change and, more importantly, why it is needed. Wrap references like \`FormatCommand\` in backticks."
```
