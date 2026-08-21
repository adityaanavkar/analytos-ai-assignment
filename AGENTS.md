# Aditya's agent instructions

These are common instructions for Kun's agents across all scenarios.

## General Guidelines

* Never use the em dash "—". Use plain dash "-" instead
* When writing commit messages, NEVER auto-add your agent name as co-author
* Never manually modify CHANGELOG.md files or any files that are marked as auto-generated
* When writing or substantially editing long Markdown files, put each full sentence on its own line.
  Preserve normal Markdown structure, but avoid wrapping multiple sentences onto one physical line.
* When making technical decisions, do not give much weight to development cost.
  Instead, prefer quality, simplicity, robustness, scalability, and long term maintainability.
* When doing bug fixes, always start with reproducing the bug in an E2E setting as closely aligned with how an end use
  This makes sure you find the real problem so your fix will actually solve it.
* When end-to-end testing a product, be picky about the UI you see and be obsessed with pixel perfection.
  If something clearly looks off, even if it is not directly related to what you are doing, try to get it fixed along
* Apply that same high standard to engineering excellence: lint, test failures, and test flakiness.
  If you see one, even if it is not caused by what you are working on right now, still get it fixed.

## Assignment delivery priority

* Prioritize getting a thin, demonstrable, end-to-end version running before hardening individual components.
* Do not block the first working RAG flow on production-grade infrastructure, exhaustive abstractions, comprehensive evaluation, or pixel-perfect UI.
* After the first end-to-end flow works, improve quality, security, evaluation, observability, and documentation iteratively.


## Subagent delegation

Use subagents aggressively to reduce work performed by the primary Sol agent.

Default to Luna subagents for:
- repository exploration and code search
- locating relevant files and call sites
- reading and summarizing modules
- straightforward implementation tasks
- writing or updating tests
- running tests and investigating simple failures
- mechanical refactors
- documentation
- independent verification of changes

The primary Sol agent should focus on:
- task decomposition
- architecture and design decisions
- difficult debugging
- ambiguous requirements
- reviewing subagent findings
- integrating changes
- final verification