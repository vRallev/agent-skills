---
name: merge-pr
description: Merge a GitHub PR or PR stack identified explicitly or clearly from context. Continue until GitHub confirms it is fully merged. Use when asked to merge, finish a merge, resolve conflicts and merge, wait for required CI, or monitor and retry a merge queue. Verify required approvals and CI. Ignore non-required CI failures. Safely rebase and force-push conflicted branches. Retry rejected queue entries without full local builds.
---

# Merge PR

Continue until GitHub reports the requested PR and every required stack member as `MERGED`. Submission, auto-merge, a successful merge command, and queue entry do not confirm completion.

## Resolve the pull request and rename the task

1. Accept a PR number, a GitHub PR URL, or a clearly established PR from the conversation. Use the current branch's PR only when it is the uniquely established target. Never choose among several candidates or guess from a title. If the target is unclear, ask for its number or URL before making changes.
2. Verify the PR's canonical `OWNER/REPO`, number, URL, state, base branch, exact head SHA, head branch, head repository, author, draft status, reviews, mergeability, and merge state:

   ```bash
   gh pr view "$PR" --repo "$REPO" --json number,url,state,isDraft,author,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner,isCrossRepository,maintainerCanModify,reviews,latestReviews,reviewDecision,mergeable,mergeStateStatus,autoMergeRequest,mergedAt
   ```

   Omit `--repo` only for initial discovery in an unambiguous current repository. Once the canonical repository is known, pass `--repo "$REPO"` to every subsequent PR command.
3. Find the available Codex `set_thread_title` tool. Rename the **current** task to exactly `Merge PR_NUMBER`, for example `Merge 12345`. When available, use `codex_app__set_thread_title({"title":"Merge 12345"})`. Do not create another task or rename an unrelated task. If the title tool is unavailable, continue merging. Disclose the limitation in the final response.
4. If GitHub already reports `MERGED`, report the verified PR number, link, and merge time. Finish. If the PR is closed but unmerged, is a draft, lacks permissions, or has an ambiguous repository, report the blocker. Do not reopen it, mark it ready, bypass protections, or guess.

## Merge a pull request stack

Before checking requirements, determine whether the PR belongs to a stack. Verify the complete live stack and its base-to-tip order from the PR base and head branches. Use a PR-body stack list only as a discovery hint.

- If the requested PR is the tip, the merge set is the whole stack. Before enqueueing any PR, make every PR satisfy this skill's requirements. Enqueue the whole stack with the repository's stack-aware operation. Never enqueue or merge only part of it.
- If the requested PR is below the tip, the merge set is the requested PR and every dependency below it toward the base. Do not enqueue PRs above the requested PR.
- Apply every readiness, repair, queue-retry, monitoring, and completion rule to every PR in the merge set. Finish only after GitHub reports them all as `MERGED`.
- If enqueueing or merging fails, keep the same merge set. Fix the blockers. Retry that set. Never shrink it to bypass a blocker.
- If any PR in the merge set needs a rebase or restack, rebase the whole stack from base to tip. Include PRs above the requested PR. Push the whole stack in that order. Preserve the head-SHA safety checks and force-with-lease rules below. Before enqueueing, refresh the merge set's heads, approvals, required checks, conversations, and mergeability.
- If no stack-aware enqueue operation is available, stop. Report that blocker. Do not risk a partial-stack merge.

## Check the actual merge requirements

On every loop and immediately before merging, refresh the live PR and base-branch protection. Do not hard-code `main`, `master`, a review count, a check name, or a merge strategy.

1. Inspect effective rules for the **actual PR base branch**. Include repository rulesets, legacy branch protection, code-owner requirements, stale-review dismissal, approval of the latest push, required conversation resolution, required status checks, and merge queues. Prefer the applicable rules endpoint. When accessible, verify legacy protection:

   ```bash
   gh api "repos/$REPO/rules/branches/$BASE_BRANCH"
   gh api "repos/$REPO/branches/$BASE_BRANCH/protection"
   ```

   Use the strictest applicable required review count. If the live rule requires one, one valid approval is normally sufficient. Optional approvals must never block merging. An inaccessible protection endpoint does not prove that no requirements exist. Treat GitHub's protected merge operation as the final authority.
2. Count effective reviews from distinct **non-author** reviewers. Use `reviews` and `latestReviews`. Exclude approvals superseded by that reviewer's `CHANGES_REQUESTED` or `DISMISSED` review. Honor actual code-owner, stale-review, and last-push requirements. An empty, missing, stale, or temporarily `BLOCKED` `reviewDecision` does not invalidate an otherwise effective approval. If a required human approval is missing, continue monitoring. Never approve as the author, invent approval, solicit a review without authorization, or bypass the rule.
3. Inspect **required checks only** on the exact current PR head:

   ```bash
   gh pr checks "$PR_NUMBER" --repo "$REPO" --required \
     --json name,state,bucket,workflow,link
   ```

   Require each applicable check to pass. For a required check, treat `pending`, `fail`, and `cancel` as not ready. For a skipped check, verify that it satisfies the live protection rule. Ignore failing, cancelled, or pending **non-required** checks. Do not use unfiltered `gh pr checks`, `statusCheckRollup`, or an overall check summary as the merge gate.
4. Wait for pending required checks with the scoped watcher:

   ```bash
   gh pr checks "$PR_NUMBER" --repo "$REPO" --required --watch --interval 30
   ```

   Monitor the running command. Keep the user informed. If a required check fails, inspect its linked GitHub Actions or Buildkite evidence on the exact head. If supported, safely rerun a verified transient or infrastructure failure. Make a focused fix only when the failure, necessary change, and authorization are clear. Otherwise, report the concrete external or human blocker. Whenever the head changes, recheck approvals and restart check monitoring.

## Resolve required review conversations

If the actual base branch requires resolved review conversations, resolve **every unresolved review conversation on the PR without asking for additional permission**. Invoking this skill authorizes those resolutions as part of merging. Unresolved conversations alone are not a reason to stop.

1. Fetch every page of review threads, including outdated threads. Resolve each unresolved thread through GitHub's review-thread resolution API. Leave resolved threads unchanged.
2. Immediately before merging or resubmitting to the queue, fetch all pages again. Verify that no unresolved threads remain. Under the same requirement, resolve new or reopened threads. If resolution fails, report the specific permission or API blocker. Do not bypass the requirement or claim success.
3. Keep conversation resolution separate from reviewer approval. Resolving threads does not satisfy required approvals or authorize dismissing reviews. If resolution is not required for merging, leave threads unchanged unless the user explicitly requests resolution.

## Resolve an actual merge conflict

Treat `mergeable: CONFLICTING` or a verified base/head conflict as a conflict. For `mergeable: UNKNOWN`, `mergeStateStatus: UNKNOWN`, or queue or protection `BLOCKED` states, read the state again. These states do not prove a conflict. Do not rebase speculatively.

When a real conflict exists:

1. Read the PR again. Record its exact old head SHA, actual base branch, head branch, and head repository. Verify push permission, especially for a fork. Never assume the PR head is on `origin`.
2. Preserve all existing staged, unstaged, and untracked user work and any attached worktrees. Prefer a new, agent-owned detached worktree in the system temporary directory. Fetch the canonical base and exact PR head first:

   ```bash
   git fetch origin "refs/heads/$BASE_BRANCH"
   git fetch origin "refs/pull/$PR_NUMBER/head"
   git worktree add --detach "$MERGE_PR_WORKTREE" "$OLD_HEAD_SHA"
   git -C "$MERGE_PR_WORKTREE" rebase "origin/$BASE_BRANCH"
   ```

   Before rebasing, verify that the fetched PR head is still `$OLD_HEAD_SHA`. If `origin` is not the canonical base remote, identify the remote that points to `$REPO`. Use that remote. Do not switch the user's current branch, stash their changes, reset or clean their checkout, detach an existing worktree, or reuse an unrelated temporary worktree.
3. Before editing, read the affected repository instructions and relevant code. Resolve each conflict with the smallest correct change that preserves both branches' intended behavior. Continue the rebase. Refresh GitHub state. If a third party updates the PR head, preserve their changes. In that case, restart from the new head.
4. Do **not** run full local builds, full test suites, `./gradlew build`, repository-wide `check`, or E2E suites. Rely on required CI. Run only a cheap, focused formatter or validation directly needed for conflict resolution.
5. Push to the actual head repository and exact head branch using an explicit head-matching lease:

   ```bash
   git -C "$MERGE_PR_WORKTREE" push \
     --force-with-lease="refs/heads/$HEAD_BRANCH:$OLD_HEAD_SHA" \
     "$HEAD_REMOTE" "HEAD:refs/heads/$HEAD_BRANCH"
   ```

   Resolve `$HEAD_REMOTE` from the verified head repository. Use a matching configured remote or that repository's verified authenticated SSH URL. Never use bare `--force`, push to the base branch, assume a fork is pushable, or overwrite a changed remote head. If the lease is rejected, refresh state. Restart with the same protection.
6. Read the PR back. Verify the exact newly pushed head SHA. Recheck effective approvals and rules. Wait for **new-head required CI**. After the rebase and push finish, remove only the agent-owned temporary worktree, if safe. If work is interrupted or unresolved, preserve the worktree. Report its path.

## Submit and monitor until merged

1. After live approval, required checks, required conversation resolution, conflict, and head-SHA checks all pass, submit GitHub's normal protected merge with `--match-head-commit "$HEAD_SHA"`. Never use `--admin`, disable protection, delete a branch, or force a merge.
2. If the actual base branch requires a merge queue, let GitHub choose the queue merge method:

   ```bash
   gh pr merge "$PR_NUMBER" --repo "$REPO" \
     --match-head-commit "$HEAD_SHA"
   ```

   GitHub may enable auto-merge or add the PR to the queue. Neither response means the PR is merged.
3. If no merge queue is required, inspect allowed merge methods and explicit user or repository preferences. If no preference says otherwise, prefer an allowed squash merge. If squash is unavailable or a preference requires another method, use an allowed rebase or merge-commit strategy:

   ```bash
   gh pr merge "$PR_NUMBER" --repo "$REPO" --squash \
     --match-head-commit "$HEAD_SHA"
   ```

   Substitute `--rebase` or `--merge` only for a verified allowed or requested method. Do not claim success from the command exit code.
4. Poll the same canonical PR, exact head, required checks, auto-merge state, and queue entry. Continue until `gh pr view` verifies `state: MERGED` and a non-null `mergedAt`. Use a persistent command session or available task-wait mechanism. Use a measured polling interval. Give regular, concise progress updates. Do not abandon the loop because checks are pending or the PR is queued.
5. If the queue rejects or removes an open, unmerged PR, return to the start of the loop. Refresh base movement, head SHA, rules, approvals, required checks, review conversations, and mergeability. If required, resolve new unresolved conversations. Resolve any new verified conflict. Wait for new required CI. Submit again. Never blindly resubmit a PR already in the queue.
6. Stop only after GitHub verifies `MERGED`, the user cancels, or progress requires an action you cannot take. Such blockers include missing human approval, unavailable permission to act or resolve required conversations, an unpushable fork, or action outside the user's authorization. Report the precise blocker. Do not present queued, pending, auto-merge-enabled, or rejected state as success.

On success, report only the confirmed PR numbers, links, and merge times. Mention conflict resolution or queue retries only when they actually occurred.
