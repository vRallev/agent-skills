---
name: check-dependency-upgrades
description: Audit TOML version catalogs and Gradle wrapper distributions for newer releases using the Maven repositories configured by the build and Gradle's official version service. Use when asked to fetch or check out a base branch and inspect libs.versions.toml or gradle-wrapper.properties, list stable or preview upgrades, honor directive or natural-language comments that intentionally hold versions, verify candidate artifacts, report full Maven coordinates and wrapper targets, or distinguish real upgrades from BOM-managed, commit-pinned, intentionally held-back, and compatibility-only versions.
---

# Check dependency upgrades

Produce a read-only, reproducible dependency audit from a known Git commit. Do not edit dependency versions unless the user separately requests an upgrade.

## Workflow

1. Read the applicable repository instructions and build, dependency, verification, and source-control guidance.
2. Check `git status` before switching commits. Preserve unrelated work. If Git LFS makes the read-only status fail, retry only that check with the LFS process disabled locally for the command.
3. Determine the configured remote's default branch. When requested, fetch it, record the fetched SHA, and check out that exact SHA detached. If the configured SSH identity fails, use an available hosting credential helper without changing the remote configuration.
4. Inspect root and literal `includeBuild` `settings.gradle` or `settings.gradle.kts` files, relevant Gradle properties, and every `gradle/wrapper/gradle-wrapper.properties` under the audited root or discovered build roots. Identify repository order, content filters, exclusive repositories, plugin repositories, credential sources, the resolved Maven Central URL, and every wrapper's distribution URL, version, and `bin` or `all` type. Never print tokens or user Gradle properties wholesale.
5. Run the bundled scanner from the repository root:

   ```sh
   python3 "${CODEX_HOME:-$HOME/.codex}/skills/check-dependency-upgrades/scripts/audit_version_catalog.py" \
     --root "$PWD" \
     --catalog gradle/libs.versions.toml \
     --output-json /tmp/dependency-upgrades.json \
     --output-markdown /tmp/dependency-upgrades.md
   ```

   The scanner recognizes common Kotlin and Groovy repository declarations, `mavenLocal()`, literal included builds, Gradle wrapper property files, and explicit upgrade-hold comments directly attached to `[versions]` entries or a wrapper's `distributionUrl`. Holds include `#noinspection GradleDependency` and clear natural-language instructions such as “do not upgrade,” “keep this version pinned,” or warnings that an upgrade would force or break downstream consumers. It resolves repository URLs and Basic-auth credentials from settings variables backed by Gradle properties, environment variables, local file paths, and literal fallbacks. It queries `https://services.gradle.org/versions/all` for wrapper releases, preserves each wrapper's existing host and `bin` or `all` distribution type, and verifies candidate distributions with a HEAD request. For expressions that arbitrary build logic prevents it from resolving, add repeatable `--repository NAME=URL` options and pass environment-variable names—not secrets—with `--credential-env NAME=USERNAME_ENV:SECRET_ENV`. Use repeatable `--settings PATH` options for non-literal included builds or other settings files.

6. Inspect the JSON `unresolved` list. Resolve metadata-less entries individually:
   - Inspect `gradleWrappers`, `gradleVersionService`, and `gradleDistributionResults`. Report every wrapper, including wrappers with no update, preview-only updates, unparseable distribution URLs, version-service failures, and candidate distribution failures.
   - For commit-SHA pins, never infer ordering from hexadecimal values. Use catalog comments or the producer dependency that defines the intended pin, then verify the exact candidate POM on the configured Maven host.
   - For a repository without `maven-metadata.xml`, use that same host's supported build/package API when available. Do not substitute Maven Search or another public index.
   - Treat suffixes such as `-jdk5` and `-compat` as compatibility variants unless evidence shows they are ordinary upgrades.
   - Inspect every non-empty `versionComment` semantically, plus `upgradeSuppression` and `suppressedUpdateAliases`. The scanner classifies common hold language automatically. If different wording still clearly says not to merge an upgrade, manually move that version key into the third table and preserve the comment as the reason.
   - Inspect `catalogActions`, including `blockedByHeldCoordinates` and `verificationFailures`, before trusting the generated tables.
   - Build the held-coordinate set from the third table after automatic and manual classification. Classify readiness by the catalog edit that would actually be made: a shared `[versions]` key or one inline alias. If any alias changed by that edit references a held coordinate, block the entire catalog key from the first and second tables. Do not merely hide the held coordinate while retaining the key as ready. Report the key under `Catalog keys blocked by intentionally held coordinates`.
   - For aliases sharing one version key, select the highest candidate version present for every alias. Never report a per-alias stable candidate as a version-key update when another alias using that key does not publish the same version. A highest common preview may be reported in the preview table only after every exact POM verifies.
7. Verify every reported Maven candidate with an exact POM request and every wrapper candidate with an exact HEAD request to the candidate distribution URL. The scanner does this for metadata-derived candidates; perform the same check for manually resolved pins.
8. Present the result as Markdown tables. Include:
   - checked-out SHA and subject;
   - catalog alias, repository-request, wrapper-file, Gradle-version-service, and distribution-check counts;
   - the exact Maven Central mirror and other configured hosts used;
   - as the first table, `Ready stable or pinned updates`, containing all and only actionable stable or pinned Maven coordinates and verified Gradle wrapper distributions;
   - preview-only updates;
   - as the third table, intentionally held-back updates that must not be merged, including the suppression comment and candidate coordinates;
   - catalog keys blocked because changing them would also upgrade an intentionally held coordinate;
   - compatibility variants that are not normal upgrades;
   - full `group:artifact:version` coordinates using the stable or pinned version in the stable table and the preview version in the preview-only table, plus the verified candidate distribution URL for wrapper updates.
9. Explain how each versionless alias is controlled—for example by a platform/BOM or an included build—and name the controlling source or update. State that no newer release was found for remaining aliases and wrapper files.
10. Remove temporary workspace files, keep generated reports under `/tmp`, and confirm `HEAD` still equals the recorded base SHA and the worktree matches its recorded baseline, including any pre-existing changes.

## Repository fidelity

- Query only repositories used by Gradle builds. Prefer the build's configured mirror over public Maven Central.
- Query only Gradle's official version service for Gradle release metadata. Derive each candidate distribution URL from the wrapper's existing distribution host and preserve its `bin` or `all` type; do not silently replace a custom mirror with `services.gradle.org`.
- Redact credentials and query strings from reported wrapper URLs. Use the original URL only for the validation request.
- Exclude Gradle snapshots, nightlies, release nightlies, and broken releases unless the user explicitly requests them. Keep stable and preview wrapper candidates separate.
- Respect exclusive repositories such as JitPack or vendor SDK feeds and authenticated internal feeds.
- Review `settingsFiles`, `repositories`, and `repositoryWarnings` in the JSON before trusting the result. Static parsing cannot evaluate arbitrary Gradle build logic; supply unresolved settings, repository URLs, and credential environment mappings explicitly.
- The scanner applies `MAVEN_REPO_<NORMALIZED_NAME>_USERNAME` plus `_TOKEN` or `_PASSWORD` for generic authenticated feeds. It also accepts common `<name>Username`, `<name>Password`, and dotted Gradle-property forms.
- Include plugin marker coordinates as `plugin.id:plugin.id.gradle.plugin:version`.
- Treat one shared catalog version key as one atomic action. Compute stable and preview candidates from the intersection of versions published for every alias using that key, and verify every coordinate at the selected common version.
- Treat held-back classification as coordinate-wide and action-blocking. If any alias under a catalog version key references a held coordinate, the entire key is not ready to upgrade, even if other aliases under that key are otherwise upgradeable. Put that key in the blocked section rather than filtering the coordinate out of a ready row.
- Treat `#noinspection GradleDependency` or a clear natural-language hold directly attached above a `[versions]` entry as an instruction not to merge newer versions for aliases using that key. Natural-language holds include equivalent phrasing—not only exact strings—such as “do not upgrade,” “keep this dependency pinned,” or “upgrading would force a higher version on consumers.” Preserve the catalog comment as the reason and move those candidates into the third, intentionally held-back table. Do not interpret unrelated explanatory comments or URLs as upgrade suppressions; if a comment is ambiguous, call it out for manual review instead of silently suppressing the update.
- Separate latest stable from latest available preview. Exclude snapshots and nightlies before candidate selection, POM scheduling, summary counts, and Markdown generation unless the user explicitly asks for them.
- Treat the scanner-generated `Ready stable or pinned updates` table as the source of truth. Do not manually add a catalog key that the scanner classified as held-blocked, shared-version-incompatible, snapshot-only, or unverified.
- Report failures and unresolved metadata honestly; do not silently omit a coordinate.

## Bundled script

`scripts/audit_version_catalog.py` parses the TOML catalog and directive or natural-language suppressions, discovers common Kotlin and Groovy repository declarations plus Gradle wrappers across root and literal included builds, queries Maven metadata and Gradle's official version service, validates candidate POMs and wrapper distributions, and emits JSON plus Markdown tables. It uses only the Python standard library and requires Python 3.11 or newer.
