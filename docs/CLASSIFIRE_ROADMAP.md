# CLASSIFIRE Roadmap

**Roadmap status:** Active  
**Current milestone:** Rebuild and lock real-report fire-seal physical model under corrected blank-opening policy  
**Current product status:** Pre-production integration build  
**Current technical coverage:** FIREFLY Package 15 source / Package 17 executable variants  
**Deferred:** Complete structural-steel and fire-rated-duct-run implementation

## 1. Current position

The governed synthetic multi-agent UAT passed end to end through Human Release staging. The v2.13 pricing and FIREFLY technical runtime releases were migrated, approved and verified. The current real-report pilot has retained:

- 10/10 PDF pages;
- 41/41 displayed image occurrences;
- 32 unique visual digests;
- 9 exact duplicate occurrences;
- 10 canonical defects;
- complete structured defect-linked text evidence;
- complete page-layout and full-resolution photograph review;
- complete defect-level photo-reconciliation records.

The resumable physical-synthesis pipeline subsequently completed all ten defects and submitted a provisional physical model containing 12 Openings and 19 Services. The model did **not** receive a Physical Model Lock. The lock was correctly refused while the workflow considered the physical model incomplete.

A domain-policy review then identified a material implementation error in the old completeness rule: the database adapter assumed every Opening required at least one Service. That is incorrect. A blank aperture, empty core hole or redundant core hole may itself require passive-fire sealing with **zero Services**. The prior UAT prompt/validator could therefore manufacture placeholder Service records merely to satisfy the old relationship rule. The 12-Opening / 19-Service submission is not suitable for lock and must be rebuilt before technical search.

The corrected physical-scope policy is now:

- `service_penetration` → one or more actual Services and ServiceOpeningLinks;
- `blank_opening` → zero Services permitted;
- `blank_core_hole` → zero Services permitted;
- never create a placeholder Service solely to satisfy a schema or workflow gate;
- every Opening still requires substrate type, substrate plane, orientation and FRL/FRL assumption before lock;
- where report text is silent, defect-linked photographs/page layout may support provisional/inferred substrate type, substrate plane and orientation when a rational visual basis exists;
- missing FRL for the current fire-seal/penetration/blank-opening scope uses the governed estimating assumption `-/120/120`, visibly marked as assumed and requiring verification before technical approval or Human Release.

The current correction path preserves all evidence work, invalidates only the **unlocked pre-technical physical submission**, forces a new physical-synthesis policy/cache version and rebuilds the Physical Model from retained evidence. No PDF extraction, photo extraction or defect intake needs to be repeated.

## 2. Source and knowledge status

### Reviewed v2.13 packages

The current review set includes Packages 01–10, 12 and 14–18. Package 13 was not re-uploaded in this review; the repository retains its previously reviewed routing baseline. Package 11 was not supplied in this review set and no new content conclusion is made about it.

Key controlled source facts:

- Package 14: 897 rows and 897 unique PKB Entry IDs;
- Package 15: 2,183 FIREFLY systems, 2,182 active and one inactive;
- Package 15 includes FIREFLY blank-aperture seal systems as well as service-penetration systems;
- Package 17: 2,861 rows, 2,860 unique Variant IDs, one retained authorised source collision, 2,182 System IDs and FIREFLY-only manufacturer coverage;
- Package 16: active human-governed runtime profile with conditional Project gates;
- Package 18: system-derived component schemas and algorithms, with legacy Package-15-specific contract names retained as compatibility aliases pending a registry-neutral schema release.

### Alignment controls added

- Technical Authority Registry introduced above individual technical libraries;
- Package 15/17 formally scoped as the FIREFLY technical library;
- Package 14 retained as commercial-only authority;
- scope-sensitive FRL assumption policy recorded;
- blank Opening/core-hole semantics added to physical completeness;
- photo-based provisional substrate type/plane/orientation assumptions explicitly governed;
- human-governed current profile distinguished from dormant autonomous-profile amendments;
- source version and count anomalies retained and disclosed rather than silently edited;
- full knowledge-source manifest, hashes and publication procedure added;
- project/knowledge alignment audit added.

## 3. Immediate execution plan

### Phase P1 — Correct and complete real-report physical modelling

**Status:** In progress — evidence complete; prior unlocked physical submission requires governed rebuild

1. Run the controlled unlocked physical-model correction. It must refuse to operate if a Physical Model Lock or downstream technical/component record exists.
2. Rebuild all ten defect proposals under a new physical-synthesis policy version so old caches cannot silently preserve the every-Opening-has-a-Service assumption.
3. Allow explicit `blank_opening` and `blank_core_hole` records with zero Services.
4. Never invent placeholder Services.
5. Use defect-linked report text first and defect-linked photos/page layout to make provisional substrate type, substrate plane and orientation assumptions where rational.
6. Apply `-/120/120` as the current-scope missing-FRL estimating assumption when source FRL is absent.
7. Reconcile every proposed Opening and actual Service, including inferred quantities and sizes.
8. Confirm exact duplicate photos did not increase scope.
9. Confirm opposite-face or alternate-angle photographs were reconciled correctly.
10. Attempt Physical Model Lock only after scope-aware completeness passes.

**Gate:** `REAL_REPORT_PHYSICAL_MODEL_LOCK_PASS`

### Phase P2 — Opening-specific FIREFLY technical search

**Status:** Ready after corrected P1

1. Search the estimate's pinned Technical Authority Registry release.
2. Search the active FIREFLY Package 15/17 records Opening by Opening.
3. For blank openings/core holes, search blank-aperture/core-hole systems without inventing Service attributes.
4. For service penetrations, compare Service, material, size, quantity, substrate, plane, orientation, opening, FRL, spacing, edge distance, support, fixing and dependencies.
5. Preserve every mismatch and unknown.
6. Select one complete source-locked variant or return a qualified result.
7. Record library, release, manufacturer, source document, page/table/figure, System ID and Variant ID.

**Gate:** `FIREFLY_OPENING_SPECIFIC_SEARCH_PASS`

### Phase P3 — Repair strategy and system-derived components

**Status:** Partial foundation exists

1. Create a current Repair Strategy tied to the valid Physical Model Lock.
2. Lock the selected strategy.
3. Parse the selected FIREFLY variant into every required product, layer, fixing, support, preparation, installation, finishing and QA component.
4. For blank openings, generate closure components without creating service-treatment components.
5. Reconcile required versus generated components.

**Gates:** `REPAIR_STRATEGY_LOCK_PASS`, `COMPONENT_COMPLETENESS_PASS`

### Phase P4 — Quantity and labour

**Status:** Blocked on productivity coverage for production reliance

1. Calculate executable quantities with inputs, units, waste, rounding and procurement minimums.
2. Derive labour from required activities rather than fixed generic hours.
3. Approve productivity sources for the 38 currently referenced FIREFLY activity codes.
4. Keep mobilisation, access, preparation, installation, QA, documentation and cleanup distinct where material.
5. Recover shared labour once.

**Gates:** `QUANTITY_ARITHMETIC_PASS`, `LABOUR_ACTIVITY_COMPLETENESS_PASS`, `PRODUCTIVITY_SOURCE_PASS`

### Phase P5 — Commercial pricing and recovery

**Status:** Strong foundation; real-report execution pending P4

1. Apply Package 14 exact/parameterised rates only after line-specific applicability.
2. Otherwise use component-built price, then bounded expert estimate.
3. Record a Commercial Method Lock for every component.
4. Prove inclusions and allocated value.
5. Prevent duplicate recovery of batt, mastic, framing, collars, wraps, fixings, access and labour.
6. Keep commercial analogues benchmark-only unless a different approved status applies.

**Gates:** `RATE_APPLICABILITY_PASS`, `COMMERCIAL_METHOD_LOCK_PASS`, `RECOVERY_RECONCILIATION_PASS`

### Phase P6 — Independent validation and outputs

**Status:** Synthetic UAT passed; real-report execution pending

1. Independently validate physical, technical, component, quantity, labour and commercial records.
2. Create the validated immutable snapshot.
3. Render the technical/audit workbook, client proposal workbook and approved PDF.
4. Reconcile all totals and output hashes.
5. Create the estimate certificate.
6. Bind Human Release to the exact snapshot and outputs.

**Gates:** `INDEPENDENT_VALIDATION_PASS`, `OUTPUT_RECONCILIATION_PASS`, `HUMAN_RELEASE_APPROVAL`

## 4. Knowledge and library programme

### K1 — Private GitHub source preservation

- publish the reviewed source pack to the private repository using the controlled publisher;
- verify the source-pack SHA-256 and every constituent file hash;
- prohibit public-repository publication;
- preserve source files as immutable evidence, not live editable runtime state;
- retain approved database releases as runtime authority.

### K2 — Registry-neutral technical contracts

- retain Package 15 and Package 17 identifiers for FIREFLY lineage;
- add Technical Library and Technical Registry Release identities to candidate/search records;
- replace new hard-coded `package15_basis` fields with registry-neutral fields while preserving compatibility aliases;
- support additional manufacturer libraries without changing FIREFLY IDs.

### K3 — Source corpus cleanup

- issue governed amendments rather than rewriting retained evidence;
- resolve accidental active PFEOS wording through aliases;
- govern the Package 14 `Library_ID` v2.11 versus release v2.13 discrepancy;
- govern Package 15 top-level v2.13 / manifest v2.5 / governance v2.3 lineage;
- govern Package 17 record version 2.7 under the v2.13 deployment release;
- preserve the known duplicate Variant ID collision with deterministic canonical IDs;
- replace blanket FRL-default language with the approved scope-sensitive policy in the next source release;
- preserve the explicit distinction between blank-aperture systems and service-penetration systems.

## 5. Platform, security and operations

### O1 — OpenClaw

- keep role-specific tool grants and deny generic writes;
- maintain image/PDF review only for authorised evidence roles;
- retain direct role-scoped CLASSIFIRE API writes where Gateway tool transport is unreliable;
- use raw OpenClaw local/in-process model transport only as a bounded fallback for explicit Gateway inference timeout;
- cache inference by evidence, physical-policy, prompt and model hashes;
- record model, prompt, policy, agent, run, transport and receipt versions.

### O2 — Mission Control

- retain Mission Control as task/control plane only;
- mirror run, gate, review and release receipts;
- link architecture changes and test evidence to tasks;
- do not store pricing/technical authority in task text.

### O3 — Security and resilience

- complete malicious-file, prompt-injection, path-traversal, formula-injection and cross-agent tests;
- validate secret handling and redacted logs;
- test backup, restore and rollback across application, database, OpenClaw, knowledge releases and Mission Control;
- maintain private repository and controlled-source handling.

## 6. Performance programme

The current real-report scripts are forensic UAT, not the production speed target.

Production work:

- stage timing and model-call instrumentation;
- deterministic extraction before AI reasoning;
- unique-image caching;
- bounded concurrency;
- batch related defects;
- ambiguity routing to deeper reasoning only when required;
- local database technical/pricing search;
- resumable checkpoints;
- transport failover metrics and retry budgets;
- 10-, 100- and 1,000-defect benchmarks;
- explicit mixed service/blank-opening fixtures and all-blank-opening fixtures.

**Gate:** `PRODUCTION_PERFORMANCE_ACCEPTANCE_PASS`

## 7. Deferred structural-steel and ductwork programme

**Status:** Source examples retained; design and implementation deferred.

Future work will include:

- whole steel member/run and local barrier-crossing classes;
- structural FRL format and DFT/section-factor measurements;
- complete fire-rated duct-run segmentation and developed area;
- drawing/markup take-off;
- separate steel and duct technical libraries;
- separate commercial calculators;
- conditional pins, mesh and access-panel components;
- regression against completed spray-calculator examples.

No steel or duct calculator data is imported into the active fire-seal/penetration runtime until this work package is separately designed and approved.

## 8. Production release criteria

CLASSIFIRE remains pre-production until:

- corrected real-report end-to-end UAT passes;
- current source and runtime manifests reconcile;
- all mandatory regressions pass;
- productivity coverage is approved;
- technical and commercial release integrity passes;
- security, backup, restore, rollback and performance tests pass;
- outputs reconcile and certificates verify;
- a competent human approves production release.

## 9. Related documents

- [CLASSIFIRE Architecture](./CLASSIFIRE_ARCHITECTURE.md)
- [Knowledge Alignment Amendment](../knowledge/amendments/CLASSIFIRE_KNOWLEDGE_ALIGNMENT_AMENDMENT_v2.13.1.md)
- [Knowledge Source Manifest](../knowledge/manifests/classifire-knowledge-source-v2.13.json)
- [Project and Knowledge Alignment Review](./reports/CLASSIFIRE_PROJECT_KNOWLEDGE_ALIGNMENT_20260811.md)
