---
name: update-dependencies
description: "Upgrade one or more repository dependencies from user-supplied exact target coordinates such as group:artifact:version, research changelogs and known issues, check Android Issue Tracker and GitHub plus repository revert history, implement and verify the version changes, then commit, create or update a draft PR, and watch CI and review feedback. Use when the user invokes $update-dependencies or requests an end-to-end dependency bump with explicit target versions."
---

# Update Dependencies

Run a dependency upgrade from exact requested versions through researched, watched PR delivery.

## Input Contract

Require one or more exact dependency targets. For Maven or Gradle dependencies, accept:

```text
group:artifact:target-version
```

Accept a list, comma-separated values, or one coordinate per line. For another ecosystem, accept its unambiguous package-and-version form.

- Treat the supplied version as authoritative.
- Do not silently select a newer version.
- Compare it with the current resolved version. If the request says upgrade but the target is lower, identify it as a downgrade and obtain explicit confirmation and rationale before mutating resolution.
- Before forcing a confirmed downgrade below an upstream dependency's declared version, require evidence of binary and runtime compatibility plus explicit acceptance of the risk. Stop and report the incompatibility when that evidence is absent.
- Ask for the missing coordinate or target version when input is incomplete or ambiguous.
- Reject dynamic targets such as `latest`, `+`, or version ranges unless the user explicitly requests them.
- If every target is already present on the base branch, report the no-op and do not create an empty commit or PR.

Example invocation:

```text
Use $update-dependencies to upgrade com.google.android.gms:play-services-location:21.4.0.
```

## Workflow

### 1. Establish repository state

1. Read all applicable `AGENTS.md` files and repository manuals before editing.
2. Inspect the worktree, branch, upstream, remotes, and default branch. Preserve unrelated changes.
3. Refresh the base branch when authentication permits. Verify freshness through the hosting API when direct Git fetch is unavailable.
4. Locate each declaration, alias, lockfile entry, and direct consumer with `rg`. Record the current resolved version and affected applications or modules. When a package is only transitive, identify the dependency that selects it and determine whether a normal declaration, constraint, or strict resolution rule would actually change the result; do not add an ineffective pin.
5. Search open PRs, remote branches, and bot branches for the exact upgrade before creating new work.
   - Do not silently create a duplicate PR.
   - Reuse an existing PR only when its branch is writable and doing so requires no history rewrite.
   - If taking over, superseding, or closing an existing PR requires a material choice, report it and ask the user while continuing read-only research where possible.

### 2. Research every version delta

Browse because release and issue information is time-sensitive. Prefer primary sources and retain direct URLs for the commit, PR, and final handoff.

For each old-to-target version:

1. Find the official changelog or release notes and the release date.
2. Summarize changes between the repository's current version and the requested target, including intermediate releases when applicable.
3. Inspect official package metadata and artifacts when useful. Compare items such as:
   - platform or minimum-runtime requirements;
   - direct and transitive dependency versions;
   - packaging, manifests, native libraries, and consumer rules;
   - removed, deprecated, breaking, or behavior-changing APIs.
4. Inspect repository call sites to determine whether each documented behavior change is exercised here.
5. Research known issues with exact-version queries:
   - official release-note warnings, security advisories, and vendor issue trackers;
   - open and closed issues in the official GitHub repository;
   - release milestones, discussions, and exact coordinate/version searches;
   - reputable integration repositories only as secondary evidence.
6. For an Android library or AAR, also scan [Google Issue Tracker](https://issuetracker.google.com/) using the exact coordinate, artifact name, target version, changed API names, and relevant public component.
7. If no public source repository exists, say so. Scan the closest official sample or integration repositories plus global GitHub issues; do not imply that a sample repository contains the closed-source implementation.
8. State negative findings narrowly: "no publicly discoverable target-version-specific issue found as of YYYY-MM-DD." Note limited confidence for recent releases, closed-source code, sign-in-gated trackers, or sparse adoption.

### 3. Check repository upgrade and revert history

Use exact declaration history and commit evidence, not only broad commit-message search.

1. Trace the version key or literal with `git log --follow`, `git log -S`, and `git log -G` as appropriate.
2. Inspect commits that introduced prior versions and any later revert, rollback, downgrade, compatibility fix, or reland.
3. Distinguish dependency reverts from unrelated feature reverts that happen to mention the same domain.
4. Report whether history is monotonic or identify the exact prior problematic version, commit, cause, and mitigation.

### 4. Implement the smallest upgrade

1. Change only the canonical version declaration, lockfile, or generated-by-tool files required by the repository.
2. Do not hand-edit generated source or dependency output that the package manager owns.
3. Avoid API or behavior changes unless the target version requires a compatibility fix.
4. Keep dependency changes isolated from unrelated cleanup.
5. Use one dependency-only commit for a logically related requested batch. Split independently risky or unrelated upgrades when repository guidance requires it.

### 5. Verify compatibility

Follow the repository's verification guidance and choose checks that exercise dependency resolution and affected application wiring.

At minimum:

1. Review the complete diff and run `git diff --check`.
2. Run the package manager's resolution or dependency-insight command and confirm each exact target wins conflict resolution.
3. Build or test the affected application or modules as required by repository guidance.
4. Run additional focused tests when an upgrade changes behavior used by repository call sites.
5. Treat missing SDKs, credentials, or other environment prerequisites separately from dependency failures. Retry with an existing configured toolchain when safe; never commit local credentials or machine paths.

### 6. Commit with the changelog impact

Invoke `$commit-changes` and follow its instructions. Before committing, re-audit staged, unstaged, and untracked files so only the requested upgrade is included.

Make the commit title identify the dependency or coherent dependency group and target version. Make the commit body explain:

- why the upgrade is useful;
- every old-to-new version;
- the important changelog behavior, fixes, or breaking changes;
- whether changed behavior reaches current call sites;
- platform-floor or transitive dependency changes and repository compatibility;
- known issues found, or the dated and caveated absence of public reports;
- direct official changelog and issue-search URLs.

Do not put routine verification commands in the commit body. The body must be useful as the PR description because `$create-or-update-pr` derives PR text from commits.

### 7. Create or update the PR

Invoke `$create-or-update-pr` and follow its instructions.

1. Push without force-pushing or rewriting remote history.
2. Create new PRs as drafts; preserve the review state of existing PRs.
3. Verify the resulting title, body, base, head, draft state, and URL.
4. Ensure the PR body retains the changelog, repository impact, known-issue caveat, and source links from the commit.
5. Leave any pre-existing automated PR untouched unless the user explicitly authorizes closing or replacing it.

### 8. Watch the PR

After the PR exists, invoke `$watch-pr` and follow it through its terminal criteria. Do not merge or mark the PR ready.

- Monitor the current head's complete CI, review threads, reviews, and PR comments.
- Diagnose failures before editing. Rerun verified transient or infrastructure-owned failures without speculative code changes.
- Use a separate commit for each genuine CI fix or accepted reviewer request; never amend or force-push.
- If the watcher requires every discovered check to conclude `success`, do not misreport conditionally skipped jobs as green. Report the exact terminal blocker and any required owner action.

## Final Handoff

Report:

- each dependency's old and new versions;
- material changelog changes and repository impact;
- known issues and research limitations;
- prior repository revert findings;
- validation performed and exact resolved versions;
- commit SHA, PR URL, base/head branches, and draft state;
- final CI/review state, reruns or fixes, and remaining manual action;
- any existing overlapping PR left untouched.
