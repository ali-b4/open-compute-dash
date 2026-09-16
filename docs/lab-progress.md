# Lab progress

## Stage 0 / audit and migration proposal

- **Status:** awaiting_review
- **What changed:** added the [audit and concrete Stage 1 proposal](stage-0-audit.md) and [decision register](decisions.md). Existing lab and website code are unchanged.
- **How to inspect it:** read the audit's workspace map, reusable-code table, and proposed Stage 1 increment.
- **Tests and evidence:** 41 baseline offline tests and 11 website tests passed; website type check and lint passed. Baseline local edits preserved; website remains clean. Figma screenshot access failed. No live provider calls, builds, or deployment.
- **Owner exercise:** compare `../provider-eval-v0.1/scripts/provider_config.py` with `/Users/ali/Documents/baloch-digital/src/app/dash/open-compute-inference/page.tsx`. Expect four configured endpoints and the existing public placeholder.
- **Unresolved decisions:** v0.5 destination (current repository recommended; PRD sibling folder remains an option). Later output-target, score-reference eligibility, and qualification-label details are recorded in the audit and do not block migration.
- **Owner feedback / approval:** user requested PRD review and guided building, and reserved all commits/pushes. Workspace clarification requested; no Stage 1 approval received.
- **Approved next increment:** none. Proposed next increment: Stage 1 source migration and offline baseline verification only.

The pause follows PRD Section 17: “Ali approves the audit, migration plan, and the next increment.” The PRD explicitly starts with Stage 0 only. Passing checks do not approve the next increment.
