# Lab progress

## Stage 2A / offline provider registry

- **Status:** awaiting_review
- **What changed:** added one versioned registry for new v0.5 planning, an offline selector, and a clearly synthetic provider-extension example. Inherited live commands retain their frozen configuration until the adapter increment.
- **How to inspect it:** follow [Stage 2A's exact review checklist](stage-2a-review.md): launch selection, synthetic extension/exclusion example, then subset selection and one registry entry.
- **Tests and evidence:** all 59 tests pass. The demonstrations select 4, 5, and 2 providers. Guarded tests confirm no credential lookup, extra file reads, network, writes, or adapter imports. All 35 inherited files still match migration fingerprints in both workspaces; website remains clean.
- **Owner exercise:** run `python3 -B scripts/inspect_providers.py` (expect 4), then use `--registry tests/fixtures/registry/five-providers.json` (expect synthetic label, 5 selected, Pearl excluded without a key), then `--providers venice ionet` (expect 2).
- **Unresolved decisions:** live access, reasoning controls, capabilities, and fresh pricing still need their later checks.
- **Owner feedback / approval:** “done, proceed” approved the completed Stage 1 checkpoint and its proposed Stage 2A. Owner's latest commit is `ac22936` (`env + stage 1 testing`).
- **Approved next increment:** none beyond the implemented Stage 2A scope. Proposed next: Stage 2B shared-adapter integration with simulated requests and explicit pricing dispatch. No live calls are included in that proposal.

## Stage 1 / preserve the baseline and migrate the lab

- **Status:** approved
- **What changed:** migrated 35 current baseline source/config/test files byte-for-byte into this repository; added setup/dependency declarations, version metadata, private-output ignore rules, source fingerprints, and an offline legacy reader. The public dashboard remains in `baloch-digital`.
- **How to inspect it:** follow [Stage 1's exact review checklist](stage-1-review.md): README folder map, synthetic reader command, and `config/lab.json`.
- **Tests and evidence:** all 50 offline tests pass (41 inherited, 9 new). All 35 copies match. All 281 fingerprinted baseline files and its Git state remain unchanged. A saved nine-observation summary retains its original measurements. Website remains clean. No live calls or installs.
- **Owner exercise:** run `python3 -B scripts/inspect_legacy.py tests/fixtures/legacy/summary.json`. Expect a synthetic/legacy label, two observations, one API success, one failure, a zero cost, and an unavailable cost. Optional real-data example is in the review checklist.
- **Unresolved decisions:** later methodology and export choices remain at their named checkpoints.
- **Owner feedback / approval:** “reviewed and committed, proceed. remember to tell me exactly what you want me to review each time.” Stage 0 was committed by the owner as `e3d04ff212cbe141d66f47e6b399802a4e6c9b7c`.
- **Approved next increment:** Stage 2A offline provider registry and fictional-provider tests, following owner's “done, proceed.” Live smoke tests, spending, and the website remain outside that approval.

## Stage 0 / audit and migration proposal

- **Status:** approved
- **What changed:** added the [audit and concrete Stage 1 proposal](stage-0-audit.md) and [decision register](decisions.md). Existing lab and website code are unchanged.
- **How to inspect it:** read the audit's workspace map, reusable-code table, and proposed Stage 1 increment.
- **Tests and evidence:** 41 baseline offline tests and 11 website tests passed; website type check and lint passed. Baseline local edits preserved; website remains clean. Figma screenshot access failed. No live provider calls, builds, or deployment.
- **Owner exercise:** compare `../provider-eval-v0.1/scripts/provider_config.py` with `/Users/ali/Documents/baloch-digital/src/app/dash/open-compute-inference/page.tsx`. Expect four configured endpoints and the existing public placeholder.
- **Unresolved decisions:** destination resolved by approval of the proposed increment in this repository. Later output-target, score-reference eligibility, and qualification-label details remain at their relevant checkpoints.
- **Owner feedback / approval:** owner reviewed, committed, and instructed “proceed”; requested exact review instructions at every checkpoint.
- **Approved next increment:** Stage 1 source migration and offline baseline verification only.

The pause follows PRD Section 17: “Ali approves the audit, migration plan, and the next increment.” The PRD explicitly starts with Stage 0 only. Passing checks do not approve the next increment.
