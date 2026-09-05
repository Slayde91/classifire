# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST)
**Product status:** Pre-production implementation and controlled UAT
**Verified shared-main baseline:** `c080424c907b01a2a979f9efbfe9561bb097ba81` (PR #177, 2026-09-05)
**Latest executable-change baseline:** `7e8f473e45e51c4cf3505846cd978749efbdac59` (PR #174)

PR #175 adopted Architecture Decision 0001 in documentation. It did not implement
the hybrid migration. This snapshot separates freshly checked source/Git/test
evidence from historical runtime evidence. All four maintained documents live
under `docs/`; root-level duplicates are not maintained.

## Contract characterisation progress

The initial [contract inventory](./OPENCLAW_CONTRACT_CHARACTERISATION.md) maps
current callers and existing coverage. Thirteen added synthetic fallback/audit
cases bring the eight-file focused suite to 83 passing tests. Executable source,
runtime configuration and authority are unchanged; full retirement parity is
not complete. PR #177 merged this inventory and coverage as c080424; its exact
post-merge CI [33933164159](https://github.com/Slayde91/classifire/actions/runs/33933164159)
passed. This documentation reconciliation rechecked that result and the 83-test
synthetic baseline; it makes no executable change.

**Next bounded task:** investigate ambiguous CLI timeout handling using a fake
completed session creation followed by a lost reply. The CLI maps timeout to
RPC_UNAVAILABLE, which can select fallback even for sessions.create. Determine
and test a fail-closed resolution without altering read-only fallback,
historical receipt compatibility or calling a real Gateway. This takes priority
over coordinator/adapter/package implementation. Other inventory gaps are listed
in the contract document.

## 1. Project health and publication

| Area | Verified state | Meaning |
| --- | --- | --- |
| Shared main | PR #177 merged as `c080424`; executable lineage through PR #174 remains present. | Hybrid is accepted, not a completed runtime migration. |
| Hosted CI | [Main run 33933164159](https://github.com/Slayde91/classifire/actions/runs/33933164159) succeeded on exactly `c080424`. | Source/test/static/migration evidence, not production or real-UAT proof. |
| Local synthetic verification | 83 tests passed across the eight contract/security files in the handoff; the prior 70-test baseline remains historical evidence. | Existing contracts have a passing baseline; full migration parity is not proven. |
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

Current documentation branch: `docs/current-hybrid-state-20260905`, worktree
`C:\CLASSIFIRE\.tmp\docs-current-hybrid-state-20260905`, created clean
from `c080424`. Only these four documents belong to this update. PR #176
previously merged the documentation reconciliation; PR #177 merged the initial
contract inventory/tests. Check Git/GitHub for this update's later publication
outcome; this snapshot does not claim its own future merge.

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
  task is the bounded uncertain-session-creation correction; this update is
  documentation-only.
- Phase 8 remains blocked on fresh authority, evidence review, semantic approval
  and separately governed canonical/replacement-lock gates.
- Phases 9-14 remain dependency-blocked; package portability does not bypass them.
- Phase 8C is planned/gated; Phase 16 is deferred.
- A mandatory autonomous fleet is superseded as the target. OpenClaw remains
  required for the current bounded inference path until replacement parity.

See the [roadmap](./CLASSIFIRE_ROADMAP.md) for phase-specific acceptance criteria.

## 6. Recommended Next Actions

1. **Resolve uncertain session creation after a lost CLI reply.**
   Add a composed fake-transport regression proving whether fallback can repeat
   an already completed creation, then make only the justified fail-closed fix.
   Preserve read-only fallback, no-tool enforcement, context separation, safe
   diagnostics and receipt compatibility. The initial inventory and 13 added
   cases are already merged; do not repeat them.
   [Start Here / Next Session](./SESSION_HANDOFF.md#start-here--next-session)
   provides files, commands and completion criteria.
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

Freshly checked for this documentation update: fetched main at c080424;
isolated starting tree; root conflict/local-change state; open PRs/issues;
successful exact-main CI 33933164159; basic branch metadata (unprotected,
no enforced checks); CLI/fallback and worker source; 83 passing synthetic
contract/security tests; documentation scope, links and diff checks.

Earlier PR #177 validation recorded full Ruff/Bandit and Mypy across 142 source
files. Those static checks are historical evidence here; hosted CI for this
documentation change must be checked separately before publication.

Detailed historical PR/runtime evidence remains in Git history and linked
documents; it was not all rerun here. No real report, customer evidence,
provider, Gateway, canonical project record, lock, deployment or release was
used or changed.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md).
