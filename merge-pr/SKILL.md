---
name: merge-pr
description: Merge a GitHub pull request identified explicitly or unambiguously from context, and continue until GitHub confirms it is fully merged. Use when the user asks to merge a PR, finish merging a PR, resolve merge conflicts and merge, wait for required CI, or monitor and retry a merge queue. Verify the actual required reviewer approvals and required CI checks, ignore non-required CI failures, safely rebase and force-push conflicted PR branches, and retry rejected merge-queue entries without running full local builds.
---

# Merge PR

Own one pull request from the user's request until GitHub reports `MERGED`. Submission, auto-merge, a successful merge command, and entry into a merge queue are intermediate states, not completion.

## Resolve the pull request and rename the task

1. Accept a PR number, a GitHub PR URL, or an unambiguous PR already established in the current conversation. A PR associated with the current Git branch is acceptable only when it is the uniquely established target. Never choose from several candidate PRs or guess based on a title. If no PR can be resolved unambiguously, ask the user for its number or URL before making changes.
2. Resolve and verify the PR's canonical `OWNER/REPO`, number, URL, state, base branch, exact head SHA, head branch, head repository, author, draft status, reviews, mergeability, and merge state:

   ```bash
   gh pr view "$PR" --repo "$REPO" --json number,url,state,isDraft,author,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner,isCrossRepository,maintainerCanModify,reviews,latestReviews,reviewDecision,mergeable,mergeStateStatus,autoMergeRequest,mergedAt
   ```

   Omit `--repo` only for the initial, unambiguous current-repository discovery. Once the canonical repository is known, pass `--repo "$REPO"` to every subsequent PR command.
3. Find and call the available Codex `set_thread_title` tool to rename the **current** task to exactly `Merge PR_NUMBER`; for example, `Merge 12345`. Use `codex_app__set_thread_title({"title":"Merge 12345"})` when available. Do not create another task or rename an unrelated task. If the title tool is unavailable, continue the merge workflow and disclose the limitation in the final response.
4. If GitHub already reports `MERGED`, report the verified PR number, link, and merge time and finish. A closed, unmerged PR, a draft, unavailable permissions, or an ambiguous repository is a real blocker; report it rather than reopening, marking ready, bypassing protections, or guessing.

## Check the actual merge requirements

Refresh live PR and base-branch protection on every loop and immediately before every merge. Do not hard-code `main`, `master`, a review count, a check name, or a merge strategy.

1. Inspect the effective rules for the **actual PR base branch**, including applicable repository rulesets, legacy branch protection, code-owner requirements, stale-review dismissal, approval of the most recent push, required conversation resolution, required status checks, and whether that branch uses a merge queue. Prefer the applicable rules endpoint and verify legacy protection when accessible:

   ```bash
   gh api "repos/$REPO/rules/branches/$BASE_BRANCH"
   gh api "repos/$REPO/branches/$BASE_BRANCH/protection"
   ```

   Use the strictest applicable required review count. One valid reviewer approval is normally sufficient when the live rule requires one; additional optional approvals must never block merging. Do not mistake an inaccessible protection endpoint for proof that there are no requirements. Let GitHub's protected merge operation remain the final authority.
2. Count the current, effective reviews of distinct **non-author** reviewers. Use `reviews` and `latestReviews`, and exclude an approval superseded by that reviewer's `CHANGES_REQUESTED` or `DISMISSED` review. Honor actual code-owner, stale-review, and last-push requirements. An empty, missing, stale, or temporarily `BLOCKED` `reviewDecision` does not invalidate an otherwise effective approval. If a required human approval is missing, continue monitoring; never approve as the author, invent approval, solicit a review without authorization, or bypass the rule.
3. Inspect **required checks only** on the exact current PR head:

   ```bash
   gh pr checks "$PR_NUMBER" --repo "$REPO" --required \
     --json name,state,bucket,workflow,link
   ```

   Require each applicable check to reach a passing outcome. Treat `pending`, `fail`, and `cancel` in a required check as not ready; verify that any skipped check actually satisfies the live protection rule. Ignore failing, cancelled, or pending **non-required** checks. Do not use an unfiltered `gh pr checks`, `statusCheckRollup`, or overall PR check summary as the merge gate.
4. Wait for pending required checks with the scoped watcher:

   ```bash
   gh pr checks "$PR_NUMBER" --repo "$REPO" --required --watch --interval 30
   ```

   Monitor the running command and keep the user informed. If a required check fails, inspect its linked GitHub Actions or Buildkite evidence on the exact head. Safely rerun an actually transient or infrastructure-related failure when supported. Make a narrowly scoped fix only when the failure, necessary change, and authorization are clear; otherwise report the concrete external or human blocker. Reinspect approvals and restart check monitoring whenever the head changes.

## Resolve an actual merge conflict

Treat `mergeable: CONFLICTING` or an explicitly verified base/head conflict as a conflict. `mergeable: UNKNOWN`, `mergeStateStatus: UNKNOWN`, and queue-related or protection-related `BLOCKED` states require a fresh read; they are not evidence of a conflict and must not trigger a speculative rebase.

When a real conflict exists:

1. Re-read the PR and record its exact old head SHA, actual base branch, PR head branch, and head repository. Verify push permission, especially for a fork. Never assume the PR head is on `origin`.
2. Preserve all existing staged, unstaged, and untracked user work and any attached worktrees. Prefer a new, agent-owned detached worktree in the system temporary directory. Fetch the canonical base and exact PR head first:

   ```bash
   git fetch origin "refs/heads/$BASE_BRANCH"
   git fetch origin "refs/pull/$PR_NUMBER/head"
   git worktree add --detach "$MERGE_PR_WORKTREE" "$OLD_HEAD_SHA"
   git -C "$MERGE_PR_WORKTREE" rebase "origin/$BASE_BRANCH"
   ```

   Verify that the fetched PR head is still `$OLD_HEAD_SHA` before rebasing. If `origin` is not the canonical base-repository remote, identify and use the remote that actually points to `$REPO`. Do not switch the user's current branch, stash their changes, reset or clean their checkout, detach an existing worktree, or reuse an unrelated temporary worktree.
3. Resolve each conflict with the smallest correct change that preserves the intended behavior of both branches. Read the affected repository instructions and relevant code before editing. Continue the rebase and refresh GitHub state; if a third party updates the PR head, discard no one else's changes and restart from the new head.
4. Do **not** run full local builds, full test suites, `./gradlew build`, repository-wide `check`, or E2E suites. Rely on required CI. Run only a cheap, narrowly targeted formatter or validation when directly needed for the conflict resolution.
5. Push to the actual head repository and exact head branch using an explicit head-matching lease:

   ```bash
   git -C "$MERGE_PR_WORKTREE" push \
     --force-with-lease="refs/heads/$HEAD_BRANCH:$OLD_HEAD_SHA" \
     "$HEAD_REMOTE" "HEAD:refs/heads/$HEAD_BRANCH"
   ```

   Resolve `$HEAD_REMOTE` from the verified PR head repository; use a matching configured remote or the head repository's verified authenticated SSH URL. Never use bare `--force`, push to the base branch, assume a fork is pushable, or overwrite a changed remote head. A rejected lease means refresh and restart, not retry with weaker protection.
6. Read the PR back, verify the exact newly pushed head SHA, recheck effective approvals and rules, and wait for **new-head required CI**. Remove only the agent-owned temporary worktree after its rebase and push have finished and it is safe to remove. Preserve an interrupted or unresolved worktree and report its path.

## Submit and monitor until merged

1. After live approval, required-check, conflict, and head-SHA checks all pass, submit the normal protected GitHub merge with `--match-head-commit "$HEAD_SHA"`. Never use `--admin`, disable a protection, delete a branch, or force a merge.
2. If the actual base branch requires a merge queue, let GitHub choose the queue merge method:

   ```bash
   gh pr merge "$PR_NUMBER" --repo "$REPO" \
     --match-head-commit "$HEAD_SHA"
   ```

   GitHub may enable auto-merge or add the PR to the queue. Neither response means the PR is merged.
3. If there is no required merge queue, inspect repository-allowed merge methods and explicit user or repository preferences. Prefer an allowed squash merge when no preference says otherwise; fall back to an allowed rebase or merge-commit strategy:

   ```bash
   gh pr merge "$PR_NUMBER" --repo "$REPO" --squash \
     --match-head-commit "$HEAD_SHA"
   ```

   Substitute `--rebase` or `--merge` only when that is the verified allowed or requested method. Do not claim success from the command exit code.
4. Poll the same canonical PR, its exact head, required checks, auto-merge state, and merge-queue entry until `gh pr view` verifies `state: MERGED` and a non-null `mergedAt`. Use a persistent command session or the available task-wait mechanism, a measured polling interval, and regular concise progress updates; never abandon the loop merely because checks are pending or the PR is queued.
5. If the queue rejects or removes the PR while it remains open and unmerged, return to the beginning of the loop. Refresh base movement, the head SHA, rules, approvals, required checks, and real mergeability; resolve any new actual conflict, wait for the new required CI, and submit again. Never blindly resubmit a PR that is already in the queue.
6. Stop only when GitHub verifies the PR is fully `MERGED`, the user cancels, or further progress genuinely requires a missing human approval, unavailable permission, unresolved protected review conversation, an unpushable fork, or another action outside the user's authorization. Report any blocker precisely instead of presenting queued, pending, auto-merge-enabled, or rejected state as success.

On success, report only the confirmed PR number, link, and merge time. Mention conflict resolution or queue retries only when they actually occurred.
