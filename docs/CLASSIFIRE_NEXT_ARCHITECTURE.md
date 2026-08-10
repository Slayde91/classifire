# CLASSIFIRE Next Architecture

## Purpose

This document records the architecture decisions discovered during real-report UAT. It is additive: the current penetration-focused UAT may continue without interruption, while future releases expand CLASSIFIRE to structural steel, fire-rated ductwork, dampers, purlins and multiple manufacturer technical libraries.

## 1. Evidence and assumption hierarchy

CLASSIFIRE should determine physical facts using this order:

1. explicit defect-linked report text;
2. defect-linked, full-resolution and zoomed photographs;
3. reconciled multi-angle photographic evidence;
4. a clearly labelled AI best estimate where a rational estimate is possible;
5. Human or Project clarification where there is no rational basis.

Every important value must preserve:

- value;
- evidence status: confirmed, stated, inferred, provisional, assumed or unresolved;
- confidence;
- source references;
- assumption-policy identifier, when applicable;
- whether Human verification is required.

A photo count is never a Service count, Opening count, repair count or quantity.

## 2. Physical scope classes

The physical-model stage should classify scope before applying FRL, quantity or technical-routing logic.

- `SERVICE_PENETRATION`
- `FIRE_SEAL`
- `LINEAR_JOINT`
- `DAMPER`
- `DAMPER_PENETRATION`
- `DUCT_PENETRATION`
- `FIRE_RATED_DUCTWORK`
- `STEEL_BARRIER_PENETRATION`
- `PURLIN_BARRIER_PENETRATION`
- `STRUCTURAL_STEEL_FIRE_PROTECTION`
- `STRUCTURAL_STEEL_COATING_REPAIR`
- `ACCESS_PANEL_OR_DOOR`
- `OTHER_PASSIVE_FIRE_SCOPE`

The distinction between `STEEL_BARRIER_PENETRATION` and `STRUCTURAL_STEEL_FIRE_PROTECTION` is mandatory.

## 3. Asset-sensitive FRL assumptions

Source evidence always controls when FRL is supplied.

### Penetration-style scope

The following missing-FRL cases may use `-/120/120` as an estimating assumption:

- service penetrations;
- fire seals;
- dampers and damper penetrations;
- duct penetrations;
- fire-rated ductwork;
- steel penetrating a fire-rated element;
- purlins penetrating a fire-rated element.

The assumption must state that FRL was not provided and that `-/120/120` is used for estimating only, subject to Project and technical approval.

### Structural steel protection

Standalone structural-steel fire protection and coating repairs use structural-format FRL. When unknown, the estimating assumption is `120/-/-`.

The assumption must require verification of, where applicable:

- required structural FRL;
- member section;
- section factor or massivity;
- number of exposed faces;
- critical steel temperature;
- approved protection system;
- target DFT.

### Scope without a default

No default is applied to unclassified or unsupported scope. The result remains unresolved.

## 4. Steel and purlins through a fire-rated wall

Where steel or purlins penetrate a fire-rated wall or other rated barrier and the member does not otherwise require full-length fire protection:

- classify it as a barrier penetration, not standalone steel protection;
- use penetration-style FRL;
- allow, for estimating, approved coating or wrap treatment for a minimum 300 mm on each side of the barrier;
- record the 300 mm allowance as a CLASSIFIRE estimating rule;
- require the selected tested or assessed system to confirm the arrangement.

The estimating rule must not be represented as universal technical approval.

## 5. Structural-steel physical asset

A future additive structural-steel model should support:

- member type and section designation;
- member length and repair length;
- exposed faces;
- section factor in m^-1;
- critical temperature;
- required FRL and FRL status;
- existing protection and condition;
- existing DFT;
- required DFT;
- coating system, primer and topcoat;
- substrate preparation;
- location;
- confidence and evidence status.

Final DFT is determined by the approved technical system, not appearance or a generic rule.

## 6. Fire-rated ductwork physical asset

A future additive duct model should support:

- duct shape;
- width, height or diameter;
- measured or estimated length;
- developed surface area;
- orientation;
- required FRL and FRL status;
- treatment type: wrap, spray, board or other;
- wrap layers and thickness;
- spray target DFT and existing DFT;
- supports and hangers;
- access conditions;
- location;
- confidence and evidence status.

Quantity formulas:

- rectangular developed area: `2 x (width + height) x length`;
- circular developed area: `pi x diameter x length`.

## 7. Technical Authority Registry

CLASSIFIRE must not treat Package 15 as the global technical database.

Package 15 is the **FIREFLY Technical System Library**. Package 17 contains executable FIREFLY variants derived from that source corpus.

The umbrella authority is the **CLASSIFIRE Technical Authority Registry**, which may contain independently governed releases such as:

- FIREFLY;
- Promat;
- Trafalgar;
- Hilti;
- Ryanfire;
- other approved manufacturer or specialist libraries.

Each estimate pins an immutable Technical Registry Release. Every technical candidate and selected system must retain:

- technical library ID;
- technical library release ID;
- manufacturer;
- source package or corpus;
- source document and revision;
- page, table and figure where applicable;
- system ID;
- variant ID;
- source hash.

No cross-manufacturer technical system may be assembled unless an approved tested or assessed hybrid system expressly permits the combination.

## 8. Production inference pipeline

The current real-report UAT is forensic and intentionally slow. Production should make expensive AI work proportional to unique pages, unique visuals and ambiguous groups rather than to every defect multiplied by several model calls.

### Production principles

- extract each page once;
- analyse each exact image digest once;
- preserve duplicate placement for layout provenance without repeating detailed vision;
- cache by evidence hash, prompt version and model version;
- batch related defects;
- process independent page, image and defect groups concurrently;
- use a fast model or deterministic parser for straightforward extraction;
- route only uncertain cases to deep GPT reasoning;
- perform technical and pricing search locally in governed databases;
- perform native-resolution or zoom review only when needed;
- persist stage checkpoints and resume safely;
- retain a forensic mode for disputed or high-risk estimates.

### Required performance metrics

- page extraction duration;
- unique-image extraction duration;
- text-inference duration and call count;
- image-inference duration and call count;
- duplicate-collapse ratio;
- photo-reconciliation duration;
- physical-model duration;
- technical-search duration;
- commercial-derivation duration;
- output-rendering duration;
- cache hit ratio;
- number of deep-reasoning escalations.

### Benchmarks

Acceptance benchmarking should cover at least:

- 10 defects;
- 100 defects;
- 1,000 synthetic defects;
- duplicate-heavy reports;
- image-heavy reports;
- text-only schedules;
- mixed-scope reports.

## 9. Recommended implementation sequence

1. Finish the current penetration-focused real-report UAT.
2. Integrate the governed FRL resolver and scope classification.
3. Rename Package 15 in active wording to the FIREFLY Technical System Library.
4. Introduce the Technical Authority Registry while preserving existing FIREFLY IDs.
5. Remove unsafe database quantity defaults from future write paths.
6. Add first-class measurement and assumption records.
7. Add structural-steel and ductwork asset models.
8. Add timing instrumentation and persistent inference cache.
9. Add bounded parallel processing and ambiguity routing.
10. Run mixed-scope and scale acceptance tests.

## 10. Non-negotiable controls

- Human Release remains human-only.
- Technical-library approvals remain human-governed.
- AI estimates must never be presented as confirmed measurements.
- Source FRL always overrides a default assumption.
- Missing quantity must never silently become one.
- Proposed repair wording remains a clue until technical applicability is established.
- Current stable Package 15/17 FIREFLY IDs must be preserved during registry migration.
