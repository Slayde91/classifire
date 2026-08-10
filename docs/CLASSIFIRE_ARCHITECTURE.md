# CLASSIFIRE Architecture

**Document status:** Current pre-production architecture baseline  
**Architecture version:** 3.14  
**Application release basis:** CLASSIFIRE v2.13 runtime  
**Current implementation focus:** Fire seals and service penetrations  
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

Pricing availability must never determine physical reality or technical applicability. A defect row, photograph, opening, Service, repair component and pricing line are separate canonical concepts.

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
- Defects, Openings, Services and Service–Opening Links;
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

## 6. Current physical model

The current production-candidate conformance scope is:

```text
Defect
  ├── EvidenceSource
  ├── Opening
  │     └── ServiceOpeningLink
  └── Service
```

One Defect may describe zero, one or many Openings and Services. One Opening may contain many Services. One Service may be linked to more than one substrate plane only when evidence proves the physical relationship.

For the current fire-seal and penetration scope, a rational AI best estimate may be used for unknown service size or quantity when report text and visual evidence provide a defensible basis. Such values must be labelled provisional or inferred, carry reduced confidence and retain the estimation basis.

### 6.1 FRL policy for the current scope

For service penetrations and fire seals:

- use the Project/source FRL when supplied;
- when no FRL is supplied, apply `-/120/120` only as an estimating assumption;
- record that the FRL was not supplied and must be verified before technical approval or Human Release;
- the assumption does not create a confirmed technical-system match.

Asset-sensitive FRL rules for structural steel and complete fire-rated duct runs are recorded for later implementation and do not expand the current conformance scope.

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

Technical search occurs opening by opening against the estimate's immutable Technical Authority Registry release.

Candidate comparison must include, where applicable:

- Service type, material, size, insulation and quantity;
- substrate type, thickness, plane and orientation;
- opening type, geometry and annular gap;
- spacing and edge distances;
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
- Service population and provenance;
- Opening and link integrity;
- Physical Model Lock;
- technical release integrity and opening-specific search;
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
- cache by evidence hash, prompt version and model version;
- process independent pages and visuals concurrently;
- batch related defects;
- route straightforward extraction to fast deterministic/model paths;
- use deeper reasoning only for ambiguity;
- search technical and commercial databases locally;
- checkpoint and resume at every stage.

Acceptance benchmarks must include 10, 100 and 1,000-defect fixtures, interrupted runs, image-heavy reports and duplicate-heavy reports.

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

1. the real-report fire-seal UAT reaches a complete Physical Model Lock;
2. FIREFLY technical search is proven on that real physical model;
3. all selected-system components, quantities and labour are complete;
4. approved productivity coverage exists for required activities;
5. knowledge-source publication and hash verification are completed in the private repository;
6. stale legacy identifiers and branding assets are removed or quarantined;
7. Package 15/17 wording is consistently represented as FIREFLY library scope under the Technical Authority Registry;
8. source-version anomalies are governed rather than silently rewritten;
9. security, backup/restore, rollback and scale tests pass;
10. a competent human approves production release.
