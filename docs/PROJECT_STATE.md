# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST)
**Product status:** Pre-production implementation and controlled UAT
**Verified shared-main baseline:** `73c428ea450d9bd17c51031187608c205e200ffd` (PR #185, 2026-09-05)
**Latest executable-change baseline:** 73c428e (PR #185)

PR #175 adopted Architecture Decision 0001 in documentation. It did not implement
the hybrid migration. This snapshot separates freshly checked source/Git/test
evidence from historical runtime evidence. All four maintained documents live
under `docs/`; root-level duplicates are not maintained.

## Verified progress and active work

PR #185 merged the optional visual/report journal lifecycle into shared main.
[Exact main CI 33941884582](https://github.com/Slayde91/classifire/actions/runs/33941884582)
succeeded on `73c428e`: 974 tests passed with 141 warnings, plus the workflow's
static and migration checks. This is synthetic/CI evidence, not production proof.
Managed inference still lacks an authenticated production capture producer.

An unfinished ProjectPackage candidate exists in
`C:\CLASSIFIRE\.tmp\project-package-draft-20260905`, branch
`feat/project-package-draft-20260905`, based on `73c428e`. Its three files are
untracked: `docs/PROJECT_PACKAGE_V1_CONTRACT.md`,
`src/classifire/services/project_package.py`, and `tests/test_project_package.py`.
The existing synthetic package suite was rerun during this documentation review:
**22 passed**. No candidate static checks, full regression or publication are
claimed. A passing archive fixture does not prove complete database extraction,
export permissions, persistence, download, import or a usable package interface.

The highest-value next task is to review, finish and publish this bounded Draft
contract/exporter candidate, preserving existing work. First resolve membership
and authorization contracts; then prove validation, determinism and safe refusal.

## 1. Project health and publication

| Area | Verified state | Meaning |
| --- | --- | --- |
| Shared main | PR #185 merged as 73c428e; consumer, journal and optional lifecycle hooks are implemented. | Hybrid is accepted, not a completed runtime migration. |
| Hosted CI | [Main run 33941884582](https://github.com/Slayde91/classifire/actions/runs/33941884582) succeeded on exactly `73c428e`. | Source/test/static/migration evidence, not production or real-UAT proof. |
| Local synthetic verification | 22 existing Draft-package tests passed in the separate untracked candidate; main CI passed 974 tests. | Existing contracts have a passing baseline; full migration parity is not proven. |
| Migration history | One Alembic head: `0026_single_active_technical_release` on `legacy_adjudicated_lineage`. | Preserve forward-only history. |
| Branch governance | Detailed protection/rules APIs previously returned HTTP 403; basic main metadata reports protected=false and no enforced checks. CODEOWNERS names Slayde91. | Normal PR #176 merge was accepted after policy evidence; never bypass failed checks or required review. |
| Open work | Issues #42 (retained Phase 8 tooling reconciliation) and #43 (OpenClaw development dependency advisories); draft PRs #9-#13 on legacy feature-to-feature bases. | Reconcile issue contents against source; do not bulk-merge the draft stack. |
| Operational health | No new runtime/database/provider verification. | Deployment, recovery, production tenancy, real project acceptance and release remain unproven. |

### Local change classification

The protected root `C:\CLASSIFIRE` was inspected read-only on
`gpt/phase8-linked-original-images` at `de0cc5a`, with
`CHERRY_PICK_HEAD=c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`.
Four unresolved deleted/updated paths remain: the
`phase8_linked_visual_run.py` and `phase8_visual_evidence.py` services and their
two tests. Staged additions, unstaged code/configuration/plugin/UI/test changes,
and untracked material are pre-existing recovery evidence. Protected pytest
directories prevent a complete untracked inventory. None belongs to this change.

Documentation-only branch: `docs/package-target-handoff-20260905` in
`C:\CLASSIFIRE\.tmp\docs-package-target-handoff-20260905`, based on `73c428e`.
Only the four maintained documents belong to this change. The package candidate's
three untracked files are separate unfinished implementation and remain untouched.
PR #185's lifecycle implementation is already merged; do not redo it.

## 2. Implemented foundations

| Component | Implemented scope | Evidence entry points |
| --- | --- | --- |
| Application | FastAPI, CLI, development UI, SQLAlchemy, audit/security and migrations | `src/classifire/api/`, `models.py`, `ui.py`, `migrations/` |
| Evidence | Project/Estimate ownership, exact retained-byte reads, quarantine, PDF and bounded XLSX/DOCX locators, approved labels and report families | `services/project_evidence.py`, `report_evidence_adapter.py`, `report_expected_label_manifest.py` |
| Physical governance | Distinct defects/openings/services/links, blank-opening semantics, guards, signed admissions, initial submission, amendments and separate signed replacement-lock execution | `services/adjudicated_physical_submission.py`, `signed_physical_model_lock_amendment_execution.py`, `signed_physical_model_lock_replacement_execution.py` |
| Proposal assessment | CLASSIFIRE controls blind inventory, Physical proposal, Validator, bounded correction and protected-state checks; single/family runners are service-only | `services/phase8_report_assessment_controller.py`, `phase8_report_assessment_runner.py` |
| OpenClaw | Fresh sessions, provider/model binding, literal-loopback transport, no-tool attestation, post-call audit and safe errors | `services/phase8_openresponses_transport.py`, `phase8_report_openresponses_transport.py`, `phase8_visual_runtime.py` |
| Controlled writes | Default plugin profile exposes only admission-bound initial submission; broader catalog entries do not prove live capability | `openclaw-plugin-classifire-controlled-write/src/index.ts`, `src/classifire/api/agent_api.py` |
| Proposal review | Retained review metadata, five-year retention, redaction, legal hold, scoped readers and immutable administrator annotations | `services/proposal_review_package.py` and lifecycle/security tests |
| Technical libraries | Source-bound Draft/revision/review/activation; current-authority checks; release lineage; atomic eligible-set publication and one-active-release constraint | `services/technical_release_publication.py`, migration `0026` and technical tests |
| Outputs | Basic calculation, PDF/XLSX, proposal-only desk quotes; snapshot V2 semantic/document integrity with V1 verification | `services/calculation.py`, `desk_quote.py`, `snapshot.py`, `api/router.py` |
| Background work | BackgroundJob and polling shell; generic queued jobs still have no handlers. Merged journal uses separate non-queued states; PR #185 adds optional transport lifecycle hooks | `models.py`, `worker.py` |

Abbreviated filenames in the last column use the directory of the preceding
path in that row. Source paths are under `src/classifire/` unless explicitly
rooted elsewhere. These are bounded capabilities, not a complete product.
Technical-library publication is not project technical selection; annotations
are not approval; a passed proposal is not canonical physical truth.

## 3. Accepted target and known gaps

[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md)
accepts a deterministic core with bounded optional AI. ChatGPT and standalone
clients will share authenticated application services. Database and retained
storage remain live truth; ProjectPackage will be a versioned interchange
contract and immutable exported revision. Imports never activate foreign
approvals, locks or release authority.

| Gap | Current boundary |
| --- | --- |
| Hybrid execution | Journal and optional visual/report lifecycle integration are merged. Full stage coordination, real producer assurance, remote cancellation and retirement remain incomplete. |
| Project package | No shared-main ProjectPackage contract, whole-project export/download or quarantined import. The local Draft archive candidate is unmerged. Existing review packages and PDF/XLSX exports are narrower. |
| Interfaces | No production MCP integration or standalone package workflow. Existing UI cannot invoke the report runner. |
| Physical acceptance | Historical records report no accepted replacement physical model/active lock for the UAT estimate; not rechecked against a live database here. |
| Technical/commercial | Extraction-assisted/manufacturer-neutral lineage, clean-machine recovery, system-derived quantities/productivity and full recovery ledger remain incomplete. |
| Validation/release | Snapshot integrity exists; full independently validated technical/commercial output and Human Release remain unproven. |
| Operations | Provider privacy/egress, tenancy, backup/restore, deployment, monitoring and performance/cost evidence remain required. |

## 4. Historical controlled-UAT evidence

The prior documented 2026-09-01 proposal-only attempt failed at `blind_inventory`:
`VISUAL_PROPOSAL_FAILED` /
`INFERENCE_PORT_FAILED: blind_inventory: Phase8OpenResponsesTransportError`.
Human comparison was `NOT_RUN`; the recorded outcome was rollback-only with no
controller/runner canonical write or Physical Model Lock.

Historical completion receipt:
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.

This reconciliation did not reopen that receipt or UAT database. Its underlying
transport reason remains unresolved; later safe-code propagation cannot recover
it retroactively. No repeat report/provider run is authorised by this snapshot.

## 5. Roadmap position and active work

- Phases 0-7 and 15 have implemented foundations with incomplete exits.
- Phase 3 contract inventory/tests and completion consumer/journal/lifecycle
  hooks are merged; full runtime migration is incomplete.
  Production capture remains unproven. Draft package work is reordered next.
- Phase 8 remains blocked on fresh authority, evidence review, semantic approval
  and separately governed canonical/replacement-lock gates.
- Phases 9-14 remain dependency-blocked; package portability does not bypass them.
- Phase 8C is planned/gated; Phase 16 is deferred.
- A mandatory autonomous fleet is superseded as the target. OpenClaw remains
  required for the current bounded inference path until replacement parity.

See the [roadmap](./CLASSIFIRE_ROADMAP.md) for phase-specific acceptance criteria.

## 6. Recommended Next Actions

1. **Finish and publish the existing Draft ProjectPackage v1 candidate.**
   Inventory complete membership, ownership and export rights; define shared
   schema/semantic validation and deterministic archive generation. Preserve
   evidence hashes, explicit unresolved stages, revision lineage and authority
   status. Do not relabel a proposal-review package as a complete project.
   [Start Here / Next Session](./SESSION_HANDOFF.md#start-here--next-session)
   gives inputs, prerequisites and completion criteria.
2. **Add governed database projection and storage/download, then import and clients.**
   Prove permissions, immutable revisions, exact archive integrity and safe new-
   project import before UI/ChatGPT adapters. Keep business logic in shared services.
3. **Resolve production AI assurance separately.**
   Authenticate actual capture/terminal evidence, privacy and recovery before
   managed wiring or OpenClaw retirement. Packages remain available without AI.

Technical-library and operational follow-ups remain separately scoped backlog.
Maintain full CI. Do not expand the Draft package slice into Phase 2/12, real UAT,
production provider wiring or a general agent platform.

## 7. Verification and limits

This documentation review verified remote main `73c428e`, PR #185 main CI success
(974 tests, 141 warnings), source lifecycle hooks, snapshot recalculation,
local branch/file state, and open issues/PRs. The separate package candidate's
22 existing synthetic tests passed with worktree-local imports and temporary
storage. Its implementation was not changed or fully qualified.

No live database, customer evidence, provider, canonical write, lock, deployment
or release was exercised. Historical UAT records remain explicitly unrefreshed.
Documentation validation checks headings, local links, consistent baseline,
next-task wording and whitespace; publication evidence lives in Git/PR/CI.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md).
