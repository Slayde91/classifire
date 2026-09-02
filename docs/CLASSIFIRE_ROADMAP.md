# CLASSIFIRE Master Roadmap

**Roadmap status:** Active

**Verified shared-main implementation:** `b33246a` (PR #126 merge, 2026-09-03)

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
- the PR #103 desk-quote evidence-read hardening;
- PR #104's expected-label manifests, atomic scope admission, V2 runner
  preflight, migration-head readiness, and `main` push validation;
- PRs #105-#118's factual reconciliation, semantic snapshot identity,
  retained-source safeguards, source-bound Draft materialisation, admission/
  UI/rule/release-administration type safety, XLSX row handling, and Mission
  Control task-response validation;
- production configuration, migration-head, browser, and diagnostic hardening;
- independent technical-document/variant review, clean source rechecks,
  current approved/unexpired source-document and stored-file metadata checks,
  technical-variant date-window checks,
  verified-byte candidate extraction and Draft-only metadata refresh after a
  clean-source recheck, Draft-only imports, source-bound variants and revisions,
  source locators, manual Draft materialisation, and active pinned
  technical-release safeguards;
- assumption-led desk-quote PDF/XLSX output as a parallel non-technical
  proposal path; and
- pull-request CI with changed-file and full-repository Ruff, full Mypy, full Bandit, full
  tests, PostgreSQL containment, and Alembic one-head validation.

PR #104 validation run `33515411987` passed on its exact head `0f6c252`. Its
first observed `main` push run `33516292114` also passed on merge `b6409a5`,
including tests and the one-head Alembic check. Every PR #105-#126 check and
corresponding `main` validation then passed; the latest post-merge run is
`33667477950` on `b33246a`. GitHub's branch-protection endpoint still returns
HTTP 403 because the current private-repository plan requires GitHub Pro or
public visibility for that configuration; required-check configuration remains
unverified.

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

### Immediate next action

#### Priority 0 - Define proposal-review package ownership before a UI

**Objective:** agree the minimum retention, redaction/deletion, reviewer-access,
and safe storage-locator contract for generated proposal-review packages before
creating a persistence migration or reviewer UI.

**Why this comes first:** PR #104 has integrated the runner and approval
boundary, but its deterministic package remains in memory or caller-selected
files. A UI or database record created before ownership is defined would create
an ungoverned second source of truth for proposal evidence.

**Scope:** retain only hash-bound package metadata, receipt/source/approval
references, reviewer-visible uncertainty, and a safe locator. The design must
remain proposal-only and add no canonical, technical, commercial, lock,
deployment, or release authority.

**Done when:** a reviewed lifecycle contract defines owner, reader, retention,
redaction/deletion, and tamper response; a later narrow migration and reviewer
surface can be tested against that contract without inventing policy.

**Uncertainty:** no existing evidence defines this lifecycle policy. It needs a
product/records-ownership decision before implementation.

### Completed and published foundations (not next actions)

#### Completed on shared main - Snapshot, technical-source, and type-safety safeguards (PRs #105-#118)

**Shared-main result:** PR #106 makes V2 snapshot identity stable across volatile
generation metadata while retaining a full-document integrity hash and V1
verification. PRs #107-#111 require retained technical sources at activation,
bind Draft variants and revisions to that exact source, require a source locator
before review, and keep extraction failures content-safe. PR #112 materialises
source-bound Draft variants only from clean retained documents. PR #113 makes
admission rejection helpers explicitly non-returning without weakening their
safe-code failure. PR #114 makes existing rule and UI response types explicit,
rejects non-text rule operators deterministically, and proves existing
library-page rendering. PR #116 preserves the existing release-administration
guards while clarifying their type boundaries; PR #117 clarifies XLSX row
handling; and PR #118 validates Mission Control task responses as JSON objects.
PR #119 reconciles those records, PR #120 uses an aware UTC clock for PDF
timestamps, and PRs #121-#122 apply current CLASSIFIRE branding to generated
artifacts and the browser workspace.

**Verification:** every PR #105-#122 check and its corresponding `main` push
validation passed; the latest `main` run is `33657134992` on `5639e26`. These
are safeguards only: no technical decision, release publication, pricing,
canonical submission, lock, deployment, or Human Release was added.

#### Completed on shared main - Report governance and main validation (PR #104)

**Shared-main result:** expected-label manifests are bound to retained report
bytes and an Estimate. Complete exact label sets are admitted atomically, each
new scope carries the approval binding, and the runner rejects legacy or unbound
scope packets before proposal-only execution. Migration and deployment-lineage
expectations now require the single packaged `0013` head.

**Verification:** PR run `33515411987` passed on `0f6c252`; post-merge `main`
run `33516292114` passed on `b6409a5`, including tests and the one-head Alembic
check. The change remains proposal-only and adds no canonical, technical,
commercial, lock, deployment, or release authority.

#### Completed on shared main - Desk-quote evidence hardening (PR #103)

**Shared-main result:** the resolver now requires an explicit Project/Estimate binding,
uses only immutable, `clean` ProjectEvidence-owned `project_evidence`, reopens
the exact retained bytes through the shared atomic reader, and checks caller
locators against persisted EvidenceSource or ReportEvidenceLocator data.
`technical_evidence` remains rejected.

**Verification:** new and cached bytes are re-hashed before return and their
hash/size are audited. Synthetic tests cover missing, altered, unsafe-path,
quarantined, cross-estimate, locator, cache-tamper, and PostgreSQL race cases.

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

No real customer report, quote, OpenClaw, Gateway, or provider run was used.
PR #103 passed CI and review; operational approval remains a separate gate before
use.

#### Completed on shared main - Secret-safe Phase 8 transport diagnostics

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

Commit `afb9de1` is an ancestor of shared `main`; historical receipts remain
verifiable and no real report/provider operation was used for this change.

#### Completed on shared main - Bounded report-assessment runner

**Current state:** `execute_phase8_report_assessment_runner()` composes the
service components as a proposal-only application service with fake-port tests.

**Required contract:** exact project, estimate, report SHA, package/policy/
profile, and a persisted human-approved expected Defect-label manifest bound to
report evidence/source SHA and estimate; every new scope batch atomically admits
the complete exact approved label set and retains that approval record; V2 scope
packets and the completion receipt bind the approval ID, SHA, and reference;
atomic clean-byte trust held through context consumption; one deterministic
outcome per expected label; no technical, pricing, canonical, lock, deployment,
or release capability.

**Acceptance criteria:**

- cross-project, hash, locator, label, profile, and byte drift fail before a
  provider call;
- omitted, duplicate, foreign, or mismatched expected labels are rejected before
  scope admission;
- retrieval-blocked, malformed, insufficient-evidence, transport-failed, and
  successful fake results each produce exactly one safe outcome;
- drawing/image locator-only and separately governed visual-byte semantics are
  preserved;
- captions remain unsupported until separately implemented and tested; and
- fake-transport integration, report-focused tests, PostgreSQL containment,
  full suite, static checks, Alembic head, and output inspection pass.

Shared-main behaviour: `execute_phase8_report_assessment_runner()` composes the
contained report reader, packets, documentary contexts, retained visual packets,
report-aware controller, proposal review, and deterministic package. It admits
new scopes only from the complete approved expected-label record, retains that
binding, then loads the same record after its clean-byte check and preflights V2
scope packets before an injected fake port. It emits a V2 receipt artifact bound
to that record. The full offline suite, focused static checks, Alembic head, and
the dedicated two-session containment race passed locally; PR and post-merge
shared CI also passed. Any real-provider run remains a separate gate, and no
downstream authority was added.

### Near-term actions

1. After the lifecycle contract is approved, implement a minimal immutable
   proposal-review package record before adding a UI. It must retain safe hashes,
   source/approval bindings, uncertainty, and a storage locator; test isolation,
   redaction, tamper failure, and absence of canonical authority.
2. Complete extraction-assisted and manufacturer-neutral lineage, publication,
   and supersession through separate migrations and reviews.
3. Independently validate physical, technical, quantity, labour, commercial,
   formula, recovery, and release integrity before Phase 12. Snapshot V2 already
   separates `generated_utc` from semantic identity while preserving full
   document integrity and V1 verification.
4. Maintain the full-repository Ruff, Mypy, and Bandit checks beside the changed-file
   Ruff fast-path, then have the repository owner decide on an upgrade or
   equivalent documented default-branch protection control.
5. Expand report evidence beyond PDF, add captions only with a real provenance
   contract, and prove multiple independent report formats.

### Later or dependency-bound actions

6. After synthetic transport behaviour is understood, obtain new explicit
   authority for one proposal-only report assessment. Review every artifact; a
   successful call is not semantic approval.
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

**Remaining:** the root checkout is conflicted recovery evidence; hosted `main`
validation passed through PR #126, but the current GitHub plan prevents
branch-protection configuration; clean-machine and release reproducibility
remain incomplete.

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
clean-source rechecks, current approved/unexpired source-document and retained-
file metadata checks, TechnicalVariant effective/expiry checks, verified-byte
candidate extraction and Draft-only
metadata refresh after a clean-source recheck, Draft-only imports, source-bound
variants and revisions, source-locator review gates, source-bound manual Draft
materialisation from clean retained documents, active immutable technical
releases, manifest eligibility checks, and active hash-bound pricing records.

**Remaining:** extraction-assisted and manufacturer-neutral lineage, governed
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
aware inputs, deterministic review artifacts, and PR #103's desk-quote
exact-byte/locator/artifact-audit checks.

**Completed foundations:** expected-label manifests bound to report bytes and
estimate; atomic complete-label scope admission; V2 approval-bound packets; and
runner preflight that rejects legacy/unbound packets before a no-tool port call.

**Remaining:** legacy-scope transition or retirement, package
retention/redaction/deletion policy, persistent reviewer package ownership,
caption/multi-format support, multi-report evidence-family accuracy, and user
review.

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

1. diagnose only with synthetic/fake ports;
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

Snapshot V2 now keeps volatile generation metadata out of the semantic hash and
binds the complete document with a separate integrity hash; V1 snapshots remain
verifiable. Independently validate physical, technical, quantity, labour,
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
- PR #75 as open work; it merged at `348bce5` and remains a bounded
  proposal-only prototype, with PR #103 evidence-read hardening on shared main.
- “Obtain authority and run the approved assessment” as the immediate task; the
  one authorised attempt already occurred and failed safely.
- Building the report runner as future work; shared main already composes it.
  The remaining work is package persistence/reviewer ownership and legacy-scope
  transition.
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
