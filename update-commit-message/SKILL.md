---
name: update-commit-message
description: Rewrite the current Git HEAD commit message with a clear title and a description that explains why the change matters. Use when the user invokes update-commit-message or asks to improve, rewrite, or amend the latest commit message without changing the commit's contents.
---

# Update Commit Message

Rewrite the message for the current `HEAD` commit without changing its contents.

## Workflow

1. Confirm the repository, branch, and working tree with `git status --short --branch --untracked-files=all`.
2. Inspect the current commit with `git show --stat --summary HEAD`, `git show --format=fuller --no-patch HEAD`, and `git show --format= HEAD`.
3. Use the patch, conversation, and recent repository context to understand the change and its purpose. If the commit is not enough, inspect nearby code or preceding commits.
4. Check whether an upstream or remote-tracking branch contains `HEAD`. If an amendment would rewrite published history, get explicit user approval before changing the commit.
5. Amend only the commit message. Do not stage local changes or alter the committed contents.
6. Confirm the new commit SHA. Report any remaining local changes.

## Commit Message

Write a short imperative title. Follow it with a description paragraph or short bullet list.

The description must:

- Explain why the change matters. Focus on its purpose rather than its contents.
- Briefly describe the change to give context.
- Emphasize the problem solved, behavior enabled, risk reduced, or benefit to the project or user.
- Wrap code references, file paths, commands, identifiers, and Gradle module or task paths such as `:abc:def` in backticks.
- Keep each prose paragraph or list item on one line. Preserve intentional Markdown structure. Let the renderer wrap text; do not add line breaks to meet a line limit.
- Omit verification details such as tests, lint, formatting, or build commands.

If a message contains backticks, use single-quoted shell arguments or a message file to prevent command substitution. Use a non-interactive amend command:

```bash
git commit --amend -m 'Concise imperative title' -m 'Explain why the change is important or helpful. Mention what changed only as needed for context, and wrap references like `FormatCommand` and `:abc:def` in backticks.'
```
