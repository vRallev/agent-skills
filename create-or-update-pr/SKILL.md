---
name: create-or-update-pr
description: Create a new draft pull request or update the existing open pull request for the current branch. Use when the user asks to create, open, update, refresh, or sync a PR for local branch work. Create new PRs as drafts, preserve the current review state of existing PRs, never mark a draft PR ready for review, and use commit titles/descriptions to form the PR title and body.
---

# Create Or Update PR

Create or update the pull request for the current branch. New PRs must be drafts; existing PRs must keep their current draft or ready-for-review state.

## Workflow

1. Confirm the repository, branch, upstream, and working-tree state with `git status --short --branch --untracked-files=all`.
2. Confirm the branch is pushed or push it if needed. If pushing would require choosing a remote or rewriting remote history, ask before pushing.
3. Determine the PR base branch from the existing PR, the user request, or the repository default branch.
4. Find whether an open pull request already exists for the current branch.
5. Inspect the commit range from the base branch to `HEAD`, including each commit subject and body. Use the patch only when a commit body is missing or too thin to explain the change.
6. Build the PR title and body from the commits using the rules below.
7. If an open PR exists, update its title and body without changing whether it is draft or ready for review. Do not convert an already public/ready PR back to draft, and do not mark a draft PR ready for review.
8. If no open PR exists, create a new PR as a draft. Never create a ready-for-review PR.
9. Report the PR URL, whether it was created or updated, and the base and head branches. When creating a new PR, mention that it was created as a draft.

## PR Text Rules

If the branch has exactly one commit in the PR range:

- Use the commit title as the PR title.
- Use the commit description as the PR body.
- If the commit has no useful body, generate a concise body from the patch that explains why the change is important or helpful, not just what changed.

If the branch has multiple commits in the PR range:

- Generate a concise PR title that summarizes the overall change.
- Format the PR body as one section per commit, in commit order:

```markdown
**Commit 1 title:**
Commit 1 description

**Commit 2 title:**
Commit 2 description
```

- Use each commit's subject as the section title.
- Use each commit's body as the section description.
- If a commit has no useful body, generate a concise why-focused description from that commit's patch.

## Draft Safety

- When creating a new PR, always pass the draft option, such as `--draft` with `gh pr create` or `draft: true` with the GitHub connector.
- When updating an existing PR, preserve its current review state. Do not call draft/ready conversion commands as part of updating title, body, labels, reviewers, or metadata.
- Never mark a draft PR ready for review from this skill.
- If a requested action conflicts with preserving an existing PR's review state, ask the user for a different workflow instead of changing that state.
