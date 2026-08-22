# CLASSIFIRE Architecture

**Document status:** Current pre-production target architecture reconciled with implementation

**Architecture version:** 3.17

**Application release basis:** CLASSIFIRE v2.13 runtime

**Current implementation focus:** Fire seals, blank openings/core holes and service penetrations

**Deferred domains:** Whole-run structural-steel protection and complete fire-rated duct runs

## 0. Implementation scope and status

This document defines the architecture that remains valid and records where the
repository has or has not reached it. It must be read with
[`PROJECT_STATE.md`](./PROJECT_STATE.md) and the roadmap. Current executable
code and tests determine implementation status; this document does not turn a
designed component into an operationally complete phase.

| Architecture area | Repository evidence | Current status |
| --- | --- | --- |
| Core application | FastAPI, server-rendered UI, Typer CLI, SQLAlchemy and Alembic | Completed foundation; pre-production |
| Evidence and physical proposal | Report/image runners, linked-original resolution, provenance and visual challenge | Completed for the controlled UAT path; generalisation in progress |
| Canonical physical model | Opening/Service/link models, scope-aware lock service and admission-bound initial submission | In progress; current UAT has no canonical model or active lock |
| Technical through Human Release | Guarded services, persistence and reference-fixture tests | Implemented foundations; blocked for the current UAT by the missing Physical Model Lock |
| OpenClaw/Mission Control | Role-scoped API/plugin contracts and Mission Control client/bootstrap | In progress; live reproducibility and deployment proof incomplete |
| External admission signer | Offline Android signer exists on shared `main` | Implemented and bounded; not present in this checked-out branch and not proof of an admission |
| Production operation | Security settings and fail-closed gates exist | In progress; clean deployment, recovery, performance and monitoring gates incomplete |

### 0.1 Repository divergence that affects architecture

The checked-out branch uses records spread across `models.py`,
`canonical_models.py` and `commercial_models.py`. Shared `main` contains the
newer admission lineage around `physical_models.py`. Both expose related
physical concepts, but they are not interchangeable source trees and must be
reconciled through reviewed changes rather than a wholesale branch merge.

The application also registers guarded phase-specific routers before an
overlapping legacy v1 router. Ordering protects the newer hard gates in known
duplicate paths, but the public API remains a compatibility composition rather
than one fully consolidated service surface. Legacy routes and models are
therefore compatibility debt, not a second approved architecture.

## 1. Product purpose

CLASSIFIRE is a passive-fire estimating and technical decision-support system produced and developed by Ceasefire PFP. Its governing transformation is:

```text
Evidence
→ Observation
→ Interpretation
→ Physical Model
→ Engineering Requirement
→ Repair Strategy
→ Component and Labour Model
→ Commercial Pricing and Recovery
→ Independent Validation
→ Validated Snapshot
→ Output
→ Human Release
```

Pricing availability must never determine physical reality or technical applicability. A defect row, photograph, Opening, Service, repair component and pricing line are separate canonical concepts.

## 2. Current authority hierarchy

For the current human-governed NSW/ACT deployment, conflicts are resolved in this order:

1. platform safety, security and system policy;
2. CLASSIFIRE Constitution and canonical ontology;
3. active runtime, jurisdiction, organisation and commercial profiles;
4. the CLASSIFIRE Knowledge Release Manifest and routing controls;
5. confirmed Project evidence;
6. the estimate's locked physical model;
7. the estimate's pinned Technical Authority Registry release;
8. the estimate's pinned pricing, product, labour, rule and markup releases;
9. authorised user instructions that do not bypass a higher authority;
10. validated snapshot and Human Release controls.

The autonomous profile provisions contained in parts of the v2.13 source corpus are dormant unless an autonomous profile is explicitly selected, validated and approved before Project processing. The current implementation retains Human Release as human-only.

## 3. System layers

### 3.1 CLASSIFIRE application and domain service

The CLASSIFIRE application owns:

- canonical Project and estimate records;
- evidence provenance;
- Defects, Openings, optional Services and Service–Opening Links;
- physical and repair locks;
- technical candidates and system-derived components;
- quantities, labour, prices and recovery records;
- validation gates, snapshots, certificates and outputs;
- library revisions and immutable release manifests.

The database is the system of record. Chat transcripts, agent memory and Mission Control task text are never authoritative Project state.

The implemented application includes both human-facing and role-scoped agent
APIs for later workflow stages. Their presence is deliberate reuse of one
domain service layer, but operational eligibility is always derived from
persisted gate records. For the current Phase 8 estimate, a read-only database
check found no canonical physical model, downstream strategy, snapshot or
release approval; the later services therefore remain inaccessible through the
workflow guards.

### 3.2 OpenClaw

OpenClaw provides model execution, agent workspaces, tool policy and runtime sessions. Models may extract, classify, compare, estimate, propose and challenge. They may not directly approve, release, change authority or overwrite canonical records.

Current specialist roles:

- `cf-orchestrator`
- `cf-intake-evidence`
- `cf-physical-model`
- `cf-technical-system`
- `cf-commercial-engine`
- `cf-validator`
- `cf-output`
- `cf-library-governance`
- `cf-platform-governance`

Every state-changing agent action must use a role-scoped CLASSIFIRE service contract. Generic database writes and generic Human Release tools remain prohibited.

The current local controlled-write plugin is version `0.5.0`. Its default
`phase8-admission-only` profile registers only
`classifire_submit_initial_physical_model` for `cf-physical-model`; broader
tools remain inactive source inventory. The profile is not proof that a loaded
Gateway is running that artifact or that the role has the required persisted
credential scope.

### 3.3 Mission Control

Mission Control is the programme, task, review and operational control plane. It may mirror stage, run, agent, gate and release receipts. It must not become:

- the technical library;
- the pricing library;
- the canonical workflow state machine;
- the final release authority.

### 3.4 Human authority

Competent humans own library approval, material exceptions and Human Release. Approval must reference exact immutable records, snapshot hashes and output hashes.

## 4. Hard workflow order

```text
Evidence intake
→ Physical modelling
→ Physical Model Lock
→ Opening-specific technical search
→ Repair Strategy Lock
→ System-derived component generation
→ Quantity and labour derivation
→ Commercial pricing and recovery
→ Independent validation
→ Validated snapshot
→ Output rendering
→ Human Release
```

A failed gate returns the estimate to the earliest owning stage. Narrative status text is never a lock, validation receipt or approval.

Where an estimate has no current canonical Opening, Service, or
Service-Opening Link records, initial canonicalisation is an additional
controlled transition before the Physical Model Lock. The required sequence is
a hash-bound proposal-only preflight, fresh external P-256 admission,
immutable admission-journal registration, same-transaction protected-state
recheck, and exact initial canonical submission. Registration records
authority only; it is neither a canonical submission nor a lock.

## 5. Evidence architecture

CLASSIFIRE reviews each material source as a container and preserves file hash, page, region, photograph and extraction method. For reports containing photographs:

- extracted text is not a substitute for page review;
- complete page layout is retained;
- native-resolution images are extracted where available;
- zoomed crops are used when detail is inadequate;
- header, footer and decorative images are classified as non-scope;
- exact visual duplicates are analysed once but every occurrence remains available for placement provenance;
- photographs of the same item from different angles or opposite barrier faces are reconciled before quantity is established;
- photograph count never becomes Service or Opening quantity.

Evidence must distinguish confirmed, stated, inferred, provisional, assumed, unresolved and rejected values. Unknown must not silently become zero, absence or quantity one.

Where report text does not state a physical field, defect-linked photographs and page layout may provide the basis for a provisional/inferred assumption. For the current fire-seal workflow this expressly includes substrate type, substrate plane and orientation. The assumption and its visual basis must remain visible; a photo-derived assumption is not a confirmed Project fact.

## 6. Current physical model

The current production-candidate conformance scope is:

```text
Defect
  ├── EvidenceSource
  └── Opening
        ├── zero Services when explicitly a blank opening/core hole
        └── one or more ServiceOpeningLinks → Services when services are present
```

The canonical distinction is critical:

- **Opening** is the physical aperture or bounded penetration condition.
- **Service** is an actual pipe, cable, conduit, duct or other service that passes through an Opening.
- A Service is therefore optional at Opening level.

A Defect may contain:

- one service penetration;
- multiple service penetrations;
- one or more blank apertures;
- one or more empty/redundant core holes; or
- a combination of service penetrations and blank openings.

CLASSIFIRE shall never create a placeholder Service merely to satisfy a database relationship or workflow gate.

### 6.1 Canonical opening types for the current scope

Current fire-seal physical modelling uses:

- `service_penetration` — one or more actual Services are linked;
- `blank_opening` — no Service is present and the aperture itself requires sealing;
- `blank_core_hole` — an empty/redundant core hole requires sealing.

`blank_opening` and `blank_core_hole` may validly contain zero Services. A service-free Opening that is not explicitly classified as blank remains incomplete and must fail closed.

### 6.2 Physical Model Lock completeness

Every Opening must have, from source evidence or a visible provisional assumption where permitted:

- substrate type;
- substrate plane;
- orientation;
- FRL or the governed current-scope FRL assumption.

Relationship completeness is then scope-sensitive:

- `service_penetration` requires at least one `ServiceOpeningLink`;
- `blank_opening` and `blank_core_hole` require no Service link;
- a blank Opening with a linked Service is contradictory and must be resolved before lock.

For the current fire-seal and penetration scope, rational AI best estimates may also be used for unknown service size or quantity when report text and visual evidence provide a defensible basis. Such values must be labelled provisional or inferred, carry reduced confidence and retain the estimation basis.

### 6.3 FRL policy for the current scope

For service penetrations, blank openings/core holes and fire seals:

- use the Project/source FRL when supplied;
- when no FRL is supplied, apply `-/120/120` only as an estimating assumption;
- record that the FRL was not supplied and must be verified before technical approval or Human Release;
- the assumption does not create a confirmed technical-system match.

Asset-sensitive FRL rules for structural steel and complete fire-rated duct runs are recorded for later implementation and do not expand the current conformance scope.

### 6.4 Admission-bound initial canonicalisation

The private signing key remains outside CLASSIFIRE in the approved external
keystore. A stale, rejected, or expired admission must not be reused. Direct
database writes or a bypass of the admission journal are prohibited.

The local migration graph converges on
`0007_reconcile_adjudicated_admission_lineages`. The local writer verifies a
short-lived P-256 admission, immutable admission registration, an exact
preflight/payload/protected-state binding, same-transaction state recheck,
single-use consumption and idempotent submission receipt. It cannot create a
Physical Model Lock. Focused tests and a disposable-copy rehearsal support the
boundary, while the source database remains unchanged.

The current 17-Opening/24-Service/24-link proposal has only a no-write v6
preflight. An immutable read-only database check confirms zero canonical
Openings, Services, links, admissions, submission receipts and active Physical
Model Locks for that estimate. The proposal is not canonical.

Shared `main` contains a reconciled admission-writer lineage and a read-only
deployment-candidate auditor, but its clean candidate is missing the required
compiled plugin artifact. The auditor therefore returns
`LOCAL_CANDIDATE_REQUIRED_ARTIFACT_MISSING`. The compiled artifact in this dirty
divergent checkout is not a substitute. Deployment/runtime proof and every real
admission, registration, submission and later lock remain separate gates.

### 6.5 Offline external signer

Shared `main` contains an Android admission signer as a separate offline trust
boundary. Its manifest declares only biometric permission, disables backup and
cleartext traffic, and has no Internet permission. The app validates the exact
admission manifest, displays its bindings, requires strong biometric approval,
uses a hardware-backed Android Keystore P-256 key, normalises and locally
verifies low-S ECDSA, and exports the signed JSON through a local document
picker.

The signer cannot register an admission, contact CLASSIFIRE, submit canonical
records or create a lock. Its private admission key is non-exportable. APK
release signing and Android admission signing are separate credentials and
governance concerns. The signer is absent from this checked-out branch, so its
shared-main implementation must not be confused with the local writer source.

## 7. Technical Authority Registry

CLASSIFIRE does not have one universal “Package 15 database”. The umbrella authority is the **CLASSIFIRE Technical Authority Registry**.

The current registry contains one active technical library:

```text
Technical library ID: TECHLIB-FIREFLY-P15
Manufacturer: FIREFLY
Source package: Package 15
Executable variants: Package 17
Source evidence: FAS190234, FAS190235 and FAS190236
```

Package 15 is therefore the **FIREFLY Technical System Library**. Package 17 contains executable FIREFLY variants derived from that source. Future manufacturer or specialist libraries must be approved independently and added as separate registry members without changing existing FIREFLY identities.

Package 15 itself contains blank-aperture seal systems as well as service-penetration systems. Technical search therefore remains Opening-specific even when the Opening contains zero Services.

Every technical candidate and selected system must retain:

- technical-library ID and release ID;
- manufacturer;
- source package/corpus;
- source document and revision;
- page, table, row and figure where available;
- System ID and Variant ID;
- source hash;
- matched, unknown and mismatched attributes;
- complete dependency and exclusion envelope.

No cross-manufacturer hybrid may be assembled unless an approved tested or assessed system expressly permits it.

## 8. Technical matching

Technical search occurs Opening by Opening against the estimate's immutable Technical Authority Registry release.

Candidate comparison must include, where applicable:

- Opening type, including blank/service-bearing status;
- Service type, material, size, insulation and quantity where Services exist;
- substrate type, thickness, plane and orientation;
- opening geometry and annular gap;
- spacing and edge distances where Services exist;
- supports, fixings and installation face;
- FRL;
- dependencies and hard exclusions.

Permitted result classes are controlled. A close match or commercial analogue never becomes confirmed technical applicability. Package 14 candidate IDs are retrieval aids only.

## 9. Components, quantities and labour

The selected technical variant must generate distinct required records for every applicable:

- product and layer;
- collar, wrap, tie, fixing and support;
- batt, board, mortar, backing and framing item;
- preparation, installation, finishing and QA activity;
- documentation, photography, labelling and cleanup activity.

A blank Opening may legitimately generate closure components without any service-treatment component. A service penetration may generate both shared opening-closure components and service-specific treatment components. Shared work must not be duplicated.

Every quantity must retain executable inputs, unit conversion, waste, rounding and procurement minimums. Every labour activity must retain quantity driver, crew, productivity source, adjustments and hours. Unexplained fixed labour and descriptive-only formulas do not satisfy completion.

Current production blocker: the FIREFLY variants reference 38 distinct labour activities, but approved productivity coverage is not yet complete. The runtime must fail closed on any selected variant requiring uncovered activity until approved productivity records exist.

## 10. Commercial authority

Package 14 is commercial pricing data only. It may not prove physical scope or technical applicability.

The pricing hierarchy is applied independently to each required component:

1. Exact Library Match;
2. Approved Parameterised Library Match;
3. Component-Built Price;
4. Expert Estimate with disclosed assumptions;
5. Not Priced when no responsible bounded method exists.

Commercial recovery is component based. A component-to-line mapping does not prove recovery. Shared batt, mastic, framing, access or labour is added only when it is not already demonstrably recovered by the selected rate or when it is a separately measured upgrade. Analogue values remain benchmark-only unless a different governed status is expressly permitted.

## 11. Release pinning and knowledge governance

Every estimate pins immutable releases for:

- pricing;
- technical registry;
- rules;
- products/materials;
- labour/productivity;
- markups.

Published releases contain exact record IDs and a verified manifest hash. Later library changes must not alter an existing estimate.

The uploaded v2.13 package files are preserved as controlled migration/source evidence. Runtime authority comes from approved database releases and manifests, not from copying large source packages into every agent prompt.

## 12. Validation and release gates

At minimum the following evidence-backed gates are required:

- source-file and page-review completeness;
- duplicate-view reconciliation;
- Opening population and provenance;
- Service population and provenance where Services physically exist;
- blank-opening classification integrity where no Service exists;
- Opening/Service relationship integrity;
- substrate type, plane, orientation and FRL-assumption completeness;
- Physical Model Lock;
- technical release integrity and Opening-specific search;
- candidate applicability and mismatch disclosure;
- Repair Strategy Lock;
- system-derived component and component completeness;
- quantity arithmetic and labour activity completeness;
- productivity source coverage;
- pricing release and rate applicability;
- Commercial Method Lock and recovery reconciliation;
- duplicate-recovery and price-anomaly review;
- formula and runtime-version integrity;
- snapshot and certificate integrity;
- proposal and output reconciliation;
- Human Release approval.

Static `PASS` text is prohibited. Every gate must retain the validator, inputs, counts, exceptions, result and hash.

## 13. Outputs

Outputs are generated only from an immutable validated snapshot. The output agent may render but may not recalculate or reinterpret scope.

Required output families include:

- detailed technical/audit workbook;
- two-sheet client proposal workbook;
- approved branded PDF output;
- version manifest;
- estimate certificate;
- assumptions, qualifications and non-reliance language appropriate to the estimate class.

PDF and XLSX renderers plus guarded human and agent export routes are present.
They require the current immutable validated snapshot and matching validation
state. No output for the current Phase 8 estimate is eligible, and this
reconciliation did not inspect a representative rendered artifact.

## 14. Performance architecture

The real-report UAT runners are forensic tools, not the production latency target. Production processing should:

- extract each page once;
- analyse each unique visual digest once;
- preserve duplicate placement without duplicate inference;
- cache by evidence hash, prompt/policy version and model version;
- process independent pages and visuals concurrently;
- batch related defects;
- route straightforward extraction to fast deterministic/model paths;
- use deeper reasoning only for ambiguity;
- search technical and commercial databases locally;
- checkpoint and resume at every stage.

Acceptance benchmarks must include 10, 100 and 1,000-defect fixtures, interrupted runs, image-heavy reports, duplicate-heavy reports, mixed service/blank-opening reports and entirely blank-opening reports.

## 15. Deferred physical domains

The following are explicitly deferred and must not be forced into the current penetration calculator or Opening/Service commercial method:

- complete structural-steel members, runs and coating repairs;
- steel/purlin local barrier crossings requiring coating or wrap;
- complete fire-rated duct runs protected by wrap, spray or board;
- steel and duct drawing/markup take-off;
- steel/duct-specific commercial calculators and technical libraries.

These future domains require additive physical-asset schemas, first-class measurements, separate technical libraries and separate commercial methods. Their source calculators and markups remain controlled future evidence.

## 16. Current known gaps

The project remains pre-production until these gaps are closed:

1. Reconcile the divergent checked-out branch with the current shared-main
   physical/admission model and migration lineage through reviewed, bounded
   changes rather than a wholesale merge.
2. Produce a reproducible shared-main controlled-write plugin artifact and pass
   the read-only Gate A audit before any deployment review.
3. Complete approved deployment and live least-privilege runtime proof before a
   fresh preflight or external signature is considered.
4. Canonicalise and independently reconcile the corrected real-report Physical
   Model through its governed boundary, then design and approve the separate
   signed lock-admission boundary required for a replacement active lock.
5. Consolidate the generic database workflow adapter with the scope-aware
   Opening completeness helper; it still assumes every Opening has a Service.
6. Retire or isolate overlapping legacy v1 routes and duplicated model paths
   after compatibility impact is understood.
7. Prove FIREFLY technical selection, component generation, quantities, labour
   and commercial recovery on the corrected locked model, including blank
   Openings and incomplete productivity coverage.
8. Complete private knowledge-source publication, registry-neutral technical
   provenance, multi-library pinning and removal of the schema-level Service
   quantity default.
9. Perform rendered-output QA, security, backup/restore, rollback, scale,
   observability and clean-machine deployment tests.
10. Preserve human-only acceptance of the exact validated snapshot and output
    hashes before production release.
