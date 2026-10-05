---
name: update-dependencies
description: "Upgrade repository dependencies to exact user-supplied versions such as group:artifact:version. Research changelogs, known issues, Android Issue Tracker, GitHub, and repository revert history. Verify the changes, commit them, create or update a draft PR, and watch CI and review feedback. Use when the user invokes $update-dependencies or requests a complete dependency upgrade with explicit target versions."
---

# Update Dependencies

Research and implement the exact requested versions. Deliver a PR and watch its CI and review feedback.

## Required input

Require one or more exact dependency targets. For Maven or Gradle dependencies, accept:

```text
group:artifact:target-version
```

Accept a list, comma-separated values, or one coordinate per line. For another ecosystem, accept an unambiguous package and version.

- Treat the supplied version as authoritative.
- Do not silently select a newer version.
- Compare the target with the current resolved version. If the request says upgrade but the target is lower:

  - Identify it as a downgrade.
  - Before changing resolution, obtain explicit confirmation and the reason for the downgrade.

- Before forcing a confirmed downgrade below an upstream dependency's declared version, require evidence of binary and runtime compatibility. For that downgrade, require explicit acceptance of the risk. If compatibility evidence is absent, stop and report the incompatibility.
- If input is incomplete or ambiguous, ask for the missing coordinate or target version.
- Unless the user explicitly requests them, reject dynamic targets such as `latest`, `+`, or version ranges.
- If every target is already present on the base branch, report that no change is needed. Do not create an empty commit or PR.

Example invocation:

```text
Use $update-dependencies to upgrade com.google.android.gms:play-services-location:21.4.0.
```

## Workflow

### 1. Establish repository state

1. Read all applicable `AGENTS.md` files and repository manuals before editing.
2. Inspect the worktree, branch, upstream, remotes, and default branch. Preserve unrelated changes.
3. If authentication permits, refresh the base branch. If direct Git fetch is unavailable, verify freshness through the hosting API.
4. Locate each declaration, alias, lockfile entry, and direct consumer with `rg`. Record the current resolved version and affected applications or modules. For a transitive-only package, identify the dependency that selects it. Determine whether a normal declaration, constraint, or strict resolution rule would change resolution. Do not add an ineffective pin.
5. Search open PRs, remote branches, and bot branches for the exact upgrade before creating new work.
   - Do not silently create a duplicate PR.
   - Reuse an existing PR only if its branch is writable and no history rewrite is needed.
   - If taking over, superseding, or closing an existing PR requires a material choice, report the choice. Ask the user. Continue read-only research where possible.

### 2. Research every version change

Browse for current release and issue information. Prefer primary sources. Keep direct URLs for the commit, PR, and final report.

For each current-to-target version change:

1. Find the official changelog or release notes and the release date.
2. Summarize changes from the current version to the requested target. Include intermediate releases when applicable.
3. When useful, compare official package metadata and artifacts for the current and target versions. Check:
   - platform or minimum-runtime requirements;
   - direct and transitive dependency versions;
   - packaging, manifests, native libraries, and consumer rules;
   - removed, deprecated, breaking, or behavior-changing APIs.
4. Inspect call sites to determine whether the repository uses each changed behavior.
5. Research known issues with exact-version queries:
   - official release-note warnings, security advisories, and vendor issue trackers;
   - open and closed issues in the official GitHub repository;
   - release milestones, discussions, and exact coordinate/version searches;
   - reputable integration repositories only as secondary evidence.
6. For an Android library or AAR, also scan [Google Issue Tracker](https://issuetracker.google.com/) using the exact coordinate, artifact name, target version, changed API names, and relevant public component.
7. If no public source repository exists:

   - Say so.
   - Scan the closest official sample or integration repositories and global GitHub issues.
   - Do not imply that a sample contains the closed-source implementation.

8. State negative findings narrowly: "no publicly discoverable target-version-specific issue found as of YYYY-MM-DD." Note limited confidence for recent releases, closed-source code, trackers that require sign-in, or sparse adoption.

### 3. Check repository upgrade and revert history

Use the exact declaration history and commit evidence. Do not rely only on broad commit-message searches.

1. Trace the version key or literal with `git log --follow`, `git log -S`, and `git log -G` as appropriate.
2. Inspect commits that introduced prior versions and any later revert, rollback, downgrade, compatibility fix, or reland.
3. Distinguish dependency reverts from unrelated feature reverts that happen to mention the same domain.
4. Report whether versions only increased. If history includes a problematic version, identify that version, commit, cause, and mitigation.

### 4. Implement the smallest upgrade

1. Change only the canonical version declaration, lockfile, or tool-generated files required by the repository.
2. Do not hand-edit generated source or dependency output that the package manager owns.
3. Unless the target requires a compatibility fix, avoid API or behavior changes.
4. Keep dependency changes isolated from unrelated cleanup.
5. Use one dependency-only commit for a related requested batch. If repository guidance requires it, split independently risky or unrelated upgrades.

### 5. Verify compatibility

Follow the repository's verification guidance. Choose checks that exercise dependency resolution and integration with affected applications.

At minimum:

1. Review the complete diff. Run `git diff --check`.
2. Run the package manager's resolution or dependency-insight command. Confirm that each exact target wins conflict resolution.
3. Build or test the affected application or modules as required by repository guidance.
4. If an upgrade changes behavior used by call sites, run additional focused tests.
5. Distinguish missing SDKs, credentials, or other prerequisites from dependency failures. When safe, retry with an existing configured toolchain. Never commit local credentials or machine paths.

### 6. Commit with the changelog impact

Invoke `$commit-changes`. Follow its instructions. Before committing, review staged, unstaged, and untracked files again. Include only the requested upgrade.

Identify the dependency or related dependency group and target version in the commit title. In the commit body, explain:

- why the upgrade is useful;
- every old-to-new version;
- the official release date of each target version in `YYYY-MM-DD` format;
- the important changelog behavior, fixes, or breaking changes;
- whether changed behavior reaches current call sites;
- changes to minimum platform versions or transitive dependencies, and repository compatibility;
- known issues found, or the date and limitations of a search that found no public reports;
- direct official changelog and issue-search URLs.

Wrap dependency coordinates, code references, file paths, command names, and Gradle module or task paths such as `:abc:def` in backticks in both the commit body and the resulting PR description. Preserve official source URLs as usable Markdown links.

Do not add line breaks to meet a maximum line length in commit bodies or PR descriptions. Keep each prose paragraph or list item on one line. Preserve intentional Markdown structure. Let GitHub or another rendering tool wrap the text.

Do not put routine verification commands in the commit body. Write a body that also works as a PR description. `$create-or-update-pr` derives PR text from commits.

### 7. Create or update the PR

Invoke `$create-or-update-pr`. Follow its instructions.

1. Push without force-pushing or rewriting remote history.
2. Create new PRs as drafts. Preserve the review state of existing PRs.
3. Verify the resulting title, body, base, head, draft state, and URL.
4. Confirm that the PR body retains the commit's release dates, changelog, repository impact, known issues and issue-search limitations, and source links. Keep backticks around code references and Gradle module paths.
5. Unless the user explicitly authorizes closing or replacing it, leave any pre-existing automated PR untouched.

### 8. Watch the PR

After the PR exists, invoke `$watch-pr`. Follow it until its completion or stopping criteria apply. Do not merge or mark the PR ready.

- Monitor the current head's complete CI, review threads, reviews, and PR comments.
- Diagnose failures before editing. For verified transient or infrastructure failures, rerun the check. Do not make speculative code changes.
- Use a separate commit for each genuine CI fix or accepted reviewer request. Never amend or force-push.
- If the watcher requires every discovered check to conclude `success`, do not report conditionally skipped jobs as green. Report the exact blocker and any required owner action.

## Final report

Report:

- each dependency's old and new versions plus the target-version release date;
- material changelog changes and repository impact;
- known issues and research limitations;
- prior repository revert findings;
- validation performed and exact resolved versions;
- commit SHA, PR URL, base/head branches, and draft state;
- final CI/review state, reruns or fixes, and remaining manual action;
- any existing overlapping PR left untouched.
