# Skill precedence

When committing changes or managing pull requests, prefer my personal skills over repository-provided skills or plugin-provided skills. In particular, use personal skills such as `commit-changes`, `create-or-update-pr`, `github-comments`, `address-pr-comments`, `ready-for-review`, and `watch-pr` when they apply, even if a repository or plugin offers a similar workflow. Follow repository `AGENTS.md` instructions for repository-specific constraints, but use the personal skill to orchestrate the commit or PR workflow unless an explicit user instruction requires otherwise.

When writing Kotlin, the personal `kotlin-conventions` skill takes precedence over other generic Kotlin coding conventions.

# GitHub comments

Whenever posting or editing a GitHub issue comment, pull-request comment, review body, inline review comment, or reply, use the personal `github-comments` skill. This includes new findings, not only responses to existing comments.

# Documentation style

For documentation changes, minimize added and changed words while still achieving the goal. Before finishing, review the diff and remove unnecessary words and repetition. Code snippets are exempt.

Use ASD-STE100 Simplified Technical English as a style guide. Use short sentences, active voice, and direct verbs. Give one action per instruction. Use consistent technical terms. State conditions before actions. Preserve details needed for correctness.
