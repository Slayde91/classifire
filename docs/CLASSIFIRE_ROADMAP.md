# CLASSIFIRE Master Roadmap

**Roadmap status:** Active

**Verified baseline:** `db28c638` (PR #100 merge, reviewed 2026-09-01)

This roadmap records verified implementation, remaining gates, and execution
order. It does not grant operational authority. Current source, tests,
migrations, Git/GitHub state, and retained receipts outrank older roadmap text.

Read with [PROJECT_STATE.md](./PROJECT_STATE.md) for the detailed current
snapshot and [CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md) for the
governing boundaries.

## 1. Status labels

| Label | Meaning |
| --- | --- |
| **Completed foundation** | Implemented and verified for the stated narrow boundary; later product gates may remain. |
| **In progress** | Material implementation exists but exit criteria are incomplete. |
| **Planned** | Approved direction without completed implementation. |
| **Blocked** | An upstream evidence, authority, safety, or implementation gate prevents progress. |
| **Deprecated / superseded** | Retained for history or compatibility; not the current build path. |

“Code exists” never means a whole phase is complete.

## 2. Current product position

Shared main now includes:

- core application, persistence, UI, API, audit, authentication, and packaged
  migration foundations;
- physical-model, evidence, proposal-only visual, admission, and receipt
  boundaries;
- Project/Estimate report ownership, atomic PostgreSQL clean-byte handling,
  stable PDF locators/scopes, report assessment components, and deterministic
  review packages;
- production configuration, migration-head, browser, and diagnostic hardening;
- independent technical-document/variant review, source rechecks, Draft-only
  imports, and active pinned technical-release safeguards;
- assumption-led desk-quote PDF/XLSX output as a parallel non-technical
  proposal path; and
- pull-request CI with Ruff, full tests, PostgreSQL containment, and Alembic
  one-head validation.

The latest hosted evidence is PR #100 run `33330916501`: 577 tests passed with
140 warnings. The workflow validates pull-request heads only; `main` has no
post-merge run, required checks, or branch protection.

The newest controlled Phase 8 attempt is not a proposal result. Runtime
inference began, then failed at the first blind-inventory call with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`. Rollback/no-write/no-lock
boundaries held. Its historical receipt retained only the transport exception
type, not the stable safe code. New proposal-only receipts retain established
safe codes without exposing exception content. No rerun is authorised.

## 3. Roadmap at a glance

| Phase | Status | Primary exit condition |
| --- | --- | --- |
| 0. Product, repository, and change control | **In progress** | Reproducible clean source, protected publication, and auditable operational evidence |
| 1. Domain and workflow governance | **In progress** | Governed physical amendments, receipt eligibility, and separate lock authority |
| 2. Governed technical/commercial libraries | **In progress** | Immutable authorised source and runtime releases with complete lineage |
| 3. OpenClaw and controlled write | **In progress** | Least privilege, reproducible operations, safe diagnostics, and approved operator flows |
| 4. Mission Control integration | **In progress** | Useful visibility without becoming estimate truth |
| 5. Evidence intake and resolution | **In progress** | Complete, owned, exact-byte evidence and expected-label coverage across supported reports |
| 6. Physical Model engine | **In progress** | Defensible model or explicit limitation for every known Defect |
| 7. Independent visual topology gate | **In progress** | Durable independent validation for every future lock candidate |
| 8. Corrected real Physical UAT | **Blocked** | Semantically approved canonical model and replacement active Physical Model Lock |
| 8C. Physical-model accuracy programme | **Planned** | Leakage-safe measured improvement after admission gates |
| 9. Technical system selection | **Blocked by Phase 8** | One defensible current strategy per supported Opening |
| 10. Quantity and labour | **Blocked by Phase 9** | Deterministic authorised components, quantities, and labour |
| 11. Commercial recovery | **Blocked by Phases 9-10** | Each required component recovered once |
| 12. Validation and immutable snapshot | **Blocked by Phases 8-11** | Reproducible snapshot with no unresolved blockers |
| 13. Canonical output generation | **Blocked by Phase 12** | Snapshot-only technical/client outputs |
| 14. Human Release | **Blocked by Phase 13** | Human acceptance of exact snapshot/output hashes |
| 15. Production hardening | **In progress** | Secure, observable, recoverable, reproducible operation |
| 16. Structural steel and full duct runs | **Planned / deferred** | Separate approved domains and evidence |

The desk-quote path is a bounded proposal-only exception. It does not advance
Phases 8-14 and is not a technical selection or canonical output.

## 4. Prioritised build plan

### Immediate next actions

#### Priority 0 - Harden desk-quote evidence before operational use

**Objective:** narrow the current desk-quote slice to `project_evidence` and make
every reference use the same ProjectEvidence-owned, atomic, exact clean-byte
boundary as the report adapter. Keep `technical_evidence` rejected unless a
separate Estimate-owned exact-byte contract is designed and approved.

**Why now:** PR #75 is merged and exposes a tangible PDF/XLSX API, but its
resolver currently trusts metadata, accepts `not_configured`, and does not
verify the caller's locator against persisted page/region or report locators.

**Relevant components:**

- `src/classifire/services/desk_quote.py`
- `src/classifire/api/router.py`
- `src/classifire/services/storage.py`
- `src/classifire/services/project_evidence.py`
- `tests/test_desk_quote.py`
- `tests/test_shared_file_containment.py`

**Acceptance criteria:**

1. only Project/Estimate-owned, immutable, `clean`, exact retained bytes are
   usable;
2. `not_configured`, pending, quarantined, missing, altered, outside-root,
   symlink, and Windows reparse-point sources fail closed;
3. locator text matches persisted EvidenceSource page/region data or a stable
   `ReportEvidenceLocator`;
4. cross-project and cross-estimate evidence fails;
5. the PostgreSQL quarantine/read race remains serialized;
6. new and cached export bytes are hash-verified and the artifact hash is
   included in the audit record;
7. failure creates no export, cached artifact, audit event, canonical state,
   technical decision, pricing mutation, or lock; and
8. focused tests, PostgreSQL race, full suite, Ruff, Mypy, Alembic head, and
   `git diff --check` pass.

No real customer report or quote is required for verification.

#### Priority 1 - Preserve secret-safe Phase 8 transport diagnostics (implemented on this branch)

**Result:** commit `afb9de1` propagates only the established safe transport code
through new outer `INFERENCE_PORT_FAILED` receipts. Historical receipts remain
valid and content-free.

**Why now:** the authorised assessment failed safely, but the receipt cannot
identify the transport failure class beyond the Python exception type.

**Acceptance criteria:**

- known codes such as `GATEWAY_TIMEOUT` survive;
- arbitrary exception messages, malformed codes, response content, tokens, and
  report content do not;
- generic exceptions retain type-only behaviour;
- receipt validation, stage hashes, protected-state checks, and no-write flags
  remain valid; and
- synthetic/fake-port tests, focused regressions, Ruff, and the full suite pass
  without report, OpenClaw, Gateway, or provider execution.

The code and focused synthetic tests satisfy the implementation criteria above;
full-suite and shared-main CI evidence remain required before any merge claim.

#### Priority 2 - Compose one bounded report-assessment runner

**Objective:** turn the merged service components into a supported proposal-only
operator flow with a fake-transport preflight.

**Required contract:** exact project, estimate, report SHA, package/policy/
profile, and approved expected Defect-label list; atomic clean-byte trust held
through context consumption; one deterministic outcome per expected label;
completion receipt over every preceding artifact; no technical, pricing,
canonical, lock, deployment, or release capability.

**Acceptance criteria:**

- cross-project, hash, locator, label, profile, and byte drift fail before a
  provider call;
- omitted expected labels are detected;
- retrieval-blocked, malformed, insufficient-evidence, transport-failed, and
  successful fake results each produce exactly one safe outcome;
- drawing/image locator-only and separately governed visual-byte semantics are
  preserved;
- captions remain unsupported until separately implemented and tested; and
- fake-transport integration, report-focused tests, PostgreSQL containment,
  full suite, static checks, Alembic head, and output inspection pass.

Current branch progress: `execute_phase8_report_assessment_runner()` now composes
the contained report reader, packets, documentary contexts, retained visual
packets, report-aware controller, proposal review, and deterministic package. It
preflights all scopes before an injected fake port and retains/hash-covers the
resulting expected-label manifest plus every controller, Phase 8 review, proposal,
packet, review, and Markdown artifact. The full offline suite, focused static
checks, Alembic head, and the dedicated two-session containment race pass locally.
Fresh shared CI and any real-provider run remain required gates; no downstream
authority was added.

### Near-term actions

3. Add a minimal report review UI after Priority 2. It must expose source
   locators, confidence, alternatives, unresolved facts, and receipt status
   without write authority.
4. Complete Draft technical materialisation, source lineage, publication, and
   supersession through separate migrations and reviews.
5. Define a semantic snapshot hash independent of `generated_utc`; add snapshot
   and output regression tests before Phase 12.
6. Add required pull-request checks and protect `main` after repository-owner
   approval. The current workflow already provides the candidate check set.
7. Expand report evidence beyond PDF, add captions only with a real provenance
   contract, and prove multiple independent report formats.

### Later or dependency-bound actions

8. After Priorities 1-2 are reviewed and the transport path is understood,
   obtain new explicit authority for one proposal-only report assessment. Review
   every artifact; a successful call is not semantic approval.
9. Resolve remaining physical uncertainty and obtain independent semantic
   approval before any canonical preflight.
10. Keep admission signing, registration, canonical submission, and Physical
    Model Lock as separately authorised operations.
11. Keep Phases 9-14 blocked until the replacement lock exists.
12. Continue Phase 15 security, recovery, data-rights, and performance work only
    where it cannot bypass an upstream product gate.

## 5. Phase details

### Phase 0 - Product, repository, and change control

**Status:** In progress

**Completed foundations:** feature-branch history, explicit authority gates,
private evidence rules, GitHub pull-request workflow, packaged migrations, and
receipt/source hashes.

**Remaining:** the root checkout is conflicted recovery evidence; `main` lacks
required checks and branch protection; the workflow has no post-merge run;
clean-machine/release reproducibility remains incomplete.

**Exit:** every publishable change starts from clean current main, is reviewed,
passes required checks, and is traceable without secrets or customer evidence.

### Phase 1 - Domain and workflow governance

**Status:** In progress

**Completed foundations:** separate Defect, EvidenceSource, Opening, Service,
`ServiceOpeningLink`, blank-opening, protected-state, admission, submission,
receipt, and lock concepts.

**Remaining:** complete amendment/reopen rules, visual-receipt eligibility in the
future lock path, and broader all-blank/mixed-service regression proof.

**Exit:** physical state and amendments are service-governed, attributable,
audited, and cannot be changed by an unauthorised role.

### Phase 2 - Governed technical and commercial libraries

**Status:** In progress

**Completed foundations:** independent technical document/variant decisions,
clean-source rechecks, Draft-only imports, active immutable technical releases,
manifest eligibility checks, and active hash-bound pricing records.

**Remaining:** Draft materialisation, manufacturer-neutral lineage, governed
publication/supersession, clean-machine import/recovery, and full commercial
rate-inclusion/recovery rules.

**Exit:** every technical/commercial decision cites an immutable authorised
release and its source cannot silently change after use.

### Phase 3 - OpenClaw and controlled write

**Status:** In progress

**Completed foundations:** role-limited no-tool proposal sessions, literal-
loopback transports, evidence rehashing, tool attestation/audit, proposal-only
receipts, admission registration, and one-shot submission boundaries.

**Remaining:** PostgreSQL containment execution, clean-machine runbooks,
credential custody, recovery/timeout evidence, and separate lock-admission
design.

**Exit:** every operation has minimum authority, safe diagnostics, exact inputs,
reproducible setup, attribution, and tested recovery.

### Phase 4 - Mission Control

**Status:** In progress

Mission Control may mirror tasks, run/gate summaries, and links. CLASSIFIRE
remains the source of project, evidence, physical, technical, commercial,
snapshot, and release truth.

**Exit:** operational visibility is useful without a second mutable estimate
database or approval workflow.

### Phase 5 - Evidence intake and resolution

**Status:** In progress

**Completed foundations:** retained evidence, linked-original controls,
Project/Estimate ownership, exact clean-byte reads, shared-byte quarantine,
PDF text/table/annotation and drawing/image locators, ordered scopes, report-
aware inputs, and deterministic review artifacts.

**Remaining:** Priority 0 desk-quote byte/locator safety, Priority 2 approved
expected-label-source proof, caption/multi-format support, multi-report
evidence-family accuracy, retention/redaction/deletion policy, and user review.

**Exit:** every downstream claim traces to exact retained bytes and a stable
report/page/item or visual locator; expected items cannot disappear silently.

### Phase 6 - Physical Model engine

**Status:** In progress

Proposal schemas and canonical physical records exist, but proposal structure is
not accepted truth. Unknown topology, substrate, dimensions, material, quantity,
or continuity remains explicit.

**Exit:** every known Defect has a defensible physical model or explicit
limitation, and a valid replacement lock exists.

### Phase 7 - Independent visual topology gate

**Status:** In progress

Historical controlled UAT proved a valid independent block and rollback. The
latest attempt failed before a new blind inventory was produced. Durable receipt
registration exists; safe diagnostics, report orchestration, broader evidence,
and future lock enforcement remain.

**Exit:** every lock candidate has an independently verified, semantically
accepted, exact durable receipt.

### Phase 8 - Corrected real Physical UAT

**Status:** Blocked

The report services and proposal contracts are merged. The 2026-09-01 authorised
attempt failed at its first inference stage; no assessment or comparison result
exists. Rollback and no-write/no-lock safeguards held.

**Ordered gate:**

1. complete Priorities 1-2 with synthetic evidence only;
2. obtain new run authority;
3. produce and human-review one outcome for every approved label;
4. resolve or retain physical uncertainty;
5. obtain independent semantic approval;
6. perform a fresh no-write canonical preflight;
7. separately authorise signing, registration, and exact canonical submission;
8. separately design/approve/authorise the replacement lock.

**Exit:** every known Defect is defensibly represented or withheld with reason,
the accepted canonical model is receipt-bound, and a replacement active Physical
Model Lock supersedes invalid historical state.

### Phase 8C - Physical-model accuracy programme

**Status:** Planned

Only charter, taxonomy, and data-rights preparation may begin before Phase 8
produces a defensible replacement lock and an end-to-end prototype reaches
snapshot-backed outputs.

The programme keeps four lanes separate: evaluation; system/prompt improvement;
optional model training; and governed continual learning. It requires rights-
cleared report/site/customer splits, evidence-family grouping, sealed holdout,
prospective shadow evaluation, uncertainty and critical-error measures, targeted
human exception review, versioned releases, rollback, and no per-report online
learning. Model output never gains canonical, lock, technical, commercial, or
Human Release authority.

### Phase 9 - Technical system selection

**Status:** Blocked by Phase 8

Search only the pinned authorised technical release, evaluate every relevant
physical condition, preserve mismatches/unknowns, and create one current strategy
per supported Opening. Pricing never proves suitability.

### Phase 10 - Quantity and labour

**Status:** Blocked by Phase 9

Derive component quantities and labour from selected systems with explicit
inputs, units, waste, rounding, procurement, access, productivity, crew, and
shared-work rules. Missing productivity fails closed.

### Phase 11 - Commercial recovery

**Status:** Blocked by Phases 9-10

Recover each required component once through an authorised pricing hierarchy
and explicit inclusion/recovery ledger. The desk-quote prototype remains a
parallel assumption-led allowance and does not satisfy this exit.

### Phase 12 - Independent validation and immutable snapshot

**Status:** Blocked by Phases 8-11

Resolve snapshot identity so volatile generation metadata does not change the
semantic hash. Independently validate physical, technical, quantity, labour,
commercial, formula, recovery, and release integrity.

### Phase 13 - Canonical output generation

**Status:** Blocked by Phase 12

Render technical/client artifacts from the immutable validated snapshot only;
renderers must not recalculate or reinterpret scope. Desk-quote PDF/XLSX output
does not mark this canonical phase complete.

### Phase 14 - Human Release

**Status:** Blocked by Phase 13

An authorised competent human accepts the exact validated snapshot and output
hashes. No model, benchmark, prompt, or agent may approve final release.

### Phase 15 - Production hardening

**Status:** In progress

Merged configuration, browser, migration, diagnostics, storage, and CI controls
are foundations only. Remaining work includes clean-machine deployment,
dependency locking, backup/restore, monitoring, incident response, privacy/data
rights, malicious-evidence and prompt-injection testing, output formula safety,
performance/cost benchmarks, and rollback exercises.

### Phase 16 - Structural steel and full duct runs

**Status:** Planned / deferred

These domains require separate physical taxonomies, source authority,
calculations, libraries, benchmark evidence, and acceptance criteria. Do not
import them into the active fire-seal/penetration runtime prematurely.

## 6. Deprecated and superseded work

- The conflicted root checkout as a publication, deployment, or bulk-merge path.
- Draft PRs #9-#13 as current-main candidates without selective reconstruction.
- PR #75 as open work; it merged at `348bce5` and is now a bounded prototype
  requiring Priority 0 hardening.
- “Obtain authority and run the approved assessment” as the immediate task; the
  one authorised attempt already occurred and failed safely.
- Building the report adapter as future work; its components are merged, while
  operator composition and expected-label proof remain.
- Site visit as an automatic first response; exhaust governed report evidence
  first and request confirmation only where materially required.
- Count equality, whole-file database hashing, or a model answer as semantic
  acceptance.
- Initial submission and Physical Model Lock as one authority.

## 7. Roadmap-wide rules

1. Source evidence is immutable; corrections are governed amendments.
2. Canonical writes are least-privilege, audited, and receipt-bound.
3. Proposal-only testing is the default for uncertain/model-driven work.
4. Human fixtures and same-case answers remain hidden from inference.
5. Better evidence does not justify inventing concealed facts.
6. Correct abstention beats unsupported confidence.
7. Technical suitability and commercial price remain separate.
8. Shared work is commercially recovered once.
9. No downstream phase bypasses an unresolved upstream gate.
10. Final release remains human-only.

## 8. Related documents

- [Current Project State](./PROJECT_STATE.md)
- [CLASSIFIRE Architecture](./CLASSIFIRE_ARCHITECTURE.md)
- [Current Session Handoff](./SESSION_HANDOFF.md)
- [Desk Quote Assumption Contract](./DESK_QUOTE_ASSUMPTION_CONTRACT.md)
- [Phase 8 Representative Run Package](./PHASE8_REPRESENTATIVE_RUN_PACKAGE.md)
- [Admission-Bound Writer Deployment Runbook](./ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md)
