---
name: commit-changes
description: Commit staged and unstaged local changes with a clear title and a description that explains why they matter. Use when the user asks to commit, including the commit step of a push, pull request, publish, or yeet workflow. For those workflows, complete this skill before publishing.
---

# Commit Changes

Commit the current local changes with a clear message.

## Workflow

1. Confirm the repository, branch, and working tree with `git status --short --untracked-files=all`.
2. Inspect staged changes with `git diff --cached --stat` and `git diff --cached`.
3. Inspect unstaged changes with `git diff --stat` and `git diff`.
4. Inspect relevant untracked files before staging them. Include source and documentation files that belong to the change. Do not add ignored files, secrets, credentials, build output, or unrelated artifacts.
5. Use the conversation and recent repository context to understand the change and its purpose. If the diff is not enough, inspect nearby code or recent commits.
6. If changes are ambiguous or clearly unrelated, ask the user before staging or committing them.
7. Stage the local changes that belong to the requested commit, including previously unstaged files.
8. Review the staged diff. Create the commit.
9. Report the commit SHA, subject, and any remaining local changes.
10. If the user also requested a push, publication, or pull request, continue that workflow after the commit report.

## Commit Message

Write a short imperative title. Follow it with a description paragraph or short bullet list.

The description must:

- Explain why the change matters. Focus on its purpose rather than its contents.
- Briefly describe the change to give context.
- Emphasize the problem solved, behavior enabled, risk reduced, or benefit to the project or user.
- Wrap code references, file paths, commands, identifiers, and Gradle module or task paths such as `:abc:def` in backticks.
- Keep each prose paragraph or list item on one line. Preserve intentional Markdown structure. Let the renderer wrap text; do not add line breaks to meet a line limit.
- Omit verification details such as tests, lint, formatting, or build commands.

If a message contains backticks, use single-quoted shell arguments or a message file to prevent command substitution. Use a non-interactive commit command:

```bash
git commit -m 'Concise imperative title' -m 'Explain why the change is important or helpful. Mention what changed only as needed for context, and wrap references like `FormatCommand` and `:abc:def` in backticks.'
```
