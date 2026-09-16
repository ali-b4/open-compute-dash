# Stage 0 review — Provider Qualification Lab v0.5

Date: 2026-09-16. Status: **approved by owner** after review and commit `e3d04ff212cbe141d66f47e6b399802a4e6c9b7c`.

The findings and proposal below record the Stage 0 checkpoint. The owner approved proceeding with Stage 1 in this repository; see [current progress](lab-progress.md).

The existing lab is a usable starting point: all 41 offline tests pass. The website already has the required public route and passes its 11 tests, type check, and lint check. The next increment is a careful migration of the lab; new benchmark behavior comes after that review.

This checkpoint follows PRD Sections 17 and 20: inspect the existing work, propose the migration, and stop before Stage 1. Only these review documents were created. No application code, baseline files, website files, Git history, or remotes were changed.

## 1. Workspaces and preservation

| Workspace | Recorded HEAD | Observed state |
| --- | --- | --- |
| Current `open-compute-dash` | `00a3e7e85efbc9cb54aed3e609fde863e66413f9` | Clean before this audit; only `.gitignore` tracked. The local PRD is explicitly ignored. Existing origin: `ali-b4/open-compute-dash`. |
| Existing `../provider-eval-v0.1` | `00875118f71d40cce7d59a95ea4488173ed5c3f8` | 14 tracked files modified, plus untracked source, tests, notes, configuration, and results. Existing origin: `ali-b4/provider-eval-v0.1`. |
| Website `/Users/ali/Documents/baloch-digital` | `3b336adbe841ab12666c9c362b5e74361ec96bf1` | Clean before and after audit. Existing origin: `ali-b4/baloch-digital`. |
| PRD's proposed `../provider-eval-v0.5` | None | Directory does not yet exist. |

The v0.1 working files contain work beyond its last commit. Copying only that commit would omit working features and tests. Stage 1 must record and preserve the actual local source state as well as the commit identifier. Do not reset, stash, overwrite, or clean that repository.

Modified tracked baseline files: `README.md`, `config/pricing.json`, `notes/metrics.md`, all five files in `providers/`, `scripts/manual_request.py`, `scripts/measurements.py`, `scripts/render_report.py`, `scripts/run_benchmark.py`, `tests/basic_chat.json`, and `tests/test_measurements.py`. Untracked work includes pricing refresh, token accounting, qualification, associated tests, and saved results.

**Proposed location, pending owner choice:** use this existing `open-compute-dash` repository for the v0.5 Python lab and its review records. Keep the public frontend in `baloch-digital`. This meets the requirement for a codebase separate from v0.1 and avoids creating another repository. If the owner prefers the PRD's sibling directory, use that instead after the migration plan is approved.

Ali owns commits and pushes. This plan needs no Git write operations or remote changes by the implementation agent. The ignored PRD remains untouched; these tracked-ready review documents record the implementation decisions without changing the owner's ignore rule.

## 2. What is already built

The intended flow remains:

```text
Local Python lab -> provider requests -> private observations
                    -> offline statistics, APS and qualification
                    -> reviewed public export -> existing website
```

The website displays saved results; it does not run paid tests.

| Existing lab area | Starting point | Reuse / required change |
| --- | --- | --- |
| Endpoint configuration | `scripts/provider_config.py`, `providers/` | Four provider integrations exist. Extend metadata and activation through a registry later. |
| Individual requests | `scripts/manual_request.py`, `scripts/raw_request.py` | Reuse request construction and saved evidence; preserve provider-specific behavior. |
| Streams and measurements | `scripts/streaming.py`, `scripts/measurements.py` | Reuse parsing/accounting helpers, but version the new timing and success definitions. |
| Repeated execution | `scripts/run_benchmark.py` | Existing sequential frozen comparison; not yet the v0.5 repeated/concurrent runner. |
| Pricing and investigation | `config/pricing.json`, `scripts/refresh_pricing.py`, `scripts/audit_tokens.py` | Reuse provider-specific accounting; historical prices require revalidation before paid work. |
| Reports and qualification | `scripts/render_report.py`, `scripts/qualify_providers.py`, `config/qualification.json` | Preserve historical interpretation; v0.5 statistics, APS, qualification rules, and public export are later increments. |
| Offline regression tests | `tests/test_*.py` | 41 tests pass without live calls. Keep them passing through migration. |

The present frozen default is **three providers, three prompts each: nine requests**. io.net still exists in the registry and manual runner. The v0.5 launch decision remains four providers; do not infer its cohort from the old default workload.

### Configured endpoint IDs

Confirmed in local `scripts/provider_config.py`; these are configured values, not a fresh verification of provider availability or access.

| Provider | Internal ID | Configured request model ID | Secret variable name |
| --- | --- | --- | --- |
| Venice | `venice` | `qwen-3-8-27b` | `VENICE_API_KEY` |
| Chutes | `chutes` | `Qwen/Qwen3.8-27B-TEE` | `CHUTES_API_KEY` |
| Darkbloom | `darkbloom` | `EigenLabs/Qwen3.8-27B-4bit-mtp` | `DARKBLOOM_API_KEY` |
| io.net | `ionet` | `Qwen/Qwen3.8-27B` | `IONET_API_KEY` |

Canonical family: `qwen/qwen3.8-27b`. Pearl remains deferred and outside launch measurements and scores. Secret values were not opened or checked.

### Measurement and data gaps

- The old throughput estimate uses provider completion tokens over the reasoning/answer delivery interval. v0.5 requires locally counted visible-answer tokens and a different interval. Keep the old metric's meaning intact.
- The existing lab can report API success for reasoning-only output. v0.5 requires a verified terminal response and the requested answer type, with measurement completeness assessed separately.
- The old default uses a 2,048-token output cap and short prompts. These observations cannot be relabeled as the new standardized APS workloads.
- Four saved summary files were inspected for structural metadata only: their observation counts are 16, 16, 9, and 9. They contain local record references and error fields; they are not public exports.
- Some older summary rows lack `finish_reason`. The current report fallback can also recalculate missing metrics using today's pricing file. The legacy reader must tolerate older fields and preserve recorded costs; missing historical pricing must stay unknown.
- Baseline ignore rules protect `.env` and caches but do not exclude private results and accounting artifacts. Establish the new lab's private-data boundaries before copying anything. Leave original historical records in place.

Normal benchmark operation uses Python's standard library. The optional token-audit tool uses `tokenizers` and `jinja2`; no dependency declaration currently records that distinction. Stage 1 should document it without installing unnecessary packages.

## 3. Website integration

The page exists at `src/app/dash/open-compute-inference/page.tsx`. The entry registry, `src/app/data/entries.ts`, explicitly marks it public. No access-control change is needed.

Reuse the existing `SiteHeader`, `RouteTransition`, inherited footer, design tokens, and metadata conventions. The current placeholder's shared content column is limited to 42rem; a wider comparison view should use route-local styling instead of widening unrelated pages. Follow the site's bone/sage palette, Space Mono type, square controls, hairline rules, and reduced-motion behavior.

The website's `AGENTS.md` requires reading the installed Next.js guides before writing code. They are available locally. The audit also reviewed `DESIGN.md`, `PRODUCT.md`, and README guidance. Installed project versions are Next.js 16.3.2, React 19.2.8, TypeScript, and Tailwind 4.

**Proposed reviewed-data destination:**

```text
baloch-digital/public/dash/open-compute-inference/data/
  current.json                       # selects an approved collection and hashes
  <collection-id>/dashboard.json
  <collection-id>/requests.csv
  <collection-id>/methodology.json
  <collection-id>/checksums.json
```

Everything under `public` is downloadable. Only approved, allowlisted exports belong here; private records and synthetic development fixtures stay outside it. Finalize validation, atomic selection, and rollback behavior at Stage 6 before implementing an importer.

The Figma reference points to file `TGTbe9V00KKQ9SAUX7u8Dt`, node `6:5`. A read-only screenshot request failed because the connector requires edit access. No design was inspected or changed. Resolve access at Stage 7; it does not block the lab migration.

## 4. PRD review and decisions still ahead

APS-R2, the four-provider cohort, deferred Pearl, one model family, and the 20/40/20/20 workload weights are settled requirements. No scoring redesign is proposed.

Independent arithmetic checks match the PRD: 1,600 release attempts, 44.8 million input tokens, and up to 819,200 output tokens before overhead and diagnostics. Component and workload weights each sum to one. The provided reliability, weak-throughput, and zero-price examples agree with the equations.

Three implementation details should be resolved at their relevant checkpoints:

| Checkpoint | Open detail | Proposed resolution — not yet approved |
| --- | --- | --- |
| Stage 3 | A 512-token cap is specified, but the length-coverage gate refers to an approved output target. | Explicitly record the visible-output target and check it in the pilot; do not assume the cap guarantees that length. |
| Stage 5 | Which endpoints may set normalization baselines when some evidence is missing? | Determine eligibility per workload using complete comparable performance/cost evidence. An unresolved other workload blocks overall APS without automatically discarding this workload's evidence. |
| Stage 6 | “Unsupported work shapes” could mean either unmeasured or proven incompatible. | Use `insufficient_evidence` for unmeasured shapes and `technically_incompatible` for verified technical inability. |

The Section 19 operational defaults remain proposals until their stated checkpoints: output/reasoning/tokenizer at Stages 2–3; pilot, samples, caching, deadlines, and collection window at Stage 4; qualification thresholds at Stage 6; design/staleness at Stages 7–8. No spending allowance or publication approval is inferred.

## 5. Verification and limits

| Check actually run | Result |
| --- | --- |
| Baseline `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v` | 41 passed. Tests inspected first; mocked requests and temporary directories only. |
| Website Node test suite | 11 passed. |
| Website TypeScript check with `--noEmit --incremental false` | Passed. |
| Website ESLint | Passed. |
| PRD arithmetic check | Counts, weights, and supplied scoring examples agree. |
| Repository state after checks | Website remains clean; baseline changes preserved. |
| Figma screenshot access | Unavailable; connector requests edit access. |

No dependency installation, production build, browser interaction test, provider catalog fetch, live inference, pricing verification, credential validation, or deployment was performed. Existing unit tests support the migration starting point; they do not establish current provider availability or v0.5 correctness.

## 6. Proposed Stage 1 increment

**Purpose:** create a working v0.5 starting point while preserving the existing experiment and its meaning.

1. Use the owner-approved destination. Inventory and fingerprint the selected current v0.1 source/config/test files, including relevant uncommitted files; record their baseline commit and local modifications.
2. Copy that reviewed material into the new lab. Exclude `.git`, real secrets, caches, raw results, pricing-history archives, and private accounting/review artifacts. Preserve those originals where they are. Copy `.env.example` only after verifying it contains placeholders.
3. Add a dependency declaration, setup instructions, private-output ignore rules, and explicit version metadata. Keep historical workload/model controls unchanged in the legacy path; no new request behavior or APS implementation in this increment.
4. Keep the existing record-reading path working. Demonstrate interpretation of one local saved legacy record without rewriting it or presenting it as APS data; use a clearly synthetic fixture for repeatable tests.
5. Run the inherited offline tests in the new location, verify the baseline remains unchanged, explain the resulting files, and stop for review before Stage 2.

**Expected result:** a runnable separate lab with the old offline tests passing and historical records still understandable. No paid requests, website changes, commits, pushes, or deployment are needed.

**Owner inspection now:** open the baseline `scripts/provider_config.py` and the website `src/app/dash/open-compute-inference/page.tsx`. You should see the four endpoint IDs in the first file and the existing placeholder in the second. This shows where measurements originate and where their reviewed results will appear.

**Review requested:** confirm the lab destination and approve or revise this migration increment. Stage 1 has not started.
