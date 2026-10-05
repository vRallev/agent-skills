---
name: create-or-update-pr
description: Create a draft pull request or update the open pull request for the current branch. Use when the user asks to create, open, update, refresh, or sync a PR for local branch work. Preserve the review state of existing PRs. Never mark a draft PR ready for review. Use commit titles and descriptions for the PR text.
---

# Create or Update PR

Create or update the PR for the current branch. Create new PRs as drafts. Preserve each existing PR's draft or ready-for-review state.

## Workflow

1. Confirm the repository, branch, upstream, and working-tree state with `git status --short --branch --untracked-files=all`.
2. Confirm whether the branch is pushed. If pushing requires a remote choice or a rewrite of remote history, ask before pushing. Otherwise, push the branch if needed.
3. Determine the PR base branch from the existing PR, the user request, or the repository default branch.
4. Check for an open PR for the current branch.
5. Inspect the commit range from the base branch to `HEAD`, including each commit subject and body. Only if a commit body is missing or too brief to explain the change, inspect its patch.
6. Build the PR title and body from the commits using the rules below.
7. If an open PR exists, update its title and body. Preserve its draft or ready-for-review state. Do not convert a ready PR to draft. Do not mark a draft PR ready for review.
8. If no open PR exists, create a new PR as a draft. Never create a ready-for-review PR.
9. Report the PR URL, whether you created or updated it, and the base and head branches. For a new PR, state that you created it as a draft.

## PR Text Rules

Format the PR body as Markdown. Put backticks around code references, file paths, command names, identifiers, and Gradle module or task paths such as `:abc:def`. Apply this rule to text from existing commit descriptions too. Do not amend the source commits. To prevent command substitution, pass bodies that contain backticks as single-quoted shell arguments, through a body file, or through a GitHub connector.

Do not insert line breaks to limit line length. Keep each prose paragraph or list item on one line. Let GitHub or another rendering tool wrap text. For text from existing commit descriptions, join line breaks inserted only to limit line length. Do not amend the source commits. Preserve intentional Markdown structure, including paragraph breaks, headings, separate list items, blockquotes, fenced code blocks, and tables.

If the branch has exactly one commit in the PR range:

- Use the commit title as the PR title.
- Use the commit description as the PR body.
- If the commit has no useful body, use the patch to write a concise body. Explain why the change helps, not just what changed.

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
- If a commit has no useful body, use its patch to write a concise description that explains why the change helps.

### PR Stacks

When creating or updating a PR stack, apply these rules to every PR:

- Prefix the title with its one-based position and the total number of PRs, for example `(7/7) This is the title`.
- Add a `## Stack` section to the body. List every PR from tip to base. Mark the current PR with `__->__`. Wrap the section in `codex-pr-stack` comments:

```markdown
<!-- codex-pr-stack:start -->
## Stack
* #123
* __->__ #122
* #121
<!-- codex-pr-stack:end -->
```

## Draft Safety

- For a new PR, always pass the draft option, such as `--draft` with `gh pr create` or `draft: true` with the GitHub connector.
- For an existing PR, preserve its review state. Do not use draft/ready conversion commands when updating its title, body, labels, reviewers, or metadata.
- Never use this skill to mark a draft PR ready for review.
- If a requested action would change an existing PR's review state, ask the user for a different workflow. Do not change that state.
