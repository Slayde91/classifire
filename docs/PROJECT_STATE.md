# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST)
**Product status:** Pre-production implementation and controlled UAT
**Verified shared-main baseline:** `d03753f94634860ed3381825f4c5d2f514e6523d` (PR #183, 2026-09-05)
**Latest executable-change baseline:** d03753f (PR #183)

PR #175 adopted Architecture Decision 0001 in documentation. It did not implement
the hybrid migration. This snapshot separates freshly checked source/Git/test
evidence from historical runtime evidence. All four maintained documents live
under `docs/`; root-level duplicates are not maintained.

## Contract characterisation progress

PR #183 merged the required completion consumer as `d03753f94634860ed3381825f4c5d2f514e6523d`.
[Exact main CI 33939296281](https://github.com/Slayde91/classifire/actions/runs/33939296281)
passed. Managed OpenClaw factories have no trusted production verifier and refuse
inference dispatch; the independent no-tool boundary remains intact.

**Current journal candidate:** `feat/execution-journal-20260905`, based on
`d03753f`, adds `services/execution_journal.py` on the existing BackgroundJob
table. It commits reservation and capture identity before producer execution,
then commits a sealed terminal record before returning completion evidence.
Owner, producer, invocation, context, state and record version are bound.
Exact completed replay does not redispatch; failed/interrupted/running attempts
cannot replay. Conditional updates prevent late completion after interruption.

**Trust and limits:** an injected trusted producer owns capture assurance.
HMAC protects stored journal content using an application-held key; it cannot
prove remote tool activity or replace producer authentication. Owner identity
must come from authenticated application composition, not user-supplied authority.
There is no API, generic-worker dispatch, runtime wiring, new dependency or
database migration. Managed inference remains blocked.

**Verification:** 27 journal tests and 171 transport/security/caller tests passed
locally. Three additional PostgreSQL restart/concurrency cases use the existing
explicit disposable-database fixture and must pass in hosted CI. Full Ruff,
Bandit and Mypy (143 source files) passed; one migration head remains. Existing
Pillow warnings persist. No real provider or customer/canonical operation ran.

**Next bounded task:** integrate the journal at the Phase 8 pre-dispatch and
post-response boundaries using injected capture/verification ports. Prove one
invocation and durable acceptance end to end with synthetic transport, including
crash and late completion. Avoid a circular dependency in which the transport
waits for a journal completion that can only be written after transport return.
Do not wire a real provider until its capture/terminal proof is authenticated;
empty audit pages and a locally sealed assertion are not enough.

## 1. Project health and publication

| Area | Verified state | Meaning |
| --- | --- | --- |
| Shared main | PR #183 merged as d03753f; required completion acceptance is implemented. | Hybrid is accepted, not a completed runtime migration. |
| Hosted CI | [Main run 33939296281](https://github.com/Slayde91/classifire/actions/runs/33939296281) succeeded on exactly `d03753f`. | Source/test/static/migration evidence, not production or real-UAT proof. |
| Local synthetic verification | 27 journal and 171 existing transport/caller tests passed; three PostgreSQL cases await hosted CI. | Existing contracts have a passing baseline; full migration parity is not proven. |
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

Current candidate: `feat/execution-journal-20260905` in
`C:\CLASSIFIRE\.tmp\execution-journal-20260905`, created cleanly from `d03753f`.
Scope: the new journal service, SQLite and PostgreSQL tests, completion contract,
contract inventory and four continuity documents. The previous consumer worktree
is clean and retained. Root recovery evidence remains unrelated and untouched.
Verify the current candidate commit/upstream/PR/merge before relying on publication.

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
| Background work | BackgroundJob and polling shell; generic queued jobs still have no handlers. Candidate journal uses separate non-queued states and explicit producer calls | `models.py`, `worker.py` |

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
| Hybrid execution | Candidate adds durable single-invocation journal, replay refusal and local interruption; full stage coordination, remote cancellation, transport integration and retirement remain incomplete. |
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
  consumer is merged; the journal candidate adds durable single-attempt storage.
  Next is transport lifecycle integration; production capture remains unproven.
- Phase 8 remains blocked on fresh authority, evidence review, semantic approval
  and separately governed canonical/replacement-lock gates.
- Phases 9-14 remain dependency-blocked; package portability does not bypass them.
- Phase 8C is planned/gated; Phase 16 is deferred.
- A mandatory autonomous fleet is superseded as the target. OpenClaw remains
  required for the current bounded inference path until replacement parity.

See the [roadmap](./CLASSIFIRE_ROADMAP.md) for phase-specific acceptance criteria.

## 6. Recommended Next Actions

1. **After journal publication, integrate its lifecycle with Phase 8.**
   Commit capture/invocation state before HTTP and terminal evidence before
   proposal acceptance, using injected trusted capture/verification ports.
   Prove the shared visual/report path with synthetic end-to-end tests and
   no circular transport/journal dependency.
   [Start Here / Next Session](./SESSION_HANDOFF.md#start-here--next-session)
   defines files, dependencies and acceptance criteria.
2. **Prove actual producer assurance before production wiring.**
   A local seal cannot certify remote events. Establish the permitted producer's
   capture/terminal identity, privacy, loss detection, cancellation and recovery.
   Keep managed inference and OpenClaw retirement gated until parity is proven.
3. **Deliver portable packages and shared interfaces in bounded slices.**
   Define membership/export rights, immutable revisions and downloads, then
   quarantined import and shared ChatGPT/standalone adapters. Draft exports need
   not await Phase 14 or retirement; they confer no release authority.

Technical-library and operational follow-ups remain separately scoped backlog.
Maintain full CI. Do not expand the next task into Phase 2/12, real UAT, packages
or a general agent platform.

## 7. Verification and limits

The journal has 27 passing file-backed SQLite tests; 171 existing transport/
security/caller tests also passed. Three guarded disposable PostgreSQL cases are
included for hosted CI and were skipped locally. Full Ruff/Bandit and Mypy (143
files) passed; Alembic retains head 0026_single_active_technical_release. Stored
synthetic rows, capture-before-execution ordering, restart, corruption, ownership,
failures, concurrent duplicate and late-completion outcomes were inspected in tests.
Eight existing Pillow warnings remain.

Baseline main d03753f and CI 33939296281 passed. Verify candidate CI/publication
separately. No real provider, customer evidence, project/canonical database,
lock, deployment or release was exercised. Producer assurance, production key
custody/rotation, remote cancellation and anti-rollback remain unproven.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md).
