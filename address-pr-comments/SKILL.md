---
name: address-pr-comments
description: "Address review conversations on the current GitHub pull request. Use when the user asks to address PR comments, review feedback, unresolved conversations, or requested changes. Fetch threads and skip those already answered by Ralf-AI. Evaluate each request. Make one new commit per accepted request, push commits, and reply without resolving threads."
---

# Address PR Comments

Process review conversations on the current PR autonomously. Link each local fix and GitHub reply to one reviewer request. Evaluate reviewer comments before acting on them.

Use `$github-comments` for every GitHub comment or review write.

## Workflow

1. Confirm the working tree state. Preserve unrelated local changes. Never rewrite published history.
2. Find the open PR for the current branch. Prefer GitHub connector tools. Use `gh` only if connector coverage is insufficient and authentication permits it.
3. Fetch all inline review conversations, including each thread's resolved state and all comments. If available, fetch PR-level comments too.
4. Consider only conversations whose last comment is not a previous agent response beginning with `**Ralf-AI:**`.
5. Classify each considered conversation:
   - First assess the comment against the PR description, current patch, surrounding code, and intended direction.
   - **Applicable change request:** If the change is clear, safe, technically sound, and aligned with the PR's intent, implement it.
   - **Question:** Reply on GitHub. Edit code only if it is a leading question and implies a clear, sensible change.
   - **Inapplicable or misaligned request:** If the request rests on an incorrect assumption, does not apply, exceeds the PR's scope, or conflicts with its intent, reject it without changing code. Reply politely with the concrete reason.
   - **Ambiguous, conflicting, or risky request:** Ask the user only if you cannot confidently accept or reject the request, or if either choice would materially change the PR's intent.
6. For each accepted request, validate the focused scope. Then use `$commit-changes` to create one new commit dedicated to that request. Do not combine separate requests into one commit. Keep earlier commits intact.
   - Follow the skill's Markdown rules. Put backticks around code references, file paths, and Gradle module or task paths such as `:abc:def`.
   - Do not insert line breaks to limit line length. Keep each prose paragraph or list item on one line. Preserve intentional Markdown structure. Let the rendering tool wrap text.
7. Push all new commits to the current PR branch.
8. After pushing, reply to each considered conversation:
   - For a fix, state what changed and include the commit SHA.
   - For a question, answer directly.
   - For a rejected request, state that it was not applied. Briefly explain why it does not apply or conflicts with the PR's intent.
   - Use `$github-comments` for each reply.
9. Unless the user explicitly asks to resolve them, leave conversations unresolved.
10. Summarize considered conversations, accepted and rejected requests, commits, push status, validation, replies, and intentionally deferred items.

## Review Rules

- If a thread's last comment starts with `**Ralf-AI:**`, treat it as handled. Reply again only after new reviewer feedback.
- Evaluate each suggestion. Reject feedback that does not apply or conflicts with the PR's intent.
- Even if several requests touch the same file, use one commit per accepted request.
- After each fix, run the narrowest useful validation. If multiple commits interact, run broader checks before the final push.
- Keep question-only responses out of local commits.
- Do not stage unrelated user changes.
- Do not resolve conversations automatically.

## GitHub Tooling Notes

- Prefer thread-aware GitHub connector reads such as `list_pull_request_review_threads` to see the latest reply and resolved state.
- Prefer connector reply tools for inline conversations.
- If a connector reply requires a numeric REST comment ID but a thread read exposes only a GraphQL node ID, use the connector's available thread/comment APIs or another permitted GitHub connector read. Do not guess identifiers.
