---
name: github-comments
description: "Post or edit GitHub issue comments, pull-request comments, review bodies, inline review comments, and replies with the required attribution prefix, then verify the published text. Use whenever a task writes a GitHub comment or submits a review. Do not use for titles, pull-request descriptions, commit messages, issue bodies, or read-only GitHub work."
---

# GitHub Comments

Use this skill for every GitHub comment or review write, including writes performed inside another workflow. It does not authorize a write by itself.

## Required Prefix

Start every issue comment, pull-request comment, review body, inline review comment, and reply exactly with:

```text
**Ralf-AI:**
```

Follow the prefix with either a space or a blank line before the comment text. The prefix applies only to comments and review bodies, not GitHub titles, pull-request descriptions, issue bodies, or commit messages.

## Workflow

1. Confirm that the user or active workflow authorized the write and that the target is correct.
2. Add the prefix to every comment body in the operation, including the review body and each inline comment in a multi-comment review.
3. Immediately before posting or editing, verify that each body starts with the exact prefix.
4. Perform the requested write with a GitHub connector when available, or `gh` when needed and authenticated.
5. Read back every published comment or review and verify the exact prefix. If an authorized write omitted it and editing is safely supported, correct the same comment and verify it again. Do not post a duplicate as a workaround.
