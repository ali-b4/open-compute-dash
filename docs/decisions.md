# Lab decisions

Date opened: 2026-09-16. No owner approval is inferred from a proposed entry.

| ID | Status / source | Decision and rationale | Affected version or stage |
| --- | --- | --- | --- |
| D001 | Owner instruction, current session | Ali handles commits and pushes. Do not perform them without an explicit request; no Git write action is part of the current proposal. | All stages; no schema effect. |
| D002 | PRD §§4, 17, 20 | Follow the guided checkpoints. Complete Stage 0 and obtain review before migration; later significant increments receive their own reviews. | All stages; no schema effect. |
| D003 | Selected requirement, PRD §§2, 6 | Launch cohort is Venice, Chutes, Darkbloom, and io.net for one Qwen model family. Pearl is deferred, absent from launch scores, and not a blocker. New providers use configuration and reviewed onboarding. | v0.5 registry / future collection manifests. |
| D004 | Selected requirement, PRD §11 | Implement APS-R2: geometric performance/cost base, workload success fraction squared, softened cost normalization, and 20/40/20/20 outer workload weights. Implementation remains a later checkpoint. | `scoring_version=aps-r2`; Stage 5. |
| D005 | Proposed; owner destination choice pending | Use existing `open-compute-dash` for the new Python lab; keep frontend in `baloch-digital`. It already has its own repository and is separate from v0.1. Alternative: proposed sibling `provider-eval-v0.5`. No remotes change. | Stage 1; no measurement change. |
| D006 | Proposed migration safeguard | Preserve the actual v0.1 working files, not just HEAD `00875118f71d40cce7d59a95ea4488173ed5c3f8`: audited baseline has 14 tracked modifications and untracked work. Copy selected source/config/tests; keep original private records and secrets in place. | Stage 1 source provenance; legacy records unchanged. |
| D007 | Proposed integration location | Reviewed public artifacts go under website `public/dash/open-compute-inference/data/<collection-id>/`, with a selected-collection manifest. Private data and synthetic fixtures stay outside `public`. | Stage 6 export/import contract; schema version to be assigned there. |
| D008 | Pending, before Stage 3 approval | Record the intended visible-answer length separately from the 512-token maximum; the pilot validates length comparability. | Workload/methodology version to be assigned. |
| D009 | Proposed, confirm at Stage 5 | Decide normalization eligibility per workload using complete comparable performance/cost evidence. Missing other workloads prevent overall APS but need not remove valid workload evidence. | APS-R2 reference-pool implementation; no equation change. |
| D010 | Proposed, confirm at Stage 6 | Distinguish unmeasured work shapes (`insufficient_evidence`) from verified inability (`technically_incompatible`). | Qualification specification version to be assigned. |

No new schema or methodology version has been implemented. Historical observations retain their existing definitions. Spend caps, live runs, final design, data publication, and deployment remain unapproved.
