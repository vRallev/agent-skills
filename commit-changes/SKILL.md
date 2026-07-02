---
name: commit-changes
description: Inspect and understand the current Git working tree, then commit its staged and unstaged local changes with a clear title and why-focused description. Use whenever the user asks to commit changes, commit this work, create a git commit, or perform the commit portion of a larger push, pull-request, publish, or yeet workflow. For requests that also ask to push, publish, or create a PR, use this skill first for the commit, then continue with the publishing workflow after the commit exists.
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
10. If the user's request also includes pushing, publishing, or opening a pull request, stop this skill after the commit report and then continue with the appropriate publishing workflow.

## Commit Message

Write a concise imperative title followed by a description paragraph or short bullet list.

The description must:

- Explain why the change is important or helpful; prioritize the "why" over the "what".
- Mention what changed only briefly, as context for understanding the reason.
- Emphasize the problem solved, behavior enabled, risk reduced, or project/user benefit.
- Wrap code references, file paths, command names, and identifiers in backticks for Markdown rendering.
- Omit verification details such as tests, lint, formatting, or build commands.

Use a non-interactive commit command, for example:

```bash
git commit -m "Concise imperative title" -m "Explain why the change is important or helpful. Mention what changed only as needed for context, and wrap references like \`FormatCommand\` in backticks."
```
