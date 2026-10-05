---
name: watch-pr
description: "Monitor a GitHub PR until every current-head CI check succeeds and reviewer feedback stops arriving. Use when asked to watch, monitor, babysit, or wait on a PR. Poll every 20 seconds in the current task. Address CI failures as they occur. Use $address-pr-comments for feedback and $commit-changes for each CI fix or accepted reviewer request. Push commits. Continue until CI stays green and feedback stays quiet."
---

# Watch PR

Monitor one pull request through CI and review feedback. Do not merge the PR.

## Setup

1. Resolve the supplied PR URL or number, repository, head branch, and current head SHA. If no PR is supplied, find the current branch's open PR. If the result is missing or ambiguous, ask the user.
2. Confirm write access to the PR branch. Use a checkout whose current branch maps to that PR. Preserve unrelated local changes. If switching would disturb them, use a separate worktree.
3. Prefer GitHub connector reads that include review threads. If connector coverage is insufficient and authentication permits, use `gh`.
4. Take an initial machine-readable snapshot of:
   - every CI check and job for the current head SHA,
   - inline review threads and all comments in each thread,
   - PR reviews and PR-level conversation comments.
5. Record stable comment identifiers or timestamps. Use them to detect new feedback, including replies to previously handled threads.

## Monitoring loop

Remain in the current active task. Wait 20 seconds between polls. Do not create or schedule an automation, heartbeat, reminder, follow-up task, or background monitor.

On every poll:

1. Refresh PR state and the head SHA. If the head changed:

   - Discard the old CI result.
   - Restart green/quiet confirmation for the new head.

2. Compare all review and PR-comment streams with the previous snapshot.
3. If new human feedback has no existing `**Ralf-AI:**` response as its latest reply, run `$address-pr-comments` for the PR. Follow all its safety, commit, validation, push, and unresolved-thread rules. Apply the classification rules below.
4. After `$address-pr-comments` finishes, immediately refresh the head SHA, CI, and comments. Any pushed commit or new comment resets green/quiet confirmation.
5. While a current-head CI job is missing, queued, pending, running, stale, or has a conclusion other than `success`, continue waiting. Do not count skipped, neutral, cancelled, timed-out, or action-required jobs as successful.
6. Address each CI failure as it occurs:
   - Inspect the failing check or job to identify the concrete failure.
   - Implement the smallest appropriate fix for that failure.
   - Run focused validation.
   - Use `$commit-changes` to create one commit for that failure.
   - Push the commit.

   Keep each CI failure fix in its own commit.
7. If a failure is transient, caused by infrastructure, externally blocked, unrelated to the PR, or unsafe to fix without more context, report the blocker. Continue monitoring. Do not make a speculative change.

## Feedback classification

Apply these additions while using `$address-pr-comments`:

Use `$github-comments` for every GitHub comment or review write.

- **Reasonable suggestion:** Accept a clear, safe request that improves correctness, reliability, tests, readability, or maintainability without materially expanding the PR. Use `$commit-changes` to make one new commit for that request. Run focused validation. Push it. Reply with the commit SHA.
- **Unreasonable suggestion:** Reject only when the request is clearly incorrect, irrelevant, duplicative, contrary to verified project constraints, or a disproportionate scope expansion. Make no code change. Post a concise, respectful GitHub reply with the concrete reason.
- **Ambiguous, conflicting, or risky suggestion:** Do not label uncertainty as unreasonable. Before editing or posting a speculative answer, ask the user as required by `$address-pr-comments`.
- **Question:** Answer directly on GitHub when the answer is verified. Do not create a commit for a question-only response.

For every commit description, do not add line breaks to meet a maximum line length. Keep each prose paragraph or list item on one line. Preserve intentional Markdown structure. Let the rendering tool wrap the text.

Never amend or force-push. Keep one commit per accepted reviewer request. Unless the user explicitly asks, never resolve a review conversation.

## Completion

Finish only when all of these are true for the same current head SHA:

- At least one CI check has been discovered. Every discovered check and job has completed with conclusion `success`. No expected or required check is missing.
- `$address-pr-comments` has considered every observed human review or PR-level comment. Each handled conversation's latest reply starts with `**Ralf-AI:**`, or no reply was needed.
- Two consecutive full snapshots, at least 20 seconds apart, have the same head SHA and no new human comments, while CI remains fully successful.

If the PR is merged or closed, stop. Report that terminal state. If authentication, branch permissions, an ambiguous or risky request, or a permanently failed external check requires owner action, report the exact blocker and required action. Do not falsely declare the PR green.

Give a concise final report with the final head SHA, CI result, handled and rejected feedback, commits pushed, validation run, replies posted, and remaining manual action.
