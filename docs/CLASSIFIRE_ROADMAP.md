# CLASSIFIRE Roadmap

## Current product focus

CLASSIFIRE is currently focused on **fire seals and service penetrations**. The active implementation and UAT sequence remains:

1. report, schedule, text and photograph intake;
2. duplicate-image and multi-angle reconciliation;
3. Defect -> Opening -> Service physical modelling;
4. Physical Model Lock;
5. opening-specific search of the authorised FIREFLY technical library (Package 15 source / Package 17 executable variants);
6. system-derived components;
7. quantity and labour derivation;
8. Package 14 commercial pricing and recovery;
9. independent validation, outputs and Human Release.

Structural-steel protection and complete fire-rated duct runs are **recorded future work and are not part of the current implementation sprint**.

## Source examples reviewed for future phases

The following user-supplied source types were reviewed only to identify future roadmap requirements:

- completed vermiculite / spray calculators;
- blank and partially completed spray-calculator quote templates;
- the current fire-seals / penetration calculator;
- the shared inventory and price list used by the penetration and spray calculators;
- marked-up structural drawings identifying whole steel members, runs and sections;
- marked-up mechanical drawings identifying complete fire-rated duct routes;
- mechanical and structural schedules containing member IDs, profiles, sizes, locations and fire-rating requirements.

These source files are controlled commercial evidence. They must remain in private controlled-source storage and must not be committed to GitHub as ordinary application assets.

## Findings retained for later steel and ductwork design

Only the following architecture requirements are carried forward now.

### Separate commercial methods

The current penetration calculator is relevant to fire seals and service penetrations. It is **not** the commercial calculation engine for structural-steel coatings or complete fire-rated duct runs.

Future CLASSIFIRE releases require a Commercial Method Registry containing independently governed methods for:

- penetration and fire-seal estimating;
- structural-steel fire-protection estimating;
- complete fire-rated duct-run estimating.

The methods may consume one shared governed product/rate source, but their formulas, applicability conditions and quantity bases must remain separate.

### Shared price source, separate calculation logic

The supplied calculators show that common rates can include labour, access, access freight, travel, accommodation, masking, spray products, boards, mastic, primers, topcoats and other materials. Future migration must establish stable rate identities and provenance once, then allow each approved commercial method to consume only the relevant records.

A shared price list must never cause the penetration, steel and duct methods to be merged into one formula engine.

### Conditional ductwork components

Pins/clips, mesh and access panels appear in the spray-calculator family and are commonly associated with ductwork scope. They are **conditional system components**, not universal allowances.

Future ductwork implementation must derive them from the selected approved technical system and actual route details. It must not automatically add pins, mesh or access panels merely because a scope item is ductwork.

### Structural-steel data carried forward

Future whole-member or whole-run steel support must be able to receive, where available:

- quantity and member ID;
- profile / section designation;
- member or repair length;
- protected sides / exposed faces;
- required fire duration / structural FRL;
- zone and location;
- beam, column, brace, purlin or other use;
- limiting temperature;
- internal / external exposure;
- section factor or massivity;
- existing and target DFT;
- coating, spray or wrap system;
- notes, evidence status and confidence.

Steel or purlin crossings through a fire-rated barrier remain a separate local barrier-penetration class from protection of an entire structural member or run.

### Complete fire-rated duct-run data carried forward

Future duct support must represent complete protected routes, not a count of barrier penetrations. It must be able to receive, where available:

- run and segment IDs;
- duct height, width or diameter by segment;
- protected length by segment;
- number of protected sides;
- required FRL;
- zone and location;
- horizontal, vertical and riser orientation;
- route start and end limits;
- bends, branches and transitions;
- supports, hangers, flanges and access doors;
- wrap layers / thickness or spray DFT;
- developed external surface area;
- notes, evidence status and confidence.

Marked-up drawings may be the primary project evidence. CLASSIFIRE must preserve drawing number, revision, scale, grid/location, legend, mark-up colour or layer, member/run labels, schedules and related section/elevation references.

### Technical authority remains separate from calculators

The calculators are commercial tools. They do not by themselves prove technical applicability, required DFT, wrap layers, fixings, access-panel requirements or other tested-system controls.

Future steel and ductwork technical libraries must be independently governed under the CLASSIFIRE Technical Authority Registry. Package 15 remains the current **FIREFLY Technical System Library** for the present penetration-focused work; it is not the universal technical database for all future steel and duct systems.

## Deferred steel and ductwork work package

**Status: DEFERRED - source examples retained; design not yet authorised for implementation.**

Later work will include:

1. controlled source intake and hashing for the spray calculators, examples, markups and shared price list;
2. formula, named-range, macro and rate-lineage inventories;
3. separation of technical rules from commercial formulas;
4. structural-steel and duct-run physical-asset schemas;
5. drawing/markup take-off workflows;
6. steel and duct technical-library releases;
7. separate commercial-method implementations;
8. regression comparisons against completed calculator examples;
9. mixed-scope and performance UAT.

No steel or ductwork calculator data is to be imported into the active fire-seal/penetration runtime until this work package is separately designed, reviewed and approved.

## Immediate fire-seal and penetration roadmap

### Phase P1 - Complete real-report physical modelling

- retain the completed 10-page / 41-image intake;
- retain exact-image de-duplication and duplicate-placement provenance;
- make per-defect physical synthesis resumable and Windows-safe;
- avoid whole-report or oversized per-defect synthesis payloads;
- use explicit text, reconciled photographs and labelled AI best estimates for size and quantity;
- apply `-/120/120` only as the approved missing-FRL estimating assumption for the current penetration/fire-seal scope;
- record confirmed, stated, inferred, provisional and assumed values distinctly;
- submit and lock only a complete canonical penetration physical model.

### Phase P2 - FIREFLY technical selection

- search the active FIREFLY Package 15/17 release opening by opening;
- reject incompatible service, size, substrate, orientation, FRL, spacing and opening configurations;
- select one complete approved variant or fail closed;
- retain source document, page/table/figure, system ID, variant ID and release provenance.

### Phase P3 - Components, quantities and labour

- derive all required components and labour activities from the selected FIREFLY variant;
- calculate every physical component separately;
- prevent one-photo, one-row or one-defect quantity defaults;
- complete approved productivity coverage before production labour pricing.

### Phase P4 - Commercial pricing and recovery

- use the penetration/fire-seal commercial method only;
- use Package 14 exact or approved parameterised rates where applicable;
- otherwise use component-built pricing, then bounded expert estimate;
- reconcile every required component and labour activity;
- prevent duplicate recovery of included batt, mastic, collars, wraps, fixings and labour.

### Phase P5 - Validation, output and performance

- independently validate physical, technical and commercial records;
- produce technical/audit and proposal outputs from a validated snapshot;
- retain Human Release as human-only;
- instrument stage timing and model-call counts;
- add evidence-hash caching, bounded concurrency and ambiguity routing before scale testing.

## Performance acceptance targets to establish

The current real-report scripts are forensic UAT tools and are not the production performance target. Production acceptance must benchmark at least:

- 10 defects;
- 100 defects;
- 1,000 synthetic defects;
- image-heavy and duplicate-heavy reports;
- text-only defect schedules;
- interrupted/resumed runs.

Metrics must include extraction time, AI call count and duration, cache hits, unique-image ratio, physical-model time, technical-search time, commercial time and output-render time.

## Related architecture record

See [CLASSIFIRE Next Architecture](./CLASSIFIRE_NEXT_ARCHITECTURE.md) for the detailed scope classifications, FRL policy, Technical Authority Registry and future physical-asset model.