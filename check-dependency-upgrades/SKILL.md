---
name: check-dependency-upgrades
description: Audit TOML version catalogs and Gradle wrappers for newer releases. Use the build's Maven repositories and Gradle's official version service. Use when asked to fetch or check out a base branch for an audit, inspect libs.versions.toml or gradle-wrapper.properties, or list stable or preview upgrades. Also use to honor version-hold comments, verify artifacts, report full Maven coordinates and wrapper targets, or distinguish upgrades from BOM-managed, commit-pinned, held, and compatibility-only versions.
---

# Check dependency upgrades

Produce a reproducible, read-only dependency audit from a known Git commit. Unless the user separately requests an upgrade, do not edit versions.

## Workflow

1. Read the applicable repository instructions and build, dependency, verification, and source-control guidance.
2. Check `git status` before switching commits. Preserve unrelated work. If Git LFS makes this read-only check fail, retry only this command. Disable the LFS process only for that retry command.
3. Determine the configured remote's default branch. When requested:
   - Fetch that branch.
   - Record the fetched SHA.
   - Check out that exact SHA detached.

   If the configured SSH identity fails, use an available hosting credential helper. Keep the remote configuration unchanged.
4. Inspect these build files:
   - root and literal `includeBuild` `settings.gradle` or `settings.gradle.kts` files;
   - relevant Gradle properties;
   - every `gradle/wrapper/gradle-wrapper.properties` under the audited root or discovered build roots.

   Identify repository order, content filters, exclusive repositories, plugin repositories, credential sources, and the resolved Maven Central URL. Record each wrapper's distribution URL, version, and `bin` or `all` type. Never print tokens or user Gradle properties wholesale.
5. Run the bundled scanner from the repository root:

   ```sh
   python3 "${CODEX_HOME:-$HOME/.codex}/skills/check-dependency-upgrades/scripts/audit_version_catalog.py" \
     --root "$PWD" \
     --catalog gradle/libs.versions.toml \
     --output-json /tmp/dependency-upgrades.json \
     --output-markdown /tmp/dependency-upgrades.md
   ```

   The scanner recognizes common Kotlin and Groovy repository declarations, `mavenLocal()`, literal included builds, and Gradle wrapper property files. It also recognizes explicit hold comments attached to `[versions]` entries or a wrapper's `distributionUrl`. Holds include `#noinspection GradleDependency` and clear instructions such as “do not upgrade” or “keep this version pinned.” Warnings that an upgrade would force or break downstream consumers also count as holds.

   The scanner resolves repository URLs and Basic-auth credentials from settings variables. Supported sources include Gradle properties, environment variables, local file paths, and literal fallbacks. It queries `https://services.gradle.org/versions/all` for wrapper releases. It preserves each wrapper's host and `bin` or `all` distribution type. It verifies candidate distributions with HEAD requests.

   If build logic prevents the scanner from resolving a repository, add repeatable `--repository NAME=URL` options. Pass environment-variable names with `--credential-env NAME=USERNAME_ENV:SECRET_ENV`. Never pass secrets as option values. For non-literal included builds or other settings files, use repeatable `--settings PATH` options.

6. Inspect the JSON results:
   - Read `unresolved`. Resolve each entry that lacks metadata.
   - Inspect `gradleWrappers`, `gradleVersionService`, and `gradleDistributionResults`. Report every wrapper. Include no update, preview-only updates, unparseable URLs, version-service failures, and candidate distribution failures.
   - For commit-SHA pins, never infer ordering from hexadecimal values. Find the intended pin in catalog comments or the producer dependency. Verify the exact candidate POM on the configured Maven host.
   - For a repository without `maven-metadata.xml`, use the same host's supported build/package API when available. Do not substitute Maven Search or another public index.
   - Unless evidence shows an ordinary upgrade, treat suffixes such as `-jdk5` and `-compat` as compatibility variants.
   - Read every non-empty `versionComment` for meaning. Inspect `upgradeSuppression` and `suppressedUpdateAliases`. The scanner classifies common hold language automatically. If other wording clearly says not to merge an upgrade, move that version key into the third table. Preserve the comment as the reason.
   - Before trusting the tables, inspect `catalogActions`, including `blockedByHeldCoordinates` and `verificationFailures`.
   - After automatic and manual classification, build the held-coordinate set from the third table. Assess readiness for the actual catalog edit: one shared `[versions]` key or one inline alias. If any affected alias references a held coordinate, exclude the entire key from the first and second tables. Do not hide the held coordinate and keep the key ready. Report the key under `Catalog keys blocked by intentionally held coordinates`.
   - For aliases sharing one version key, select the highest candidate version present for every alias. If another alias does not publish that version, do not report a per-alias stable candidate as a version-key update. Report the highest common preview only in the preview table, after every exact POM verifies.
7. Verify every reported Maven candidate with an exact POM request. Verify every wrapper candidate with an exact HEAD request to its distribution URL. The scanner checks metadata-derived candidates. Apply the same checks to manually resolved pins.
8. Present the result as Markdown tables. Include:
   - checked-out SHA and subject;
   - catalog alias, repository-request, wrapper-file, Gradle-version-service, and distribution-check counts;
   - the exact Maven Central mirror and other configured hosts used;
   - first table: `Ready stable or pinned updates`, with all and only actionable stable or pinned Maven coordinates and verified Gradle wrapper distributions;
   - preview-only updates;
   - third table: intentionally held-back updates that must not be merged, with the suppression comment and candidate coordinates;
   - catalog keys blocked because changing them would also upgrade an intentionally held coordinate;
   - compatibility variants that are not normal upgrades;
   - full `group:artifact:version` coordinates, with stable or pinned versions in the stable table and preview versions in the preview-only table;
   - verified candidate distribution URLs for wrapper updates.
9. Explain what controls each versionless alias, such as a platform/BOM or an included build. Name the controlling source or update. State that no newer release was found for the remaining aliases and wrapper files.
10. Remove temporary workspace files. Keep generated reports under `/tmp`. Confirm that `HEAD` still equals the recorded base SHA. Confirm that the worktree matches its recorded baseline, including pre-existing changes.

## Repository fidelity

- Query only repositories used by Gradle builds. Prefer the build's configured mirror over public Maven Central.
- Query only Gradle's official version service for Gradle release metadata. Derive each candidate distribution URL from the wrapper's existing host. Preserve its `bin` or `all` type. Do not silently replace a custom mirror with `services.gradle.org`.
- Redact credentials and query strings from reported wrapper URLs. Use the original URL only for the validation request.
- Unless the user explicitly requests them, exclude Gradle snapshots, nightlies, release nightlies, and broken releases. Keep stable and preview wrapper candidates separate.
- Respect exclusive repositories such as JitPack or vendor SDK feeds and authenticated internal feeds.
- Before trusting the result, review `settingsFiles`, `repositories`, and `repositoryWarnings` in the JSON. Static parsing cannot evaluate arbitrary Gradle build logic. Supply unresolved settings, repository URLs, and credential environment mappings explicitly.
- The scanner applies `MAVEN_REPO_<NORMALIZED_NAME>_USERNAME` plus `_TOKEN` or `_PASSWORD` for generic authenticated feeds. It also accepts common `<name>Username`, `<name>Password`, and dotted Gradle-property forms.
- Include plugin marker coordinates as `plugin.id:plugin.id.gradle.plugin:version`.
- Treat one shared catalog version key as one atomic action. Select stable and preview candidates from versions published for every alias using that key. Verify every coordinate at the selected common version.
- Apply holds to the full coordinate and catalog action. If any alias under a version key references a held coordinate, block the entire key. This applies even if other aliases could be upgraded. Put the key in the blocked section. Do not remove the held coordinate from a ready row and keep that row.
- Treat `#noinspection GradleDependency` or a clear hold directly above a `[versions]` entry as an instruction not to merge newer versions for that key's aliases. Match meaning, not only exact strings. Examples include “do not upgrade,” “keep this dependency pinned,” or “upgrading would force a higher version on consumers.” Preserve the comment as the reason. Move the candidates into the third, intentionally held-back table. Do not treat unrelated explanations or URLs as holds. If a comment is ambiguous, flag it for manual review. Do not silently suppress the update.
- Separate the latest stable version from the latest preview. Unless explicitly requested, exclude snapshots and nightlies before candidate selection, POM scheduling, summary counts, and Markdown generation.
- Treat the scanner-generated `Ready stable or pinned updates` table as the source of truth. If the scanner classified a key as held-blocked, shared-version-incompatible, snapshot-only, or unverified, do not manually add it.
- Report failures and unresolved metadata. Do not silently omit a coordinate.

## Bundled script

`scripts/audit_version_catalog.py` parses TOML catalogs and directive or natural-language holds. It discovers common Kotlin and Groovy repository declarations and Gradle wrappers in the root and literal included builds. It queries Maven metadata and Gradle's official version service. It validates candidate POMs and wrapper distributions. It emits JSON and Markdown tables. It uses only the Python standard library and requires Python 3.11 or newer.
