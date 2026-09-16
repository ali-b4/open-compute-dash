# Stage 2A review — provider configuration and offline selection

Date: 2026-09-16. Status: **awaiting owner review**. All checks below passed.

There is now one provider registry for new v0.5 work. It records the four launch endpoints, their exact model IDs, the names of their key variables, and what still needs verification. Another compatible endpoint can be added to offline selection through configuration.

**Configured does not mean verified.** This increment does not test API access, refresh prices, or send requests. Existing live commands retain their historical configuration until the separate adapter increment.

## Exactly what to review

Run these commands from the repository root. No API keys are needed.

**1. Review the launch selection.**

```bash
python3 -B scripts/inspect_providers.py
```

Expect **4 selected providers**: Venice, Chutes, Darkbloom, and io.net. Each should show unverified access and capabilities, plus historical/unverified pricing. Pearl should not appear. Confirm those are the launch providers you expect.

**2. Check that configuration can add a provider while excluding a deferred one.**

```bash
python3 -B scripts/inspect_providers.py --registry tests/fixtures/registry/five-providers.json
```

Expect a prominent **SYNTHETIC TEST REGISTRY** label and **5 selected providers**, including “Example Lab (synthetic).” Pearl appears only as excluded, with `access_pending` status. The key-variable list must contain no `PEARL_API_KEY`. This fixture does not create a real account or integration.

**3. Try a smaller selection and inspect one entry.**

```bash
python3 -B scripts/inspect_providers.py --providers venice ionet
```

Expect **2 selected providers**, Venice then io.net. Open the first entry in [config/providers.json](../config/providers.json). Check that the display name, exact model ID, and key-variable **name** are understandable. The unknown capability fields are intentional; no secret values belong in this file. The command does not edit the registry or saved results.

You do not need to review every repeated unknown field or the validation code line by line.

## What changed

| File | Purpose |
| --- | --- |
| `config/providers.json` | Four enabled endpoints with their configured identities, adapter type, secret-variable names, capability evidence, and historical pricing references. |
| `scripts/provider_registry.py` | Validates registry structure and builds selections. Counts and required variable names come from the selected entries. Disabled entries are excluded; unknown or disabled explicit selections fail clearly. |
| `scripts/inspect_providers.py` | Displays the selection without loading keys, contacting providers, or saving files. `--json` exposes the complete configuration summary. |
| `tests/fixtures/registry/five-providers.json` | Clearly synthetic extension example with a fictional endpoint and a minimal disabled Pearl placeholder. |
| `tests/test_provider_registry.py` | Offline validation, extension, exclusion, isolation, and regression checks. |
| `config/lab.json`, README, progress/decision logs | Records the current increment and explains the boundary between new configuration and inherited live commands. |

The registry distinguishes three things: selection (`enabled`), lifecycle (`verification_pending`, for example), and evidence (`unknown`, `configured`, `measured`, etc.). No current capability is presented as measured. TEE and 4bit-MTP labels come only from configured model names; actual serving behavior remains unverified.

Pricing entries point to the copied historical configuration. The inspector does not open that file or turn its old prices into a current quote. Its selection output is not an approved collection, schedule, spending reservation, or score snapshot.

## Verification

| Check | Result |
| --- | --- |
| Full offline test suite | **59 passed:** previous 50 tests plus 9 grouped registry tests. |
| Launch / synthetic / selected-subset demonstrations | **4 / 5 / 2** selected providers, respectively. |
| Deferred Pearl | Excluded; no key requirement, request, or score. Explicit selection rejects with an explanation. |
| Other configuration changes | Removing, disabling, or adding an arbitrary compatible entry changes selection without a named-provider code branch. |
| Offline isolation | Guarded tests reject any environment lookup, unexpected file read, adapter/service import, network use, or write. Registry loading and selection still pass. |
| Invalid inputs | Duplicate IDs/JSON fields, invalid flags/adapter/URLs, secret-value fields, unsupported selections, and inconsistent evidence rejected. |
| Independent review | One malformed-host validation gap found and fixed; regression cases added. No other actionable issues reported. |
| Historical behavior | All 35 inherited files still match their migration fingerprints in this repository and the original baseline. Existing tests pass. |
| Website / credentials | Website working tree remains clean. The local `.env` was not read or changed. |

`--json` output was also checked: it parses correctly and records `network_requests: 0` and `live_run_authorized: false`. Unknown and disabled explicit selections return a clean error with exit code 2, without a traceback.

To rerun the full offline suite:

```bash
python3 -B -m unittest discover -s tests -v -b
```

Expected final result: `Ran 59 tests` followed by `OK`.

This increment completes the configuration/selection portion of provider extension. Shared-adapter dispatch, collection/export handling, and eventual dashboard rendering remain separate acceptance steps. No provider access, balance, current capability, or price was checked, and no paid or catalog requests were sent.

## Your decision at this checkpoint

Approve the registry contents and demonstrated selection behavior, or identify what should change.

**Proposed next increment: Stage 2B — shared adapter integration with offline tests.** Connect the registry to request construction and provider-specific options, preserve exact launch payload behavior, and demonstrate a fictional endpoint through a simulated response. Unknown pricing formats must fail explicitly. This proposal includes no live calls; live access/price/smoke checks need a separate bounded plan.

The PRD requires a stop after each significant configuration/adapter increment. Commits and pushes remain the owner's responsibility.
