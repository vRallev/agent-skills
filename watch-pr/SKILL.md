---
name: watch-pr
description: "Monitor a GitHub pull request until every CI check on its current head is successful and reviewer feedback has stopped arriving. Use when the user asks to watch, monitor, babysit, or wait on a PR; repeatedly inspect CI and new review or PR comments, invoke $address-pr-comments for feedback, commit and push reasonable requested changes, politely reject unreasonable requests on GitHub, and continue until the PR is stably green and quiet."
---

# Watch PR

Monitor one pull request through CI and review feedback. Do not merge the PR.

## Setup

1. Resolve the supplied PR URL or number, repository, head branch, and current head SHA. If no PR is supplied, resolve the open PR for the current branch; ask only if the result is missing or ambiguous.
2. Confirm write access to the PR branch and use a checkout whose current branch maps to that PR. Preserve unrelated local changes; use a separate worktree when switching would disturb them.
3. Prefer thread-aware GitHub connector reads. Use `gh` when connector coverage is insufficient and authentication permits it.
4. Take an initial machine-readable snapshot of:
   - every CI check and job for the current head SHA,
   - inline review threads and all comments in each thread,
   - PR reviews and PR-level conversation comments.
5. Record stable comment identifiers or timestamps so later snapshots detect newly posted feedback, including replies to previously handled threads.

## Monitoring Loop

Use the product's recurring monitoring or wait mechanism when available. Otherwise poll at a five-minute cadence without a tight shell loop.

On every poll:

1. Refresh PR state and the head SHA. If the head changed, discard the old CI result and restart green/quiet confirmation for the new head.
2. Compare all review and PR-comment streams with the previous snapshot.
3. When new human-authored feedback exists whose latest reply is not an existing `**Ralf-AI:**` response, run `$address-pr-comments` from `/Users/ralf/.codex/skills/address-pr-comments/SKILL.md` for the PR. Follow all of its safety, commit, validation, push, reply-prefix, and unresolved-thread rules, with the classification rules below.
4. After `$address-pr-comments` finishes, refresh the head SHA, CI, and comments immediately. Any pushed commit or new comment resets green/quiet confirmation.
5. Continue waiting while a current-head CI job is missing, queued, pending, in progress, stale, or has any conclusion other than `success`. Do not count skipped, neutral, cancelled, timed-out, or action-required jobs as successful.
6. Inspect a persistent CI failure enough to identify and report the blocker, but do not make an unsolicited CI-driven code change unless a reviewer request or the user authorizes it. Continue monitoring transient or externally owned failures.

## Feedback Classification

Apply these additions while using `$address-pr-comments`:

- **Reasonable suggestion:** Accept a clear, safe request that improves correctness, reliability, tests, readability, or maintainability without materially expanding the PR. Make one new commit for that request, run focused validation, push it, and reply with the commit SHA.
- **Unreasonable suggestion:** Reject only when the request is clearly incorrect, irrelevant, duplicative, contrary to verified project constraints, or a disproportionate scope expansion. Make no code change. Post a concise, respectful GitHub reply with the concrete reason and prefix it exactly with `**Ralf-AI:**`.
- **Ambiguous, conflicting, or risky suggestion:** Do not label uncertainty as unreasonable. Ask the user before editing or posting a speculative answer, as required by `$address-pr-comments`.
- **Question:** Answer directly on GitHub when the answer is verified. Do not create a commit for a question-only response.

Never amend or force-push. Keep one commit per accepted reviewer request. Never resolve a review conversation unless the user explicitly asks.

## Completion

Finish only when all of these are true for the same current head SHA:

- At least one CI check has been discovered, every discovered CI check and job has completed with conclusion `success`, and no expected or required check is missing.
- Every observed human review or PR-level comment has been considered by `$address-pr-comments`; the latest reply in each handled conversation is `**Ralf-AI:**` or no reply was needed.
- Two consecutive full snapshots, at least five minutes apart, have the same head SHA and no new human comments, while CI remains fully successful.

If the PR is merged or closed, stop and report that terminal state. If authentication, branch permissions, an ambiguous/risky request, or a permanently failed external check requires owner action, report the exact blocker and required action; do not falsely declare the PR green.

Give a concise final handoff with the final head SHA, CI result, handled and rejected feedback, commits pushed, validation run, replies posted, and any remaining manual action.
