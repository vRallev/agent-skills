---
name: check-dependency-upgrades
description: Audit TOML version catalogs in Gradle projects for newer dependency and plugin releases using the Maven repositories configured by the build. Use when asked to fetch or check out a base branch and inspect libs.versions.toml, list stable or preview upgrades, verify candidate artifacts, report full Maven group:artifact:version coordinates, or distinguish real upgrades from BOM-managed, commit-pinned, and compatibility-only versions.
---

# Check dependency upgrades

Produce a read-only, reproducible dependency audit from a known Git commit. Do not edit dependency versions unless the user separately requests an upgrade.

## Workflow

1. Read the applicable repository instructions and build, dependency, verification, and source-control guidance.
2. Check `git status` before switching commits. Preserve unrelated work. If Git LFS makes the read-only status fail, retry only that check with the LFS process disabled locally for the command.
3. Determine the configured remote's default branch. When requested, fetch it, record the fetched SHA, and check out that exact SHA detached. If the configured SSH identity fails, use an available hosting credential helper without changing the remote configuration.
4. Inspect root and literal `includeBuild` `settings.gradle` or `settings.gradle.kts` files plus relevant Gradle properties. Identify repository order, content filters, exclusive repositories, plugin repositories, credential sources, and the resolved Maven Central URL. Never print tokens or user Gradle properties wholesale.
5. Run the bundled scanner from the repository root:

   ```sh
   python3 "${CODEX_HOME:-$HOME/.codex}/skills/check-dependency-upgrades/scripts/audit_version_catalog.py" \
     --root "$PWD" \
     --catalog gradle/libs.versions.toml \
     --output-json /tmp/dependency-upgrades.json \
     --output-markdown /tmp/dependency-upgrades.md
   ```

   The scanner recognizes common Kotlin and Groovy repository declarations, `mavenLocal()`, and literal included builds. It resolves repository URLs and Basic-auth credentials from settings variables backed by Gradle properties, environment variables, local file paths, and literal fallbacks. For expressions that arbitrary build logic prevents it from resolving, add repeatable `--repository NAME=URL` options and pass environment-variable names—not secrets—with `--credential-env NAME=USERNAME_ENV:SECRET_ENV`. Use repeatable `--settings PATH` options for non-literal included builds or other settings files.

6. Inspect the JSON `unresolved` list. Resolve metadata-less entries individually:
   - For commit-SHA pins, never infer ordering from hexadecimal values. Use catalog comments or the producer dependency that defines the intended pin, then verify the exact candidate POM on the configured Maven host.
   - For a repository without `maven-metadata.xml`, use that same host's supported build/package API when available. Do not substitute Maven Search or another public index.
   - Treat suffixes such as `-jdk5` and `-compat` as compatibility variants unless evidence shows they are ordinary upgrades.
7. Verify every reported candidate with an exact POM request. The scanner does this for metadata-derived candidates; perform the same check for manually resolved pins.
8. Present the result as Markdown tables. Include:
   - checked-out SHA and subject;
   - catalog alias and repository-request counts;
   - the exact Maven Central mirror and other configured hosts used;
   - stable or pinned updates;
   - preview-only updates;
   - compatibility variants that are not normal upgrades;
   - full `group:artifact:version` coordinates using the stable or pinned version in the stable table and the preview version in the preview-only table.
9. Explain that versionless aliases are platform/BOM-managed and name the controlling BOM update. State that no newer release was found for remaining aliases.
10. Remove temporary workspace files, keep generated reports under `/tmp`, and confirm `HEAD` still equals the recorded base SHA and the worktree is clean.

## Repository fidelity

- Query only repositories used by Gradle builds. Prefer the build's configured mirror over public Maven Central.
- Respect exclusive repositories such as JitPack or vendor SDK feeds and authenticated internal feeds.
- Review `settingsFiles`, `repositories`, and `repositoryWarnings` in the JSON before trusting the result. Static parsing cannot evaluate arbitrary Gradle build logic; supply unresolved settings, repository URLs, and credential environment mappings explicitly.
- The scanner applies `MAVEN_REPO_<NORMALIZED_NAME>_USERNAME` plus `_TOKEN` or `_PASSWORD` for generic authenticated feeds. It also accepts common `<name>Username`, `<name>Password`, and dotted Gradle-property forms.
- Include plugin marker coordinates as `plugin.id:plugin.id.gradle.plugin:version`.
- Group aliases that share one catalog version only when their selected candidate versions match.
- Separate latest stable from latest available preview. Exclude snapshots unless the user explicitly asks for them.
- Report failures and unresolved metadata honestly; do not silently omit a coordinate.

## Bundled script

`scripts/audit_version_catalog.py` parses the TOML catalog, discovers common Kotlin and Groovy repository declarations across root and literal included builds, queries Maven metadata concurrently, validates candidate POMs, and emits JSON plus Markdown tables. It uses only the Python standard library and requires Python 3.11 or newer.
