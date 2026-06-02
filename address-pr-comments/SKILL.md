---
name: address-pr-comments
description: "Address review conversations on the current GitHub pull request end to end. Use when the user asks to address PR comments, review feedback, unresolved conversations, or requested changes: fetch current-PR threads, skip conversations already answered by Ralf-AI, apply actionable fixes locally with one new commit per request, push commits, and reply to each considered conversation on GitHub without resolving threads."
---

# Address PR Comments

Process current-PR review conversations autonomously. Keep every local fix and GitHub reply traceable to one reviewer request.

## Required Reply Prefix

Prefix every GitHub message posted by this workflow with exactly:

```text
**Ralf-AI:**
```

Do not post an unprefixed GitHub reply, review, or PR comment.

## Workflow

1. Confirm the working tree state. Preserve unrelated local changes and never rewrite published history.
2. Resolve the open pull request for the current branch. Prefer GitHub connector tools; use `gh` only when connector coverage is insufficient and authentication permits it.
3. Fetch all inline review conversations, including resolved state and all comments in each thread. Fetch PR-level comments too when available.
4. Consider only conversations whose last comment is not a previous agent response beginning with `**Ralf-AI:**`.
5. Classify each considered conversation:
   - **Change request:** implement the requested local change when clear and safe.
   - **Question:** reply on GitHub without editing code unless it is a leading question and the implied change is clear and sensible.
   - **Ambiguous, conflicting, or risky request:** ask the user before editing or posting a speculative answer.
6. For each implemented request, validate the focused scope, then create one new commit dedicated to that request. Do not combine separate requests into one commit. Keep earlier commits intact.
7. Push all new commits to the current PR branch.
8. Reply to each considered conversation after pushing:
   - For a fix, state what changed and include the commit SHA.
   - For a question, answer directly.
   - Prefix every reply with `**Ralf-AI:**`.
9. Leave conversations unresolved unless the user explicitly asks to resolve them.
10. Summarize considered conversations, commits, push status, validation, replies, and any intentionally deferred items.

## Review Rules

- Treat a thread as already handled when its last comment starts with `**Ralf-AI:**`; do not add another reply unless new reviewer feedback follows it.
- Use one commit per reviewer request even when several requests touch the same file.
- Run the narrowest useful validation after each fix. Run broader checks before the final push when multiple commits interact.
- Keep question-only responses out of local commits.
- Do not stage unrelated user changes.
- Do not resolve conversations automatically.

## GitHub Tooling Notes

- Prefer thread-aware GitHub connector reads such as `list_pull_request_review_threads` so the latest reply and resolved state are visible.
- Prefer connector reply tools for inline conversations.
- If a connector reply requires a numeric REST comment ID but a thread read exposes only a GraphQL node ID, use the connector's available thread/comment APIs or another permitted GitHub connector read. Do not guess identifiers.
- When posting any GitHub message, verify the body starts with `**Ralf-AI:**` before sending.
