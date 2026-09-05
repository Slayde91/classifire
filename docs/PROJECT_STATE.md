# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST)
**Product status:** Pre-production implementation and controlled UAT
**Verified shared-main baseline:** `45b1f7f8196805854f7bd344eb57d7e5b737d9e9` (PR #180, 2026-09-05)
**Latest executable-change baseline:** `45b1f7f` (PR #180)

PR #175 adopted Architecture Decision 0001 in documentation. It did not implement
the hybrid migration. This snapshot separates freshly checked source/Git/test
evidence from historical runtime evidence. All four maintained documents live
under `docs/`; root-level duplicates are not maintained.

## Contract characterisation progress

PR #180 merged the socket deadline correction as 45b1f7f; exact main CI
[33935963213](https://github.com/Slayde91/classifire/actions/runs/33935963213)
passed. PR #179 uncertain-creation refusal remains intact.

**Current audit-page candidate (until merged):** reject any nextCursor field
and responses exceeding the requested 100-event limit with TOOL_AUDIT_INVALID.
Eleven new cases cover both endpoints and the valid 100-event terminal boundary.
Ten refusal cases failed before the fix; 131 focused/caller tests now pass
(114 contract/security plus 17 report/representative). Valid legacy empty-page
receipt hashes remain unchanged. No authority, migration or provider change.

**Newly verified limitation:** the installed OpenClaw 2026.7.1-2 package matches
the configured pin. Its audit.list supports the existing filters and optional
nextCursor; audit.activity.list is not registered in the inspected stock handler
catalog. The retained fallback request is compatible with the stock method's schema.
The writer is asynchronous, can drop queued metadata and can be disabled while
stored records remain readable. The list result provides no persistence barrier
or loss/coverage certificate. A terminal empty page is an observation of retained
records, not proof that no tool action occurred. The page fix does not close this
gap. See the [contract inventory](./OPENCLAW_CONTRACT_CHARACTERISATION.md) for
artifact hashes and exact limits. The transport can still return a proposal
after an empty page; complete coverage is not yet an enforced acceptance gate.

**Next bounded task:** establish a trusted execution/audit completion evidence
contract before using this audit as complete protection. Inspect existing
NoToolSessionAudit, transport acceptance, receipts and durable job abstractions;
define how terminal execution, durable event coverage, loss/disabled-writer state
and authority are proved. Separate historical observation receipts from new
acceptance evidence. Record implementation/migration impact before coding;
implement only a justified fail-closed boundary with synthetic ports. Do not
invent a Gateway field, use sleeps/repeated empty reads as proof, or remove
independent no-tool attestation. OpenClaw retirement/live completeness claims
remain blocked on this missing protection.

## 1. Project health and publication

| Area | Verified state | Meaning |
| --- | --- | --- |
| Shared main | PR #180 merged as `45b1f7f`, including socket deadline enforcement. | Hybrid is accepted, not a completed runtime migration. |
| Hosted CI | [Main run 33935963213](https://github.com/Slayde91/classifire/actions/runs/33935963213) succeeded on exactly `45b1f7f`. | Source/test/static/migration evidence, not production or real-UAT proof. |
| Local synthetic verification | 114 tests passed across the eight contract/security files in the handoff; the prior 70-test baseline remains historical evidence. | Existing contracts have a passing baseline; full migration parity is not proven. |
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

Current implementation branch: `fix/phase8-audit-contract-20260905`,
worktree `C:\CLASSIFIRE\.tmp\phase8-audit-contract-20260905`,
created cleanly from `45b1f7f` before editing. This candidate changes one runtime
service, its tests, the contract inventory and four continuity documents.
Verify its eventual commit/PR/merge in GitHub; the snapshot does not claim a
future publication result.

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
| Background work | BackgroundJob persistence and polling worker shell; no registered handlers, so queued jobs fail | `models.py`, `worker.py` |

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
| Hybrid execution | No complete durable job/run/stage coordinator, replacement adapter, cancellation/crash recovery or proven OpenClaw retirement. Extend existing abstractions first. |
| Project package | No complete ProjectPackage schema, whole-project export/download or quarantined import. Existing review packages and PDF/XLSX exports are narrower. |
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
- Phase 3 initial contract inventory/tests are merged. The next implementation
  task is trusted completion evidence following the newly verified asynchronous
  audit gap. The current candidate refuses incomplete/oversized pages only.
- Phase 8 remains blocked on fresh authority, evidence review, semantic approval
  and separately governed canonical/replacement-lock gates.
- Phases 9-14 remain dependency-blocked; package portability does not bypass them.
- Phase 8C is planned/gated; Phase 16 is deferred.
- A mandatory autonomous fleet is superseded as the target. OpenClaw remains
  required for the current bounded inference path until replacement parity.

See the [roadmap](./CLASSIFIRE_ROADMAP.md) for phase-specific acceptance criteria.

## 6. Recommended Next Actions

1. **Establish trusted execution/audit completion evidence.**
   After publishing the page-refusal candidate, define the completion/coverage
   proof and its fail-closed validation at existing service boundaries.
   Record migration impact and preserve legacy observation-receipt verification.
   The stock API has no certificate for writer health, dropped events or a
   persisted terminal boundary; polling or fabricated provider fields cannot
   supply one.
   [Start Here / Next Session](./SESSION_HANDOFF.md#start-here--next-session)
   provides prerequisites and completion criteria.
2. **After the remaining characterisation gate, establish the smallest durable run contract.**
   Extend BackgroundJob/worker where suitable, then add a feature-flagged
   provider adapter with tested rollback. Do not implement these in the
   characterisation task.
3. **Then deliver packages and shared interfaces.**
   Define membership/export rights, deterministic revisions and downloads,
   followed by quarantined new-project import and MCP/standalone adapters.
   Policy-permitted Draft exports need not wait for Phase 14 but cannot claim
   Released authority.

Technical-library and operational follow-ups remain separately scoped backlog.
Maintain full CI. Do not expand the next task into Phase 2/12, real UAT, packages
or a general agent platform.

## 7. Verification and limits

Current candidate verification: installed package/version, audit handler/schema,
event store and asynchronous writer inspected read-only; artifact hashes recorded
in the contract inventory. No live configuration or ledger was read. Ten new
refusal cases failed before the fix; 131 tests pass after it, including the legacy
golden receipt. Full Ruff/Bandit and Mypy (142 source files) passed; one Alembic head remains.
Declared type stubs were installed only in task-temporary storage. Existing Pillow
getdata warnings remain in representative tests. No real Gateway/provider,
customer data, canonical write, lock, deployment or release was exercised.
Baseline main CI 33935963213 passed; verify candidate CI/publication separately.

Detailed historical PR/runtime evidence remains in Git history and linked
documents; it was not all rerun here. No real report, customer evidence,
provider, Gateway, canonical project record, lock, deployment or release was
used or changed.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md).
