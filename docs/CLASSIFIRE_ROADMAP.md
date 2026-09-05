# CLASSIFIRE Master Roadmap

**Status:** Active; prototype-first delivery approved 2026-09-05.
**Verified shared-main baseline before P1a:** `96d686952021828ef1fb28b53f4d6eea566376aa` (PR #188).
**P1a implementation:** locally demonstrated on `feat/draft-scope-import-20260905`; verify publication from current Git/PR checks.
**Accepted architecture:** [ADR 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md)
plus approved [ADR 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md).

## 1. Delivery decision

**Build a working, testable UI prototype before broad fine tuning.** The first
milestone is a persisted Draft Scope workspace in the existing application.
Deliver its screen, minimum shared contract, validation, storage and download as
one usable slice. Do not finish every schema, archive feature, orchestration
abstraction or edge case before allowing a user to try the product.

The four capabilities remain independently callable: scope analysis, system
matching, estimating and reporting. The full evidence-to-Human-Release chain
is a rule for defensible conclusions and authority, not a mandatory user journey.
Users may stop, edit, save, export, replace inputs and explicitly continue.

[Project State](./PROJECT_STATE.md) records what is actually implemented;
[Architecture](./CLASSIFIRE_ARCHITECTURE.md) defines boundaries;
[Handoff](./SESSION_HANDOFF.md) specifies the single next engineering task;
[GOAL.md](../GOAL.md) records the product outcome.

## 2. Verified starting point

- Existing FastAPI/Jinja UI supports authentication, projects, estimates, manual
  physical entry, library administration and retained proposal-review screens.
  P0 now extends that shell with a separate persisted manual Draft Scope workspace;
  see the [demo](./DRAFT_SCOPE_DEMO.md) and [contract](./DRAFT_SCOPE_V1_CONTRACT.md).
- Existing opening/service forms write guarded canonical physical rows. Preserve
  their behavior; a Draft editor must not use them by disabling admission guards.
- Deterministic domain services, exact-byte evidence handling, technical-library
  governance, calculation/snapshot/rendering, audit and migrations are foundations.
- PR #185's completion consumer/journal/lifecycle hooks are merged. Full workflow
  scheduling, production capture assurance and OpenClaw replacement are incomplete.
- P0 main CI [33947498324](https://github.com/Slayde91/classifire/actions/runs/33947498324)
  passed on `96d6869` with 1,020 tests. P1a adds an actual Chrome upload/preview/
  confirmed replacement/manual-edit/reimport/restart demonstration and focused
  service/HTTP checks; verify its own publication. No result proves production readiness.
- Three untracked Draft ProjectPackage files remain in
  `.tmp/project-package-draft-20260905`; their 22 tests passed in the prior review.
  They are candidate archive work, not a shipped contract or UI. Reuse compatible
  pieces when needed, preserving originals and documenting any schema change.
- Historical Phase 8 UAT/lock state was not rechecked against a live database.
  Production and authoritative real-data exits remain unproven.

## 3. Status and evidence rules

| Status | Meaning |
| --- | --- |
| Completed foundation | Narrow implementation and evidence exist; not a completed product milestone. |
| Next / planned | Approved work, without demonstrated completion. |
| Active local candidate | Unmerged work to inspect and reuse; not shared-main capability. |
| Reordered / superseded | A previous delivery priority no longer controls the next task. |
| Blocked authoritative exit | Required real evidence/approval/operational proof is absent; safe Draft development may continue. |
| Deferred | Deliberately outside the current prototype path; revisit on evidence or feedback. |

A UI milestone requires observed browser behavior plus relevant API/service tests.
A schema, test count, mock screen or successful CI alone does not finish it.

## 4. Prioritised build plan

### Prototype delivery track

Order by user-visible value. Build the minimum shared contracts within each
slice. Keep each PR focused on its selected increment; do not bundle the whole
prototype into it.

| Milestone | Priority/status | User-visible exit and required evidence |
| --- | --- | --- |
| **P0. Draft Scope workspace** | **Completed bounded prototype; merged PR #188** | In an isolated synthetic environment, log in, create/open a project, enter one defect with multiple openings/services and an unresolved observation, validate, save, reload/restart, reopen and download the exact saved Draft Scope JSON. Inspect the browser and downloaded content. No matching, pricing or canonical promotion runs. |
| **P1a. Saved Scope import/replacement** | **Implemented and locally demonstrated; verify publication** | Upload saved Draft Scope JSON, validate/check its declared hash and version, preview identity/content/uncertainty and explicitly append a local revision. Preserve source lineage and prior revisions; reject stale saves and foreign authority. Demonstrate browser round trip and refusal cases. No ZIP or report extraction in this slice. |
| **P1b. One evidence intake path** | Upcoming; scan/storage/retention prerequisites unresolved | Add one explicitly supported evidence intake path using existing retained-evidence services. Unsupported content is visibly refused; extraction remains proposed until reviewed. Manual entry stays usable without AI. |
| **P2. System matching workspace** | Upcoming | Load saved/manual valid scope in a fresh session, view evidence-bound candidates or unresolved findings from a small synthetic approved library, inspect reasons/limits, save/export a System Match revision and stop without estimating. No keyword-only compatibility or fabricated approvals. |
| **P3. Estimate workspace** | Upcoming | Load sufficient saved/manual scope, quantity and system inputs; calculate a small supported scenario with units, explicit rate/method basis, recovery and overrides; save/export an Estimate revision and stop without reporting. Unknown technical/pricing facts remain visibly provisional or unresolved. |
| **P4a. Scope-only Draft reports** | **Next after P1a publication; advanced from P4** | Explicitly select a saved Scope, freeze its envelope/project labels/profile version together, preview and download readable PDF plus filterable XLSX from that same retained snapshot. Reopen after restart without output drift. Include missing/unknown values and imported lineage; no estimation or canonical lock bypass. Inspect page images and workbook cells/types. |
| **P4b. Other independent Draft report profiles** | Planned after relevant artifacts exist | Select available revisions and scope-only, technical, estimate or combined profile; preview missing/stale sections; download readable PDF and filterable XLSX from the same snapshot. Inspect both formats, IDs, units, formulas and totals. Do not recalculate or require all capabilities to run. |
| **P5. Project portability and shared ChatGPT access** | After relevant commands are demonstrated | Bundle declared capability/evidence revisions, validate exact membership and rights, save/download a versioned ProjectPackage and safely import into a new project. A thin ChatGPT client invokes the same proven commands; it need not wait for unrelated domain breadth. Inspect round-trip content and client parity. |
| **P6. User trial and refinement** | After each usable slice; consolidate after P0-P4 | A user completes the documented tasks; record observed failures and usability feedback, fix supported-path problems, then broaden formats, technical/pricing coverage and edge cases. No fixed timeline or accuracy claim without measurements. |

**First interactive prototype = P0. Four-capability prototype = demonstrated
P0-P4 behavior**, including P1a/P1b, independent/manual entry and reporting from partial
inputs. Full portability/ChatGPT and production readiness are separate exits.
No placeholder button or hard-coded success screen counts as a capability.

### Minimum controls now; refinement later

| Required for each exposed prototype path | Can wait until needed or after user feedback |
| --- | --- |
| Existing authentication, CSRF for browser mutations, appropriate permissions, explicit project/artifact ownership and a controlled test environment | Multi-organization product breadth and production tenancy rollout; never claim cross-tenant isolation without proof |
| Stable IDs, valid relationships/units, attributed manual input, uncertainty, provenance, durable saves and revision identity | Exhaustive taxonomies, every document format, polished layouts and every rare workflow combination |
| Preserve canonical guards, technical/commercial separation, deterministic supported calculations and visible Draft status | Real canonical Phase 8-14 acceptance, production lock/release operations and deep accuracy optimization |
| Bound and validate exposed inputs/downloads, refuse unsafe paths/tampering and avoid secrets or customer fixtures; safe spreadsheet output when exposed | ZIP conflict resolution/offline synchronization before ZIP import exists; large-file/performance tuning before measured need |
| Targeted happy-path and material negative tests, browser inspection, required CI and no known supported-path safety/correctness defect | General agent framework, full scheduler, provider migration and broad failure-matrix expansion unrelated to the selected slice |

Deferring breadth means restricting and declaring the supported scope. It never
means suppressing known errors, weakening tests or bypassing permissions.

### Work reordered and retained

| Work | Revised disposition |
| --- | --- |
| Finish the generic ProjectPackage exporter before any UI | **Superseded priority.** Keep the candidate; reconcile only what P0 needs, then complete packaging when it serves P5. |
| Scope-only reporting waits until every capability exists | **Reordered.** P4a follows the proven JSON round trip; other profiles still depend on their actual artifacts. |
| Complete all four schemas before building screens | **Superseded.** Evolve compatible contracts alongside demonstrated use cases. |
| OpenClaw completion/journal/transport foundations | **Completed bounded foundations** (PRs #183-#185); preserve them without making replacement work a P0 dependency. |
| Remaining capture assurance, general jobs, replacement adapter and retirement | **Separate gated backlog.** Mandatory before applicable provider deployment/retirement, unnecessary for deterministic manual P0. |
| Full technical-source lineage, broad pricing inference, all formats and edge cases | **Deferred breadth.** Do only what the selected supported capability needs; no implied source redistribution or learned-price reliability. |
| Existing domain guards, exact-byte reads, snapshot integrity, scoped review and CI | **Retained foundations.** Reuse them; avoid parallel business pipelines or regression. |
| Legacy draft PRs #9-#13 / dirty root | **Recovery context.** Do not bulk-merge or overwrite. |

### Immediate next action

Deliver **P4a: scope-only Draft PDF/XLSX reporting**, after verifying P1a
publication. The approved roadmap already permits the scope-only profile early;
this adds another useful independent capability over demonstrated saved scopes.
Use one retained, hash-bound report snapshot and reuse existing libraries/layout
patterns. Do not call estimate recalculation or fabricate priced Estimate records.

P1b remains required. Inspection found that `save_upload` leaves files pending or
not_configured and no current clean-scan producer was found; verified locked-byte
reads require PostgreSQL. Establish actual scanning, safe concurrent upload and
source-retention behavior before exposing parsed DOCX/PDF/XLSX evidence. These
prerequisites are not permission to label unscanned bytes clean for a demo. Scanner
and disposable PostgreSQL availability were not verified in this increment.

### Authoritative readiness track

The existing phase catalogue below retains its detailed domain and release exits.
Phases 8-14 gate authoritative project results, not all prototype implementation.
A validated manual artifact replaces session dependence; it does not replace
required evidence, local approval, physical locks or technical eligibility.
Library and operational gates apply when those capabilities/data are actually
exposed. Provider/customer operations, deployment and release need their existing
authorization and evidence. P0 does not require a real provider or customer file.

## 5. Authoritative phase catalogue and retained backlog

### Phase 0 - Product, repository, and change control

**Status:** In progress

**Completed foundations:** feature-branch history, explicit authority gates,
private evidence rules, GitHub pull-request workflow, packaged migrations, and
receipt/source hashes.

**Remaining:** the root checkout is conflicted recovery evidence. Exact main CI
passed on `96d6869` (PR #188); basic metadata previously reported main unprotected.
Detailed protection configuration limits were not rechecked here; do not infer
plan restrictions or bypass CI/review from that fact. Clean-machine and release
reproducibility remain incomplete.

**Exit:** every publishable change starts from clean current main, is reviewed,
passes required checks, and is traceable without secrets or customer evidence.

### Phase 1 - Domain and workflow governance

**Status:** In progress

**Completed foundations:** separate Defect, EvidenceSource, Opening, Service,
`ServiceOpeningLink`, blank-opening, protected-state, admission, submission,
receipt, and lock concepts. Synthetic sealed-submission regression coverage proves
that all-blank models remain service-free and that mixed blank/multi-service models
retain their explicit links through the canonical writer and completeness check.
The generic pre-technical path now has an attributed, audited reopen service and
`estimate:write` API route: it invalidates only an active unsigned lock, preserves
all retained physical rows, and refuses technical, commercial, rule, snapshot, or
release dependencies.
A separate no-write P-256 signed-amendment verifier now requires an active current
signed lock, a prospective canonical payload, and an exact semantically approved
visual-validation receipt. Physical lock hashes also normalise decimal display
scale so unchanged values remain stable after refresh. Its transaction-ready
no-write preflight locks and rechecks the target Estimate and lock, downstream
lifecycle dependencies, and prospective Defect ownership. An additive immutable
signed-amendment admission journal can now retain one fresh verified manifest,
canonical prospective payload, preflight receipt, and human-governance audit
event. Registration is idempotent only for the same eligible signed manifest,
rechecks every retained binding on replay, and refuses a conflicting reuse of its
amendment-admission ID or a corrupt retained record. A no-write consumption bridge now reloads an exact journal record and reruns the
locked fresh preflight. The lock service exposes the exact canonical JSON
preimage behind the existing lock hash, including Defect, evidence, Opening,
Service, and link row identities; the ordinary lock summary is derived from that
same path. A permission-gated writer now consumes the exact registered admission
in one transaction, reconciles only its approved Opening, Service, and link
payload, invalidates only the authorised signed lock, and records immutable
before/after snapshots, hashes, row mappings, execution receipt, and audit.
No-op changes, unauthorised roles, corrupt replays, and later downstream
dependencies fail closed; injected write failure proves the mutation and
invalidation roll back together. A disposable PostgreSQL two-session race test
proves a concurrent exact retry blocks and then returns the same single outcome
without a second mutation or audit event. It does not create a replacement lock or grant
technical, commercial, snapshot, release, or other downstream authority. A separate
short-lived P-256 replacement-lock manifest can now be checked by a transaction-ready,
no-write preflight. It locks the Estimate and every current physical row; rechecks the
intact amendment outcome, prior signed-lock binding, approved visual receipt, exact
amended content hash, scope-aware physical completeness, editable status, and absence of downstream dependencies; and
returns an exact no-write receipt. Changed state, expired or altered signatures, corrupt
evidence, any active lock, or later technical, commercial, rule, snapshot, or release
state fails closed. An immutable human-attributed admission journal now reruns that
locked preflight and records the exact canonical signed envelope and receipt. Exact
replay is idempotent; changed, conflicting, or corrupted evidence fails closed. A
fresh separately signed approval can follow an expired unused approval without
rewriting history. Registration creates no lock and grants no downstream authority.
A separate active-human `estimate:write` transaction now consumes one exact
registered admission only after rerunning the locked fresh preflight. It creates
the exact replacement Physical Model Lock over the unchanged approved snapshot
and records one immutable outcome plus audit event atomically. Exact completed
replay is idempotent; state drift, active-lock races, corrupt evidence, or failed
outcome/audit writes fail closed or roll back together. It performs no technical
selection, pricing, deployment, or release and grants no downstream authority.

**Remaining:** exercise the governed evidence-to-physical workflow on separately
authorised project data and satisfy the Phase 1 exit evidence. The implemented
writer does not itself authorise a real replacement-lock operation, and the current
UAT estimate still has no accepted active replacement lock.

**Exit:** physical state and amendments are service-governed, attributable,
audited, and cannot be changed by an unauthorised role.

### Phase 2 - Governed technical and commercial libraries

**Status:** In progress

**Completed foundations:** independent technical document/variant decisions,
clean-source rechecks, current approved/unexpired source-document and retained-
file metadata checks, TechnicalVariant effective/expiry checks, verified-byte
candidate extraction and Draft-only
metadata refresh after a clean-source recheck, Draft-only imports, source-bound
variants and revisions, hash-bound Draft source-document predecessor lineage, source-locator review gates, source-bound manual Draft
materialisation from clean retained documents, active immutable technical
releases, manifest eligibility checks, immutable published technical source-lineage
checks, active hash-bound pricing records, read-only current-authority visibility
on TechnicalVariant and TechnicalDocument detail screens, read-only retained
document/locator visibility for every TechnicalVariant revision, and structured
immutable source-lineage visibility on TechnicalRelease detail screens. Governed
technical publication now requires an active technical approver, includes every
current eligible active logical variant exactly once or fails closed, rechecks
exact bound source bytes, and atomically supersedes the prior release with the
new immutable manifest and audit event. A technical-only database constraint
prevents concurrent publication from leaving two active technical releases.

**Remaining:** extraction-assisted and manufacturer-neutral lineage,
clean-machine import/recovery, and full commercial rate-inclusion/recovery rules.

**Exit:** every technical/commercial decision cites an immutable authorised
release and its source cannot silently change after use.

### Phase 3 - Hybrid orchestration and controlled execution

**Status:** In progress

**Accepted target:** deterministic CLASSIFIRE commands own workflow and
authority-bearing transitions. A small CLASSIFIRE-owned coordinator persists
jobs, runs, stages, leases, retries, cancellation, safe outcomes, and audit
correlation. Optional stateless model adapters may propose evidence
interpretations or independent challenges; they do not control workflow or
write canonical state.

**Completed foundations:** role-limited no-tool proposal sessions, literal-
loopback transports, evidence rehashing, tool attestation/audit, proposal-only
receipts, admission registration, one-shot submission boundaries, and PRs
#183-#185 completion consumer/journal/optional transport lifecycle integration.

**Remaining within the separate replacement track:** extend the existing contract
characterisation and journal into only the required durable job/run/stage handling, provider-neutral
inference adapters, governed secret custody, timeout/cancellation/retry and
crash-recovery evidence, provider-egress classification/minimisation, permitted
provider/endpoint and network-allowlist enforcement, tenant/project isolation,
retention/residency policy, content-safe telemetry, cross-tenant and
confused-deputy tests, negative authority tests, historical-receipt support, and
feature-flag rollback. OpenClaw remains the current adapter until the retirement
gates in Architecture Decision 0001 pass.

**Exit:** every operation has minimum authority, safe diagnostics, exact inputs,
reproducible setup, attribution, and tested recovery; deterministic package
work remains available with all model adapters disabled; and the required
runtime no longer depends on OpenClaw.

### Phase 4 - Operational visibility

**Status:** In progress

Mission Control may mirror tasks, run/gate summaries, and links. CLASSIFIRE
remains the source of project, evidence, physical, technical, commercial,
snapshot, and release truth.

The accepted target is CLASSIFIRE-owned job/run/stage visibility. Mission
Control may remain temporarily as a read-only projection and may be retired
when the native visibility and recovery evidence are adequate. It may not own
project state, approval state, workflow truth, or command authority.

**Exit:** operational visibility is useful without a second mutable estimate
database or approval workflow.

### Phase 5 - Evidence intake and resolution

**Status:** In progress

**Completed foundations:** retained evidence, linked-original controls,
Project/Estimate ownership, exact clean-byte reads, shared-byte quarantine,
PDF text/table/annotation and drawing/image locators, strict explicitly numbered
caption locators, bounded XLSX worksheet/cell locators, bounded DOCX document/paragraph/simple-table locators, ordered scopes, explicit human-approved report-family manifests, deterministic family proposal-review aggregation of independently validated member packages, and governed five-year retention/redaction/hold/integrity-checked scoped reviewer visibility plus administrator-only immutable human-review annotations for those approved family packages,
report-aware inputs, deterministic review artifacts, and PR #103's desk-quote
exact-byte/locator/artifact-audit checks.

**Completed foundations:** expected-label manifests bound to report bytes and
estimate; atomic complete-label scope admission; V2 approval-bound packets; and
runner preflight that rejects legacy/unbound packets before a no-tool port call, and a database-backed proposal-review controller that rejects them before package assembly.

**Remaining:** support for formats beyond PDF/XLSX/DOCX and a separately authorised operator flow. Caption-to-image association and any caption-derived fact remain unsupported. Shared main supplies CLASSIFIRE-owned five-year retention, redaction, legal hold, integrity refusal, a controlled-UAT scoped reviewer surface, explicit reader grants, administrator-only immutable human-review annotations, and a service-only family runner that preflights every member before any no-tool port is created.

The accepted hybrid target also adds a distinct future `ProjectPackage`
portability boundary. The complete versioned schema, deterministic whole-project
generation and validation, immutable storage, permission-checked download,
quarantined import, lineage/conflict handling, export profiles, and signature
policy are not implemented. This must not be confused with the narrower
proposal-review package or current PDF/XLSX estimate exports.

**Exit:** every downstream claim traces to exact retained bytes and a stable
report/page/item or visual locator; expected items cannot disappear silently;
and package evidence membership, provenance, and safe-import prerequisites are
defined and proven. End-to-end package generation remains a cross-cutting track,
not a Phase 5 exit dependency.

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
8. separately authorise signing, registration, and exact replacement-lock execution.

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

**Status:** Authoritative exit blocked by Phase 8; P2 Draft/manual development is allowed

Search only the pinned authorised technical release, evaluate every relevant
physical condition, preserve mismatches/unknowns, and create one current strategy
per supported Opening. Pricing never proves suitability.

### Phase 10 - Quantity and labour

**Status:** Authoritative exit blocked by Phase 9; bounded P3 development is allowed

Derive component quantities and labour from selected systems with explicit
inputs, units, waste, rounding, procurement, access, productivity, crew, and
shared-work rules. Missing productivity fails closed.

### Phase 11 - Commercial recovery

**Status:** Authoritative exit blocked by Phases 9-10; bounded P3 development is allowed

Recover each required component once through an authorised pricing hierarchy
and explicit inclusion/recovery ledger. The desk-quote prototype remains a
parallel assumption-led allowance and does not satisfy this exit.

### Phase 12 - Independent validation and immutable snapshot

**Status:** Authoritative exit blocked by Phases 8-11; Draft artifact identity work is allowed

Snapshot V2 now keeps volatile generation metadata out of the semantic hash and
binds the complete document with a separate integrity hash; V1 snapshots remain
verifiable. Independently validate physical, technical, quantity, labour,
commercial, formula, recovery, and release integrity.

### Phase 13 - Canonical output generation

**Status:** Canonical output exit blocked by Phase 12; independent P4 Draft reporting is allowed

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

- Infrastructure/schema perfection before an interactive prototype.
- The former package-exporter-first handoff as the current next task.
- Treating the full canonical chain as a compulsory user session sequence.

- The conflicted root checkout as a publication, deployment, or bulk-merge path.
- Draft PRs #9-#13 as current-main candidates without selective reconstruction.
- PR #75 as open work; it merged at `348bce5` and remains a bounded
  proposal-only prototype, with PR #103 evidence-read hardening on shared main.
- “Obtain authority and run the approved assessment” as the immediate task; the
  one authorised attempt already occurred and failed safely.
- Building the report runner as future work; shared main already composes it.
  The remaining work is formats beyond PDF/XLSX/DOCX,
  caption-to-image association policy, and a separately authorised operator flow. Human-review annotations remain proposal-only observations.
- Site visit as an automatic first response; exhaust governed report evidence
  first and request confirmation only where materially required.
- Count equality, whole-file database hashing, or a model answer as semantic
  acceptance.
- Initial submission and Physical Model Lock as one authority.
- A persistent autonomous agent fleet as a mandatory domain or runtime path.

## 7. Roadmap-wide rules

1. Source evidence is immutable; corrections are governed amendments.
2. Canonical writes are least-privilege, audited, and receipt-bound.
3. Proposal-only testing is the default for uncertain/model-driven work.
4. Human fixtures and same-case answers remain hidden from inference.
5. Better evidence does not justify inventing concealed facts.
6. Correct abstention beats unsupported confidence.
7. Technical suitability and commercial price remain separate.
8. Shared work is commercially recovered once.
9. No authoritative downstream result bypasses an unresolved upstream gate;
   independently validated Draft prototype work is allowed within its stated limits.
10. Final release remains human-only.
11. ChatGPT, standalone, CLI, and administrative interfaces call the same
    CLASSIFIRE application and domain services; they do not duplicate business
    rules.
12. No interface, package, model, agent, prompt, or orchestration task grants
    canonical, technical, commercial, lock, deployment, or Human Release
    authority by itself.
13. AI must earn its use through measured accuracy, safety, or efficiency
    benefit; deterministic workflows remain the default.
14. OpenClaw retirement requires documented security, provider privacy/egress,
    receipt, recovery, observability, clean-machine, compatibility, and rollback
    parity, including cross-tenant and confused-deputy refusal.

## 8. Related documents

- [Product Goal](../GOAL.md)
- [Engineering Guidance](../AGENTS.md)
- [ADR 0002 - Independent Capabilities](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md)
- [Current Project State](./PROJECT_STATE.md)
- [CLASSIFIRE Architecture](./CLASSIFIRE_ARCHITECTURE.md)
- [Architecture Decision 0001 - Hybrid CLASSIFIRE Architecture](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md)
- [Current Session Handoff](./SESSION_HANDOFF.md)
- [Desk Quote Assumption Contract](./DESK_QUOTE_ASSUMPTION_CONTRACT.md)
- [Phase 8 Representative Run Package](./PHASE8_REPRESENTATIVE_RUN_PACKAGE.md)
- [Admission-Bound Writer Deployment Runbook](./ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md)
