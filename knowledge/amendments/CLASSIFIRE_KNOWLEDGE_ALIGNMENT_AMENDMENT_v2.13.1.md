# CLASSIFIRE Knowledge Alignment Amendment v2.13.1

**Amendment ID:** CLASSIFIRE-KNOWLEDGE-ALIGNMENT-v2.13.1  
**Status:** Binding implementation overlay for the current pre-production branch  
**Applies to:** CLASSIFIRE v2.13 source packages, runtime manifests, OpenClaw agents and CLASSIFIRE application  
**Does not do:** rewrite, rename or silently alter retained source evidence

## 1. Purpose

This amendment reconciles the retained v2.13 knowledge corpus with the current CLASSIFIRE application architecture discovered during real-report UAT. It preserves source wording and identifiers while defining how the current implementation must interpret known lineage, scope and policy differences.

## 2. Source preservation

1. Uploaded Packages 01–10, 12 and 14–18 remain immutable controlled source evidence.
2. Package 13 in the repository remains the previously reviewed routing baseline; it was not included in the current upload set.
3. Package 11 was not supplied in the current review set; no new content authority is inferred.
4. Original hashes, row counts, System IDs and Variant IDs must be preserved.
5. Corrections are implemented through this overlay and later governed source releases, not silent source-file edits.

## 3. Technical Authority Registry

1. The umbrella technical authority is the CLASSIFIRE Technical Authority Registry.
2. Package 15 is the current **FIREFLY Technical System Library**.
3. Package 17 contains executable FIREFLY variants derived from Package 15 source evidence.
4. Current FIREFLY evidence is limited to FAS190234, FAS190235 and FAS190236.
5. Existing Package 15/17 System IDs and Variant IDs remain stable.
6. Future technical libraries are registered independently by manufacturer or specialist domain.
7. New records and outputs must include technical-library ID and release ID; legacy Package-15-specific field names remain compatibility aliases only.
8. A Package 14 row, product name or candidate ID never proves technical applicability.

## 4. Package 14 commercial authority

1. Package 14 controls commercial pricing evidence only.
2. It must not establish Service, material, substrate, Opening, FRL, technical system or compliance.
3. The source discrepancy between `Library_ID = CLASSIFIRE-PACKAGE-14-v2.11` and release/deployment version 2.13 is retained as lineage metadata.
4. Runtime authority remains the approved immutable `2.13-runtime` pricing release whose exact records and manifest hash have been verified.
5. A future source release should reconcile the Library ID without changing stable PKB Entry IDs.

## 5. Package 15 and Package 17 lineage

1. The Package 15 filename/top-level release is v2.13.
2. Its internal technical-library manifest records version 2.5 and governance controls from v2.3.
3. Package 17 records identify version 2.7 and are deployed under the v2.13 runtime release.
4. These are version layers, not permission to apply newest-wins reasoning.
5. Runtime records must retain source version, parser/normalisation version, deployment release and approval lineage separately.
6. The retained Package 17 source has 2,861 rows, 2,860 unique Variant IDs and one known source collision: `TSL-FF-FAS190236-RIR1-25A-V211-VAR01`.
7. The importer must preserve both source rows using deterministic canonical record IDs while preventing duplicate active Variant identity.

## 6. FRL assumptions

The repeated source amendment stating that unknown FRL defaults to at least 120 minutes is interpreted only through an approved scope-sensitive estimating policy.

### Current fire-seal and service-penetration scope

- Source FRL, when provided, controls.
- Missing FRL may use `-/120/120` as an estimating assumption.
- The record must state that FRL was not provided, the value is assumed for estimating, and verification is required before technical approval or Human Release.
- The assumption does not create a confirmed technical match or compliance statement.

### Deferred structural steel

- Standalone structural-steel protection uses structural-format FRL, with `120/-/-` as the missing-FRL estimating assumption when later activated.
- Steel or purlin barrier crossings remain a separate penetration-style class.

### Deferred complete fire-rated duct runs

- Whole-run duct protection remains separate from a duct barrier penetration.
- Its FRL, route, dimensions, length, developed area, supports and selected system require a separately approved future workflow.

### No silent default

Unclassified scope receives no FRL default. Every applied default must have an assumption-policy ID and Human verification requirement.

## 7. Evidence and best-estimate policy

1. Explicit defect-linked text is reviewed with full-resolution and layout-linked photographs.
2. Exact image duplicates are analysed once; occurrences remain for placement provenance.
3. Different views of the same Service or Opening are reconciled before quantity.
4. Photograph count, defect count and row count do not establish physical quantity.
5. Missing exact size or quantity does not automatically stop a budget/provisional estimate when a rational evidence-supported estimate can be made.
6. Where report text does not state substrate type, substrate plane or orientation, defect-linked photographs and page layout may support a provisional/inferred assumption when a rational visual basis exists.
7. Photo-derived substrate/orientation assumptions must remain visibly provisional/inferred and retain their basis; they do not become confirmed technical facts.
8. AI-estimated values must remain provisional/inferred, carry reduced confidence and state the basis.
9. Where no rational basis exists, the item remains unresolved or Not Priced as applicable.

## 7A. Blank openings and redundant core holes

1. An Opening does not require a Service merely because the Opening requires passive-fire sealing.
2. An empty aperture, blank opening, redundant core or empty core hole is valid physical scope in its own right.
3. The canonical current-scope opening types are `blank_opening`, `blank_core_hole` and `service_penetration`.
4. `blank_opening` and `blank_core_hole` may contain zero Services and therefore require no `ServiceOpeningLink`.
5. A `service_penetration` must retain at least one actual Service relationship.
6. CLASSIFIRE must never invent a pipe, cable, conduit or other Service merely to satisfy a workflow or database relationship.
7. A service-free Opening must be explicitly classified as blank; an unclassified Opening with no Service remains incomplete.
8. Blank openings still require substrate type, substrate plane, orientation and FRL/FRL-assumption data before Physical Model Lock.
9. Package 15/17 technical search remains Opening-specific for blank openings and must select a valid blank-aperture/core-hole system where available.

## 8. Runtime profile

1. The current deployment is human-governed.
2. Human Release remains human-only and must reference the exact snapshot and output hashes.
3. Autonomous-profile amendments in the source corpus are dormant unless explicitly selected, separately validated and approved before Project processing.
4. Narrative statements and model-generated statuses are never locks, approvals or releases.

## 9. Physical and commercial scope

1. The current implementation conformance scope is fire seals and service penetrations represented through Defects, Openings, optional Services and Service–Opening Links.
2. A Defect may contain one or more service penetrations, one or more service-free blank openings/core holes, or a combination.
3. Complete structural-steel protection and complete fire-rated duct runs are deferred additive asset classes.
4. The penetration calculator and Package 14 penetration rates must not price whole-run steel or duct coating scope.
5. Future steel and duct calculators use separate commercial methods while consuming approved shared rate records where applicable.

## 10. Labour and productivity

1. Labour is derived from system-required activities and executable productivity records.
2. Unexplained fixed hours do not satisfy the Productivity Source gate.
3. Current FIREFLY variants reference 38 distinct labour activities.
4. Any selected variant requiring an activity without approved productivity must fail closed for production reliance.

## 11. Package 18 contract transition

1. Package 18 schemas and algorithms remain a valid v2.13 compatibility source.
2. New schema releases must use registry-neutral names such as `TechnicalCandidateRequirement` and `technical_library_basis`.
3. Existing `Package15CandidateRequirement`, `package15_basis` and Package-15 parser names remain compatibility aliases for FIREFLY v2.13 lineage.
4. Compatibility aliases must not imply that all future technical libraries are Package 15.

## 12. Implementation precedence

Where retained source wording conflicts with this amendment solely because the current implementation has moved from a single FIREFLY library to a registry architecture or corrected a database implementation assumption that every Opening must contain a Service, this amendment controls the implementation without altering the source evidence. Constitutional requirements, confirmed Project evidence and exact tested/assessed source conditions continue to prevail.

## 13. Required regressions

- missing-FRL penetration/fire-seal assumption is visible and does not create a confirmed match;
- unknown scope receives no default;
- a blank/redundant core hole can reach Physical Model Lock with zero Services when explicitly classified and otherwise complete;
- a service penetration with zero Services fails closed;
- no placeholder Service is created for a blank opening;
- missing substrate type/plane/orientation can be provisionally inferred from defect-linked photographs when rational and the basis remains visible;
- Package 15 search results carry FIREFLY library provenance;
- a second technical library can coexist without changing FIREFLY IDs;
- Package 14 cannot establish technical applicability;
- exact duplicate images do not increase quantity;
- estimated size and quantity remain provisional;
- Package 17 source collision preserves both rows but one controlled Variant identity;
- autonomous release is unavailable under the human-governed profile;
- uncovered productivity blocks production reliance.
