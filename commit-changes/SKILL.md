---
name: commit-changes
description: Inspect and understand the current Git working tree, then commit its staged and unstaged local changes with a clear title and why-focused description. Use when the user invokes commit-changes or asks to commit the current local work, including when the intent should be reconstructed from the agent conversation and repository context.
---

# Commit Changes

Commit the current local work with an intentional message.

## Workflow

1. Confirm the repository, branch, and working-tree state with `git status --short --untracked-files=all`.
2. Inspect staged changes with `git diff --cached --stat` and `git diff --cached`.
3. Inspect unstaged changes with `git diff --stat` and `git diff`.
4. Inspect relevant untracked files before staging them. Include untracked source or documentation files that belong to the local change. Do not add ignored files, secrets, credentials, build output, or unrelated artifacts.
5. Use the current agent conversation and recent repository context to understand what the local change is doing and why. Inspect nearby code or recent commits when the diff alone is insufficient.
6. If the working tree contains ambiguous or clearly unrelated changes that should not share a commit, ask the user before staging or committing.
7. Stage the local changes that belong to the requested commit, including previously unstaged files.
8. Review the staged diff and create the commit.
9. Report the commit SHA, subject, and whether any local changes remain.

## Commit Message

Write a concise imperative title followed by a description paragraph or short bullet list.

The description must:

- Explain what changed briefly.
- Emphasize why the change was needed or what behavior it enables.
- Wrap code references, file paths, command names, and identifiers in backticks for Markdown rendering.
- Omit verification details such as tests, lint, formatting, or build commands.

Use a non-interactive commit command, for example:

```bash
git commit -m "Concise imperative title" -m "Explain the change and, more importantly, why it is needed. Wrap references like \`FormatCommand\` in backticks."
```
