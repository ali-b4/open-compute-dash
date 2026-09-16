# Provider Qualification Lab v0.5

This repository is the new working lab for Open Compute Inference. **Stage 2A adds the provider registry and offline selection.** The completed migration and legacy reader remain available. Standardized v0.5 benchmarks, APS-R2 scoring, and public exports come in later reviewed increments.

The original `../provider-eval-v0.1` lab and its saved results remain in place. The public dashboard will be built in the separate `baloch-digital` website.

## Start here — no accounts or API calls needed

Use Python 3.10 or newer. No package installation or `.env` file is needed for these commands. Run them from this repository's root.

```bash
python3 -B scripts/inspect_providers.py
```

Expect four enabled launch providers: Venice, Chutes, Darkbloom, and io.net. Access and capabilities are unverified; prices are historical references. This command reads configuration only. It neither loads keys nor contacts providers.

```bash
python3 -B scripts/inspect_providers.py --registry tests/fixtures/registry/five-providers.json
```

Expect a **synthetic** five-provider selection, including Example Lab, and a disabled Pearl placeholder excluded without a key requirement. This demonstrates extension through configuration, not working access to another provider.

To inspect a subset, add `--providers venice ionet`. This changes the displayed selection only; the registry and saved observations are unchanged. `--json` shows the full selection details.

For the current review checklist and exact expected results, see [Stage 2A review](docs/stage-2a-review.md).

```bash
python3 -B -m unittest discover -s tests -v -b
```

This runs the inherited offline tests plus the legacy-reader and registry checks. Provider requests are simulated; tests create temporary files, not real benchmark results.

```bash
python3 -B scripts/inspect_legacy.py tests/fixtures/legacy/summary.json
```

This reads a **synthetic example** of an old summary. It should identify the data as legacy, preserve a recorded zero cost, and show missing values as unavailable. The output is a local inspection, not a public export or an APS score.

The completed [Stage 1 review](docs/stage-1-review.md) also includes a saved-result example.

## Where things live

| Location | Purpose |
| --- | --- |
| `config/providers.json` | The provider registry for new v0.5 work: exact model IDs, endpoint configuration, secret-variable names, and evidence status. |
| `scripts/provider_registry.py`, `scripts/inspect_providers.py` | Offline registry validation and provider selection. They do not call an adapter or read credentials/pricing files. |
| Other `scripts/`, `providers/` | Inherited request, streaming, measurement, and report code, plus the offline legacy reader. |
| `tests/` | Original regression tests and frozen workloads; clearly synthetic reader/registry fixtures. |
| `config/lab.json` | Project/version metadata and the new registry location. It does not authorize a live run. |
| `config/pricing.json`, `config/qualification.json` | Historical configuration copied unchanged. It is not fresh evidence of current prices or capabilities. |
| `docs/migration-manifest.json` | Source commit, uncommitted-file inventory, and exact copied-file fingerprints. |
| `results/`, `exports/` | Private local output locations, excluded from Git. Neither contains copied historical data. |
| `docs/lab-progress.md`, `docs/decisions.md` | Current checkpoint, decisions, and owner approvals. |

The inherited frozen workload remains three providers and nine requests. v0.5's launch registry includes Venice, Chutes, Darkbloom, and io.net. Pearl is deferred and absent from that launch registry; its placeholder appears only in the extension test fixture.

**Integration boundary:** new v0.5 selection uses only `config/providers.json`. Inherited live commands still use the historical `scripts/provider_config.py`; adding a registry entry does not yet make it callable. Connecting the registry to request/adapter/pricing behavior is a separate reviewed increment. This preserves the old frozen workload and live defaults while the offline configuration is reviewed.

## Historical records and dependencies

`inspect_legacy.py` reads saved summaries or normalized observations without changing them. It uses their saved values, never current prices, and never prints prompts, response text, raw errors, or local record references. It preserves the old definition of throughput, which differs from the planned v0.5 definition.

Links inside the copied pricing/qualification configuration may refer to `notes/`, `results/`, `config/provider-catalogs/`, or `config/pricing-history/` in the **original v0.1 directory**. Those private artifacts were deliberately left there. A missing local evidence file does not mean the old measurement was reverified.

[requirements.txt](requirements.txt) records the dependency-free core. [requirements-token-audit.txt](requirements-token-audit.txt) lists optional packages for the inherited token investigation. That optional workflow also needs historical tokenizer assets and assumes records are inside its own lab directory; it is not part of this migration's demonstrated workflow. v0.5's pinned tokenizer is a later increment.

The inherited request, pricing-refresh, and benchmark commands can contact providers. Live use needs its own approved run and budget; use the offline commands above for this checkpoint. The inherited report renderer can write beside its input, so use the new reader when inspecting the preserved baseline.

Ali handles all commits and pushes. Each significant increment ends with a concrete review checklist before the next one starts.
