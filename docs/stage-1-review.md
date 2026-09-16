# Stage 1 review — the lab has moved safely

Date: 2026-09-16. Status: **approved by owner** with “done, proceed,” after commit `ac22936`. All checks below record the completed Stage 1 checkpoint.

The new working lab is in `open-compute-dash`. We copied **35 files from the current v0.1 working directory**, including its uncommitted improvements, without changing their contents. The original lab and its saved results remain in place. The new reader lets you inspect those results offline while keeping their original meaning.

## Exactly what to review

1. **Open [README.md](../README.md), especially “Where things live.”** Check that the separation is clear: this repository runs the lab; `baloch-digital` will display approved results; the old lab retains historical evidence. You do not need to review all 35 copied files line by line.
2. **Run the synthetic example below.** Check that it is visibly labeled synthetic and legacy, a recorded zero cost stays zero, and a missing cost says “Unavailable.” This is the new behavior to inspect in this increment.
3. **Open [config/lab.json](../config/lab.json).** Check that it says `migration_only`, preserves the legacy workload version `0.1`, and lists no implemented scoring versions. `aps-r2` is the planned next scoring method, not a score already calculated.

Run this from the repository root:

```bash
python3 -B scripts/inspect_legacy.py tests/fixtures/legacy/summary.json
```

Expected: two saved synthetic observations, one API success and one API failure. Chutes has a saved cost of zero; Venice has an unavailable cost. Missing finish reasons remain unavailable. These invented figures are only an example for checking the reader.

**Optional: inspect your real saved result without changing it:**

```bash
python3 -B scripts/inspect_legacy.py ../provider-eval-v0.1/results/summary/20260915T145335Z-cbd77e7c/summary.json
```

Expected: **9 saved observations, 9 legacy API successes**, from Chutes, Darkbloom, and Venice. API success does not guarantee a final answer. The command reads existing measurements; it does not call providers, calculate APS, or update the original file. Those timing/cost values were checked against the saved summary during migration.

## What changed

| Files | Change and purpose |
| --- | --- |
| `scripts/`, `providers/`, original `tests/`, two historical config files, `.env.example` | 35 source/config/test files copied byte-for-byte from the actual working baseline. Provider behavior and frozen workload controls remain as they were. |
| `scripts/inspect_legacy.py` | New read-only inspection of old summaries and normalized records. Preserves saved values; missing values stay unavailable. Current pricing is never used to fill gaps. |
| `tests/test_legacy_reader.py`, `tests/fixtures/legacy/` | New offline checks and conspicuously synthetic examples, including old records without finish reasons and privacy exclusions. |
| `README.md`, `requirements*.txt`, `config/lab.json` | Setup, dependencies, and explicit project/version metadata. Core operation and tests need no installed packages. |
| `.gitignore` | Keeps credentials, raw results, pricing/catalog archives, and draft exports out of Git. The placeholder `.env.example` remains trackable. |
| `docs/migration-manifest.json` | Records exactly where the copied source came from and its file fingerprints. |
| `docs/lab-progress.md`, `docs/decisions.md` | Records the owner's Stage 0 approval, this increment, and the next review boundary. |

A file fingerprint is a compact check of its contents. Matching fingerprints prove that the copied files match the source; they do not certify the correctness of the older measurement definitions.

The new project metadata is descriptive. It does not add budget controls to inherited live commands. Those commands remain outside this checkpoint's authorized offline work.

## Verification

| Check | Result |
| --- | --- |
| Full offline test suite on Python 3.14.5 | **50 passed:** 41 inherited tests and 9 new reader tests. |
| Exact copied-file comparison | **35 of 35** match their recorded source fingerprints. |
| Baseline preservation | All **281 fingerprinted baseline files**, including historical evidence, unchanged. Original Git commit and working-tree status unchanged. Secrets, caches, and Git internals were excluded from content fingerprinting. |
| Synthetic reader demonstration | Two observations; zero cost and unavailable cost remain distinct; synthetic/legacy labels visible. |
| Actual saved-summary demonstration | Nine observations read; saved timing, throughput, and cost values preserved; source file unchanged. |
| Private-output boundary | No `.env`, raw results, draft exports, catalogs, or pricing-history archive copied. Ignore rules checked; `.env.example` remains trackable. |
| Website | Working tree remains clean; no website files changed. |
| Independent code review | No actionable correctness or scope issues found in the new reader/configuration. |

To rerun the offline tests:

```bash
python3 -B -m unittest discover -s tests -v -b
```

Expected final result: `Ran 50 tests` followed by `OK`. The `-b` option hides the simulated request logs from passing tests, so the final test summary is easier to read. These tests use simulated provider responses and temporary files.

Optional token-audit packages and their historical tokenizer assets were not installed or exercised. Saved prices/capabilities were not reverified. No v0.5 benchmark methodology, APS calculation, website implementation, paid run, or publication was added.

## Your decision at this checkpoint

Approve the migrated structure and the legacy-reader behavior, or identify what you want changed. You do not need to judge the old numerical results as a provider ranking.

**Proposed next increment: Stage 2A — offline provider registry.** Make the four-provider configuration explicit and extensible, including activation state, model IDs, secret-variable names, and evidence status. Demonstrate an additional fictional provider through offline tests and keep Pearl excluded. Live smoke tests and fresh pricing/access checks will require a separate bounded plan and approval.

The review stop comes from PRD Sections 4 and 17: Stage 1 requires owner review of the migration and file structure before new endpoint behavior is introduced. Commits and pushes remain the owner's responsibility.
