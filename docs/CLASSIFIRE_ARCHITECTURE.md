# CLASSIFIRE Architecture

**Document status:** Current pre-production architecture baseline  
**Architecture version:** 3.16
**Application release basis:** CLASSIFIRE v2.13 runtime  
**Current implementation focus:** Fire seals, blank openings/core holes and service penetrations  
**Deferred domains:** Whole-run structural-steel protection and complete fire-rated duct runs

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

The ORM, registration boundary, controlled writer, migrations, and tests now
converge on the clean `0007` contract, and the exact current proposal passed a
disposable-copy registration/submission rehearsal without changing the source
database or creating a lock. The repository v0.5.0 plugin candidate has an
explicit fail-closed profile that locally registers only the admission tool for
`cf-physical-model`, while retaining broader tools inactive in source. The
boundary is not yet deployed or operationally proven: the rebuilt plugin has
not been installed/restarted and the live `cf-physical-model` credential does
not yet have the admission-only scope.
Those live changes and every real admission or canonical submission retain
separate authority gates.

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

1. the corrected real-report UAT proposal is made eligible for canonicalisation through approved writer deployment, runtime boundary verification, a current external signature, separately authorised registration, and separately authorised submission; a valid Physical Model Lock remains required afterward;
2. the generic database workflow adapter is fully consolidated with the new scope-aware Opening completeness helper rather than retaining the prior every-Opening-has-a-Service assumption internally;
3. FIREFLY technical search is proven on the corrected real physical model, including any blank openings/core holes;
4. all selected-system components, quantities and labour are complete;
5. approved productivity coverage exists for required activities;
6. knowledge-source publication and hash verification are completed in the private repository;
7. stale legacy identifiers and branding assets are removed or quarantined;
8. Package 15/17 wording is consistently represented as FIREFLY library scope under the Technical Authority Registry;
9. source-version anomalies are governed rather than silently rewritten;
10. security, backup/restore, rollback and scale tests pass;
11. a competent human approves production release.
