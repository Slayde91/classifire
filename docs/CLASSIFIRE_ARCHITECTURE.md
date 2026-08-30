# CLASSIFIRE Architecture

**Document status:** Current pre-production architecture reconciled with local implementation

**Architecture version:** 3.22

**Current implementation focus:** Evidence resolution and proposal-only physical modelling for fire seals, blank openings/core holes, and service penetrations

**Deferred physical domains:** Whole-run structural-steel protection and complete fire-rated duct runs

## 1. Scope and implementation labels

This document describes the architecture CLASSIFIRE is intended to preserve and
the extent to which the local repository currently implements it. It must be
read with [PROJECT_STATE.md](./PROJECT_STATE.md) and
[CLASSIFIRE_ROADMAP.md](./CLASSIFIRE_ROADMAP.md). Executable source, tests, Git
state, and retained runtime receipts determine factual implementation status.

The status labels used here are:

| Label | Meaning |
| --- | --- |
| **Completed** | Implemented and supported by current code, tests, or execution evidence for the stated boundary. |
| **In progress** | Material implementation exists, but an acceptance condition or production proof remains incomplete. |
| **Planned** | Approved direction without a completed implementation boundary. |
| **Blocked** | An upstream evidence, governance, authority, or technical condition prevents progression. |
| **Deprecated / superseded** | Retained only for compatibility or history and not the current approved path. |

Implementation claims also identify their repository tier:

| Repository tier | Meaning |
| --- | --- |
| **Shared current-main** | Published source on the current shared `main` lineage. |
| **Branch candidate** | Coherent feature-branch work based on current main; it is not shared-main implementation unless reviewed and merged. |
| **Legacy-root evidence** | Useful later-phase or historical implementation in the materially divergent primary checkout; not a merge or deployment candidate. |

## 1.1 Audit reconciliation - 30 August 2026

The architecture remains governed by the evidence-to-human-release chain, but
repository tiers must not be confused with implementation completion.

- **Shared current-main (`b776174`)** is the active published foundation. It
  contains the PR #74 application baseline, PR #78 human-session revocation
  hardening, PR #79's recovery decision, PR #80's bounded v2 assessment/review
  contract, PR #81's contained report-evidence adapter and production-startup
  guard, and the secret-free pull-request validation workflow. Its single
  migration head is `0011_report_evidence_locators`.
- **The primary legacy checkout is quarantined source-control evidence, not a
  deployable/current implementation tier.** PR #79 records the isolated decision
  to retain the four accepted current-main conflict-path versions and not
  transplant the stale cherry-pick. The checkout itself still has an active
  cherry-pick and unmerged files, so it remains invalid for publication,
  canonical writes, or deployment.
- **The bounded report-assessment contract is shared-main source.** PR #80
  merged `efd4641` after its successful workflow run; it remains proposal-only
  and does not authorise a real report run or canonical state change.
- **The contained report-evidence adapter is shared-main source.** PR #81
  merged exact clean-byte/project ownership, stable locators, deterministic
  report review, report-bound prompt/receipt contracts, a managed no-tool
  runtime, and the disposable PostgreSQL race service. Its final CI run passed
  500 tests. No real report or provider run has been performed.
- **The cable semantics are shared-main behaviour.** A
  cable bundle's `quantity` counts bundles; a defensible individual cable count
  is separate. Without that count, a bundle may be classified small, medium, or
  large. A cable tray remains a distinct service with estimated tray dimensions.
- **Technical intake and most production hardening remain separate candidates.** The
  Draft-bound technical-intake commits (`d76562e`, `0edeaac`) and proposed
  `0019_technical_intake_materializations` migration are not on main. The
  production-boundary commit `a3de490` is also local-only. PR #81 separately
  merged only a narrow startup guard: unsafe production settings fail before
  filesystem or lifecycle writes, and production never creates schema or seeds
  an administrator. The remaining candidates do not change shared-main
  architecture until separately reviewed and published.

### Architecture follow-up required

Before any report assessment, obtain separate authority for the controlled
proposal-only run and human review. PR #81 has already been independently
reviewed and its disposable PostgreSQL containment race passed in CI. The
adapter extends the merged contract and must not create a competing path.

1. Keep the completed contained adapter limited to project-owned, hash-bound
   proposal evidence; a controlled report run remains a separate authority.
2. Keep storage ownership, containment, package preparation, inference, API, and
   UI as reviewable layers. Do not transplant the broad report-context or dirty
   technical-intake continuation wholesale.
3. Continue technical-intake normalization/materialization only after its shared
   containment dependency is reconciled as a separate migration boundary.
4. Reconcile production bootstrap and security hardening from `a3de490` on
   current main as a separate change, preserving all existing authority gates.
5. Keep report-derived inference, human review, canonical submission, Physical
   Model Lock, technical approval, commercial approval, and Human Release as
   separate authorities.

## 2. Product purpose and governing order

CLASSIFIRE is a passive-fire evidence analysis, physical modelling, technical
decision-support, quantification, estimating, and close-out platform. Its hard
reasoning order is:

```text
Project Evidence
-> Defects
-> Services and Assets
-> Openings
-> Substrate Planes
-> Physical Model
-> Repair Components
-> Technical System Search
-> Compatibility Validation
-> Commercial Applicability
-> Quantity and Labour
-> Reconciliation
-> Estimate, Scope, and Close-out
-> Human Release
```

Physical reality is modelled before technical selection or commercial pricing.
A report row, Defect, photograph, Opening, Service, repair component, and
commercial line are separate concepts. One Defect does not imply one Opening,
one Service, or quantity one.

## 3. Authority and source of truth

CLASSIFIRE's governed database is canonical project state. OpenClaw sessions,
Mission Control task text, prompts, model output, chat history, local package
files, and temporary receipts are not canonical estimate state.

For the current human-governed deployment, authority is resolved in this order:

1. platform security and system policy;
2. the CLASSIFIRE Constitution, ontology, and active governed profiles;
3. retained Project evidence and explicit evidence confidence;
4. the current canonical and locked Physical Model;
5. pinned technical, product, labour, pricing, rule, and markup releases;
6. independent validation and immutable snapshot evidence; and
7. competent human approval of the exact release artifacts.

No proposal, inference result, UAT package, source hash, Gate receipt, external
signature, or approval for one operation silently grants authority for a later
operation. Canonical submission, Physical Model Lock, deployment, technical
approval, commercial approval, and Human Release remain separate boundaries.

## 4. Current repository composition

### 4.1 Shared current-main foundation - Completed for its stated boundary

Shared current-main contains the active Phase 8 foundations:

- FastAPI, CLI, SQLAlchemy, and Alembic infrastructure;
- the current Opening, Service, and Opening-Service relationship model;
- the reconciled admission lineage through
  `0008_retire_legacy_initial_submissions`; and
- the additive durable visual-validation receipt migration
  `0009_visual_validation_receipts`;
- component-level protected-state fingerprinting;
- proposal-blind visual inventory and mandatory reconciliation;
- bounded Validator-to-Physical correction and strict proposal receipts;
- retained visual-evidence adaptation;
- guarded linked-original discovery, retrieval, and retention;
- strict `site_observation` evidence intake at the existing evidence-registration
  boundary, with one-Defect binding, immutable source checks, per-fact locators,
  explicit uncertainty and limitations, and an audit-bound payload digest;
- literal-loopback, no-tool OpenResponses transport and dedicated Physical and
  Validator runtime identities;
- a validation-only post-inference human-reference comparator;
- the bounded linked-original-to-proposal runner; and
- immutable admission registration and one-shot initial submission without lock
  creation.

These are completed foundations, not completion of Phase 8 or production
readiness.

### 4.2 Shared-main representative-run implementation - Completed for its stated boundary

Shared current main also includes:

- a strict, approval-bound representative-run package;
- deterministic binding to the checked-out Git revision and executable source
  tree, including uncommitted candidate bytes;
- disposable SQLite and storage-snapshot execution with mandatory rollback
  verification;
- no-write Gateway readiness checking and a loopback protocol fallback when the
  installed CLI cannot provide the required RPC;
- full-report linked-original verification followed by defect-scoped retention
  and inference;
- stricter visual prompts, correction authority, evidence filtering, and receipt
  validation;
- content-safe evidence-review requests for a blocked Validator outcome; and
- fully local recovery of a blocked review request from retained receipts and
  session transcripts.

The representative run has been executed once against an explicitly approved
retained report. Retrieval and rollback boundaries behaved as designed, but the
independent Validator blocked the proposal because material physical facts could
not be established from the governed evidence. This is valid fail-closed
behaviour. It is not an approved Physical Model.

### 4.3 Legacy-root later-phase evidence - In progress and not consolidated

The materially divergent primary checkout contains guarded foundations for
technical search and Repair Strategy, components and labour, commercial
recovery, independent validation, immutable snapshots, richer outputs, and
human-only release. Focused tests exercise much of that chain.

Those foundations are legacy-root evidence only. They are absent or materially
different on current main, use a superseded model/API/migration composition in
places, and must not be merged wholesale. Any useful capability must be
reconciled phase by phase onto current main with its own review, migrations,
tests, and acceptance evidence.

## 5. System layers

### 5.1 CLASSIFIRE application and domain services

CLASSIFIRE owns canonical projects and estimates, retained evidence provenance,
Defects, Openings, Services and links, locks, technical decisions, required
components, quantities, labour, commercial recovery, validation gates,
snapshots, outputs, approvals, and immutable library-release pins.

All state-changing operations pass through role-scoped services. A narrative
status or model answer is never a database write, lock, validation receipt, or
approval.

### 5.2 OpenClaw

OpenClaw provides controlled inference sessions, model routing, workspace/tool
policy, and audit evidence. Visual roles may inspect governed evidence and
return strict proposals or challenges. They may not directly submit canonical
data, create a lock, approve a technical system, approve a commercial method, or
release an estimate.

The proposal path uses separate configured Physical and Validator identities.
Both must have empty effective tool inventories for the run. The client sends no
tools and rejects tool calls, redirects, model/profile drift, changed evidence
bytes, malformed responses, and unavailable post-turn audit evidence.

### 5.3 Mission Control

Mission Control is a task, review, and operational visibility plane. It may
mirror run, gate, test, and release summaries. It must not become a second
estimate database, technical library, pricing authority, workflow state machine,
or release authority.

### 5.4 Human authority

Competent humans own source-library approval, material evidence exceptions,
technical and commercial approvals where required, and final Human Release.
Human decisions must bind to exact governed records, hashes, and reasons.

## 6. Evidence architecture

### 6.1 Retained source evidence

Every material source is retained as a governed container with file identity,
hash, page/region context, extraction method, and provenance. Extracted text is
not a substitute for visual review when photographs, drawings, tables, or page
layout affect the physical interpretation.

Evidence values retain explicit states such as Confirmed, Inferred,
Provisional, and Unresolved. Unknown must not silently become zero, absence,
quantity one, a service class, a material, or a dimension.

### 6.2 Linked originals

The linked-original boundary restricts approved hosts, resolved network
addresses, TLS, redirects, paths and query keys, MIME type, byte size, pixel
count, dimensions, and run time. A retrieved image is accepted only after it is
visually bound to the report-provided image and proves usable additional detail.

Current-main retention normally binds the verified original to an active parent
thumbnail. The shared-main implementation also supports report-derived parent
evidence only when the immutable PDF hash, page, photo identity, native
dimensions, and crop bounds all match. Content-addressed bytes and redacted
provenance are retained without committing the caller's transaction.

Lower-resolution page context, annotations, and alternate views remain relevant
when they contain information not present in the linked original. Photograph
count never becomes Opening or Service quantity.

### 6.3 Full-report retrieval versus defect-scoped inference

The representative package verifies retrieval requirements across every reviewed
photo row in the approved report. This protects against silently validating only
the easiest linked image.

Retention and inference are narrower. The runner selects only verified originals
whose governed parent evidence belongs to the one requested Defect. Its packet
allowlist contains only those current retentions and the ready parent evidence
IDs explicitly named by the approved package mapping; any other same-Defect
visual row is excluded. The managed inference runtime starts only after this
bounded packet exists. Therefore:

- full-report retrieval success does not prove full-report physical modelling;
- one representative Defect result does not prove multi-defect generalisation;
- report-wide image counts do not become defect-level topology or quantity; and
- parents belonging to other Defects and unlisted same-Defect visual evidence are
  not exposed to the selected inference.

Active nonvisual evidence may remain in the database but is excluded from the
visual packet unless it carries the explicit governed visual metadata contract.

## 7. Proposal-only visual architecture

The controller executes an ordered, independently bound sequence:

```text
Blind Validator inventory
-> Physical proposal
-> Conditioned Validator review
-> Optional bounded correction
-> Approved, Blocked, or Failed receipt
```

The blind inventory cannot see the proposal or a human answer key. The Physical
role cannot see the blind inventory. Human-reference material is validation-only
and never provided to inference.

The schemas enforce separate Openings and Services, explicit links, exact blank
opening types, unique candidate identifiers, explicit uncertainty, governed
Validator issue codes, and complete blind reconciliation. Correction authority
is field-specific. An issue authorising a quantity correction does not authorise
an unrelated substrate, material, topology, or relationship change.

Approved and blocked controller receipts bind the final blind inventory,
proposal, and Validator payload hashes to the corresponding final inference
stages. Protected state is checked throughout the run. Any unexpected state
change, tool exposure, structural authority escape, malformed result, or hash
substitution fails closed.

### 7.1 Post-inference human adjudication boundary

Human evidence decisions remain a separate, post-inference provenance record.
They must bind the exact review request and proposal lineage, account for every
requested item, preserve unresolved outcomes, and remain invisible to runtime
inference. A human-adjudicated proposal may record a limited physical
interpretation, but it is not a visual approval receipt, canonical submission,
Physical Model Lock, technical selection, quantity completion, or release.

The retained v2 review for the selected representative Defect demonstrates this
boundary as local execution evidence: all seven review items and four unresolved
observations are accounted for, and the visible topology is represented as five
Openings, six Services, and six links. Report-evidence-limited dimensions, depth
and obscured boundaries, exact substrate composition, labels/material proof,
and opposite-face continuity remain unresolved. The provenance and evidence-family
review validators are on shared main. The retained v2 response remains local
human-review evidence; it is neither canonical state nor publication authority.

### 7.2 Property assessment and proposal review - Merged shared-main foundation

Shared main has a strict v2 property-assessment layer without changing
canonical persistence:

```text
Evidence manifest
-> v2 Physical proposal with property assessments
-> independent Validator and bounded correction
-> proposal-only controller receipt
-> hash-bound JSON review
-> inert Markdown human review
```

Every declared opening, service, and substrate property has an assessment. A
value is Confirmed, Approximate, Inferred, or Unknown; Approximate and Inferred
values carry confidence; all non-Unknown conclusions retain reasoning and
allowed-manifest evidence references. Measurements may use defensible ranges,
and credible alternatives remain explicit. Additional evidence is requested
only when required, not automatically for every Unknown value.

The proposal schema rejects undeclared technical-system, product, commercial,
canonical, lock, and release fields. Fresh runs use the exact v2 prompt/runtime
profile and v2 receipt pairing. Historical v1 prompt bytes and paired v1
policy/receipt records remain verifiable, but a v2 result cannot be relabelled
as v1. Review status and proposal outcome are cross-checked, and invalid,
insufficient-evidence, or no-proposal cases cannot be relabelled as successful.

The merged report adapter now binds general documentary report evidence and
emits deterministic review artifacts for selected report Defects, including
retrieval-blocked and insufficient-evidence outcomes. It does not weaken the
v2 contract or grant canonical persistence authority.

## 8. Trusted-UAT representative package

### 8.1 Approval metadata

The package is executable only when it records all of the following trusted-UAT
metadata:

- a non-empty approval reference, approver, and UTC authorisation time;
- the exact `rollback_only_linked_visual_proposal` scope;
- the approved report SHA-256 and the exact configured retrieval-host allowlist;
- the target estimate, representative Defect, and operator references;
- the expected 40-character Git revision and source-tree SHA-256; and
- explicit policy flags requiring rollback, forbidding canonical submission and
  lock creation, and hiding the human reference from inference.

This metadata authorises only the bounded representative proposal run. It does
not authorise a fresh canonicalisation preflight, external signing, admission
registration, canonical submission, Physical Model Lock, deployment, pricing,
or release.

### 8.2 Source and input binding

The deterministic source-tree fingerprint covers Python/JSON/TOML files under
`src/classifire`, the representative package runner, and `pyproject.toml`. Git
pins those Python, JSON, and TOML inputs to LF line endings, making the raw-byte
fingerprint reproducible across clean checkouts. The hash binds the exact
executable candidate even when the Git base revision is unchanged and the
worktree contains reviewed uncommitted changes.

All package inputs must resolve inside the package directory. Duplicate JSON
keys, non-finite values, absolute paths, parent traversal, report-hash drift,
source drift, malformed human-reference material, wrong parent evidence, or a
non-empty target Physical Model stop execution before the unsafe downstream
boundary.

### 8.3 Gateway readiness and inference boundary

Preflight checks that a Gateway token is available but does not retain or report
it. The only readiness RPC describes a fixed nonexistent session key; it creates
no session and performs no inference or retrieval.

The runtime first uses the explicit local CLI RPC adapter. If that CLI is
unavailable, the shared-main implementation may use the same authenticated Gateway
protocol directly over a literal-loopback WebSocket. The fallback does not allow
remote hosts or broaden the RPC/parameter allowlist. Runtime sessions and model
requests remain subject to the existing no-tool guard.

### 8.4 Rollback and filesystem-write boundary

`rollback-only` does not mean that no bytes are ever written. The authorised run
may write only to disposable package-controlled locations:

- downloaded linked originals in the disposable retrieval root;
- content-addressed evidence bytes in the disposable storage snapshot;
- temporary retained-evidence rows inside the disposable SQLite transaction;
  and
- content-safe receipts in the new output directory.

The runner starts an explicit outer SQLite transaction before retention and
rolls it back even when validation blocks or inference fails. It then expires
ORM state and proves that protected counts and the component-level fingerprint
match the pre-run state. Database rows created for temporary retained evidence
must therefore disappear after rollback.

Rollback does not delete permitted disposable filesystem bytes or output
receipts. Those artifacts are evidence of the run and must remain outside live
canonical storage. The runner performs no database commit, canonical physical
submission, or Physical Model Lock.

## 9. Blocked review and offline recovery

### 9.1 Evidence-review request - Completed candidate capability

When a structurally valid Validator returns `BLOCKED`, the candidate can emit a
content-safe evidence-review request. It binds the controller and proposal file
hashes, carries supported structured issues and unresolved blind observations,
and asks a human to resolve each item against retained or newly governed
evidence.

The sanitizer rejects credentials, capability-bearing URLs, control characters,
unsafe identifiers, and unbound artifact hashes. A blocked request is a review
handoff, not a correction, approval, canonical proposal, lock, or pricing
instruction.

### 9.2 Offline recovery - Completed with explicit limitations

If an earlier blocked run predates the review-request writer, the local recovery
tool can reconstruct the request without rerunning inference. It requires the
approved package, no-write completion and representative receipts, controller
receipt, proposal, deterministic session keys, session-index records, and the
single assistant JSON payload for every successful stage. It validates hashes,
stage identities, and final blind/proposal/Validator domain schemas before
writing exactly the review request and recovery receipt to a new directory.

Recovery does not open the retained report or linked-original files and performs
no retrieval, inference, Gateway call, human-reference comparison, canonical
submission, lock, or pricing action. It does read the bound local session
transcripts, which can contain prior prompt content.

The proof is deliberately limited. Local OpenClaw session history is mutable,
and recovery does not replay Gateway authentication, runtime tool attestation or
audit, OpenResponses response identity, or external transport. It proves local
correspondence among retained artifacts and transcript payloads, not an
immutable third-party execution ledger.

## 10. Canonical physical model

The current physical-model scope is:

```text
Defect
  -> EvidenceSource
  -> one or more Openings
       -> zero Services for an explicit blank opening or blank core hole
       -> one or more Opening-Service Links when services are present
```

An Opening is the aperture or bounded penetration condition. A Service is a
physical pipe, cable, conduit, duct, or other item passing through it. A Service
is optional at Opening level. Placeholder Services are prohibited.

A lock candidate must retain defensible barrier/substrate, plane, orientation,
opening classification, FRL or governed assumption, service identity and
quantity, relationship provenance, and explicit limitations. Evidence that
cannot establish a service class, quantity, material, dimension, opening
relationship, or opposite-face continuity remains unresolved rather than being
invented to make the model complete.

The representative Validator's blocked outcome means no current proposal has
passed this completeness boundary. The historical adjudicated no-write proposal
and its canonicalisation preflight remain historical evidence only.

## 11. Admission-bound canonicalisation and lock separation

Shared current-main supports immutable admission registration and one-shot
initial physical submission. A fresh admission must bind the exact estimate,
normalized payload, protected state, proposal/preflight evidence, policy and
implementation identities, issuer/key, purpose, and short expiry. The writer
rechecks all bindings in the submission transaction and consumes the admission
once.

Registration records authority; it is not a canonical write. Initial submission
cannot create a Physical Model Lock. A separately designed, reviewed, signed,
and authorised lock-admission boundary is required before a replacement lock can
exist.

The durable visual-validation receipt registry is a separate, immutable
evidence boundary. It normalizes and hash-binds the exact reviewed candidate,
controller receipt, evidence manifest, family inventory and reviewed family
record, human request and response, policy versions, and review decision. Its
side-effect-free verifier
can prove that an exact semantically approved receipt is bound to a future lock
candidate, but it neither creates a lock nor grants lock-admission authority.

The current real-report path is blocked before these boundaries because its
representative visual proposal is not approved. Even after the evidence blocker
is resolved, external signing, registration, exact submission, and lock creation
remain separately authorised operations.

## 12. Technical, quantity, commercial, and release architecture

Shared current-main already contains basic technical-candidate search, pinned
release records, estimating-rule and line calculation, snapshot locking, and
PDF/XLSX rendering. Those foundations do not complete the target chain below.
Richer guarded end-to-end implementations exist only as legacy-root evidence and
must be reconciled selectively rather than treated as current-main completion.

### 12.1 Technical authority - Basic shared foundation; richer legacy foundation; blocked

Technical selection is Opening-specific and uses immutable releases in the
CLASSIFIRE Technical Authority Registry. Commercial pricing cannot prove
technical suitability. Every candidate must preserve its source, release,
system/variant identity, matched attributes, unknowns, mismatches, dependencies,
and exclusions. Unsupported conditions remain unresolved.

The complete guarded selection and Repair Strategy Lock path is legacy-root
evidence and is not consolidated on current main. It is also blocked for the
current estimate because there is no approved, canonical, locked Physical
Model.

Current-main technical approval is only a basic prototype boundary: a Draft or
In Review variant can be activated directly, requester and decider separation is
not enforced, and source/page evidence is not a full governed authority
registry. There are no current-main `tests/test_technical*` files. The
Draft-bound approval, revision, and shared containment candidate must therefore
be reviewed and tested before technical records are production-trusted.

### 12.2 Components, quantities, and labour - Basic shared calculation; richer legacy foundation; blocked

A selected technical variant generates distinct required components and labour
activities. Quantity retains inputs, units, waste, rounding, and procurement
rules. Labour retains its quantity driver, crew, governed productivity source,
adjustments, and hours. Missing productivity fails closed. Shared work is
recovered once. Current-main line calculation does not yet provide this complete
system-derived component and productivity chain.

### 12.3 Commercial recovery - Basic shared rules; richer legacy foundation; blocked

Commercial selection follows the physical and technical model. Each required
component receives one governed pricing basis. Shared batt, closure, access,
framing, mastic, or labour is added only when it is not already recovered or is
genuinely separate work. Analogue pricing remains benchmark-only unless a
governed rule expressly permits otherwise. Current-main estimating rules do not
yet implement the complete rate-inclusion/recovery ledger.

### 12.4 Validation, snapshot, output, and Human Release - Basic shared outputs; richer legacy foundations; blocked

Independent validation must prove physical, technical, quantity, labour,
commercial, formula, recovery, and release integrity. Passing state is frozen
as an immutable reproducible snapshot. Output renderers may render that snapshot
but may not recalculate or reinterpret scope.

Human Release remains human-only and must accept the exact snapshot and output
hashes. Current-main snapshots and renderers remain basic and retain legacy
compatibility names; they are not full validation certificates or Human Release.
The snapshot builder also includes the current generation timestamp in the
hashed payload and has no snapshot-focused regression suite, so reproducible
snapshot identity is not yet proven. The current estimate has no eligible
downstream state.

## 13. Security and confidentiality

Report evidence, linked URLs, credentials, tokens, private signing keys,
commercial source data, and governed technical material remain within their
approved storage and execution boundaries. Prompts, receipts, logs, review
requests, and documentation must not disclose secrets, local storage paths, or
capability-bearing URLs.

The offline admission key and APK release-signing identity are separate trust
objects. Neither private key belongs in CLASSIFIRE source, configuration,
receipts, or documentation.

Current-main production startup now fails closed before it creates storage,
schema, or a default administrator. Production requires a non-default secret
and administrator password, HTTPS-only sessions, and PostgreSQL; it never
calls `create_all()` or seeds an administrator. This branch has a separate,
validated but unmerged candidate that packages the immutable Alembic history,
exposes an explicit installed upgrade command, and refuses production CLI
setup/import commands before they can create schema or seed defaults. Shared
main still lacks those boundaries, and live deployment proof and the remaining
broader hardening work are still pre-production boundaries. Project-owned
report intake, clean-only evidence use, and atomic quarantine are source and
CI-proven; they are not deployment or live-report proof.

## 14. Current architecture status

| Area | Status | Current boundary |
| --- | --- | --- |
| Application, persistence, and current migration lineage | **Completed foundation** | Shared current-main; pre-production |
| Linked-original retrieval and governed retention | **Completed foundation** | Shared current-main; approved hosts/report formats remain narrow |
| Site-observation evidence intake | **Completed contract** | Shared current-main; evidence registration only, with no Physical Model write or lock authority |
| Proposal-only visual controller and no-tool runtime | **Completed foundation** | Shared current-main; production persistence/generalisation incomplete |
| Property-assessment and proposal-review contract | **Merged shared-main foundation** | PR #80 merged `efd4641`; the contract remains proposal-only, with no canonical-write interface |
| Trusted-UAT package and rollback proof | **Completed shared-main capability** | Representative run executed; source and receipt package are merged |
| Representative physical proposal | **Reviewed with limitations / non-canonical** | Human review records a local 5/6/6 proposal-only topology; report-evidence-limited facts and independent semantic approval remain unresolved |
| Content-safe evidence review and local recovery | **Completed shared-main capability** | Recovery proof has documented mutability/replay limits |
| Report storage ownership and malware containment | **Merged shared-main / pre-production** | PR #81 binds StoredFiles to Project/Estimate evidence and verifies clean-byte reads; its disposable PostgreSQL quarantine-race test passed in CI |
| Canonical Physical Model for the current estimate | **Blocked** | No approved proposal or separately authorised submission |
| Replacement Physical Model Lock | **Blocked** | Separate signed lock-admission design and authority required |
| Technical authority | **Basic prototype / blocked** | Current main lacks enforced approval-role separation and focused technical tests; governed candidate work is not merged |
| Snapshot and Human Release | **Basic prototype / blocked** | Snapshot reproducibility and full validation certificate are not proven; upstream Physical Model gate unresolved |
| Production bootstrap and security gates | **Merged limited hardening plus unmerged CLI/migration candidate** | Main rejects unsafe production settings before filesystem or lifecycle work and suppresses production `create_all`/seed; this branch packages immutable migrations, adds an explicit upgrade command, and blocks production CLI setup/import seeding, but deployment proof and the remaining `a3de490` scope are still unreviewed |
| Continuous integration | **Established on shared main** | The secret-free pull-request workflow passed for PR #80 and the final PR #81 head, including the disposable PostgreSQL race |
| Evidence-family taxonomy and multi-report accuracy | **In progress** | One approved source and representative Defect do not prove generalisation |
| Governed accuracy/learning programme | **Planned** | No training before the roadmap admission gates |
| Structural-steel and full duct-run domains | **Planned / deferred** | Separate schemas, libraries, calculators, and acceptance evidence required |
| Whole-file database hashing and count-only acceptance | **Deprecated / superseded** | Replaced by component fingerprints and semantic/evidence-backed validation |
| Generic writer or same-operation lock creation | **Deprecated / superseded** | Replaced by admission-bound one-shot submission and separate lock boundary |
| Wholesale legacy-branch merge | **Deprecated / superseded** | Use bounded phase-specific reconciliation from current main |

## 15. Next valid architectural action

The next repository action is a separately authorised, controlled,
proposal-only report assessment followed by human review. The assessment
contract and contained report-evidence adapter are already merged; that does
not authorise technical selection, pricing, canonicalisation, locking,
deployment, or release.
The ordered boundary is:

1. atomically bind malware state and content hash to the bytes read or served,
   propagating unsafe shared-byte state across every referencing row;
2. bind each report and generated package to its Project or Estimate and reject
   cross-project access;
3. give report text, tables, captions, drawings, annotations, metadata, page
   context, and governed images stable report/page/item locators;
4. generate exactly one review artifact for every selected report-labelled
   Defect, including deterministic retrieval-blocked, malformed, and
   insufficient-evidence outcomes; and
5. bind each review to its report/package, manifest, prompt/runtime profile,
   proposal, and controller receipt; make the later completion receipt hash
   every preceding emitted artifact; and prove protected state is unchanged.

This work may require one small additive ownership migration. It must not expose
the broad candidate UI, select a technical system, price work, write a canonical
model, create a lock, deploy, or release. A site visit remains conditional only
after report evidence is exhausted or a later governed decision requires
confirmation.

The receipt verifier remains a no-write pre-lock check, not signed lock
admission. Submission, lock creation, technical selection, pricing, output,
deployment, and Human Release retain their separate gates.
