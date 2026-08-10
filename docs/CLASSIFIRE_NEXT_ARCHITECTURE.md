# CLASSIFIRE Next Architecture

## Purpose

This document records the architecture decisions discovered during real-report UAT. It is additive: the current penetration-focused UAT may continue without interruption, while future releases expand CLASSIFIRE to structural steel, entire fire-rated duct runs, dampers, purlins and multiple manufacturer technical libraries.

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
- `DUCT_BARRIER_PENETRATION`
- `FIRE_RATED_DUCT_RUN`
- `STEEL_BARRIER_PENETRATION`
- `PURLIN_BARRIER_PENETRATION`
- `STRUCTURAL_STEEL_FIRE_PROTECTION`
- `STRUCTURAL_STEEL_COATING_REPAIR`
- `ACCESS_PANEL_OR_DOOR`
- `OTHER_PASSIVE_FIRE_SCOPE`

The following distinctions are mandatory:

- `FIRE_RATED_DUCT_RUN` means the complete identified run or route of ductwork requiring fire wrap, fire spray, board or another approved protection system. It is not a synonym for a duct penetration.
- `DUCT_BARRIER_PENETRATION` is used only when the defect is specifically the opening, seal, damper or local barrier interface where a duct crosses a fire-rated element.
- `STEEL_BARRIER_PENETRATION` is separate from `STRUCTURAL_STEEL_FIRE_PROTECTION`.

## 3. Asset-sensitive FRL assumptions

Source evidence always controls when FRL is supplied.

### Barrier-penetration scope

The following missing-FRL cases may use `-/120/120` as an estimating assumption:

- service penetrations;
- fire seals;
- dampers and damper penetrations;
- duct barrier penetrations;
- steel penetrating a fire-rated element;
- purlins penetrating a fire-rated element.

The assumption must state that FRL was not provided and that `-/120/120` is used for estimating only, subject to Project and technical approval.

### Entire fire-rated duct runs

Where an entire run of ductwork requires fire wrap, fire spray, fire board or another approved fire-resisting system, classify the physical scope as `FIRE_RATED_DUCT_RUN`.

When the source does not provide an FRL, `-/120/120` may be used as a separately identified duct-run estimating assumption. This must not be described as a penetration-only allowance.

The assumption must require later verification of:

- the complete protected route and its start/end limits;
- required FRL;
- duct type and construction;
- size and shape by segment;
- horizontal, vertical and riser segments;
- bends, transitions and branches;
- length by segment;
- developed external surface area;
- supports, hangers, access doors, flanges and discontinuities;
- selected approved wrap, spray, board or other system;
- wrap layers/thickness or spray DFT where applicable.

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

## 6. Entire fire-rated duct-run physical asset

A fire-rated ductwork item is an entire identified run, route or bounded section requiring continuous protection. It must not be represented as one penetration or one arbitrary `each` item.

The physical model should segment a run whenever size, shape, direction, level, treatment requirement or evidence basis changes. Each segment should support:

- run ID and segment ID;
- start and end locations;
- duct shape;
- width, height or diameter;
- measured or AI-estimated length;
- developed external surface area;
- horizontal, vertical, riser or other orientation;
- bends, branches and transitions;
- required FRL and FRL status;
- treatment type: wrap, spray, board or other;
- wrap layers and wrap thickness;
- spray target DFT and existing DFT;
- supports and hangers;
- access doors, flanges and joints;
- penetrations encountered along the route as separately linked barrier-interface records where applicable;
- access conditions;
- location;
- confidence and evidence status.

Run totals must aggregate the measured segments rather than count photographs, defect rows or penetration points.

Quantity formulas before system-specific laps, waste and allowances:

- rectangular developed area: `2 x (width + height) x length`;
- circular developed area: `pi x diameter x length`.

Package-specific technical rules must later add overlaps, joints, layers, fixings, supports, termination requirements, spray thickness and other approved-system requirements.

## 7. Technical Authority Registry

CLASSIFIRE must not treat Package 15 as the global technical database.

Package 15 is the **FIREFLY Technical System Library**. Package 17 contains executable FIREFLY variants derived from that source corpus.

The umbrella authority is the **CLASSIFIRE Technical Authority Registry**, which may contain independently governed releases such as:

- FIREFLY;
- Promat;
- Trafalgar;
- Hilti;
- Ryanfire;
- specialist duct-wrap or fire-spray libraries;
- structural-steel coating libraries;
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
- mixed-scope reports;
- long fire-rated duct routes with changing sizes and multiple segments.

## 9. Recommended implementation sequence

1. Finish the current penetration-focused real-report UAT.
2. Integrate the governed FRL resolver and scope classification.
3. Rename Package 15 in active wording to the FIREFLY Technical System Library.
4. Introduce the Technical Authority Registry while preserving existing FIREFLY IDs.
5. Remove unsafe database quantity defaults from future write paths.
6. Add first-class measurement and assumption records.
7. Add structural-steel and full-run ductwork asset models.
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
- A fire-rated duct run must never be reduced to the number of wall/floor penetrations it crosses.
- Current stable Package 15/17 FIREFLY IDs must be preserved during registry migration.
