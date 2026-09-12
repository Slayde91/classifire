# CLASSIFIRE Master Roadmap

Reconciled 2026-09-12. Current facts and exact PR/CI state belong in
[PROJECT_STATE.md](./PROJECT_STATE.md); architecture in
[CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md).

## Current delivery decision

Preserve ADRs 0001/0002: a shared modular deterministic core, four independently
callable capabilities, optional AI and portable project artifacts. Prioritize a
user-testable workflow before broad polish; never remove evidence or authority gates.
P0-P6 are bounded Draft milestones, not completion of production Phases 0-16.

## Completed, active and deferred work

| Classification | Current work and evidence |
| --- | --- |
| Completed bounded implementation | Manual Draft Scope, JSON round trip, selected-target Match review/measurements, manual/rate-selected Estimate and all four PDF/XLSX report profiles; shared service contracts and tests |
| Completed bounded implementation | PDF, Excel and Word retained inspection/review; Scope v7 Word evidence; ProjectPackage v5 selected artifacts/originals and governed import/re-export. Word PRs #252-#254 are merged |
| Completed bounded implementation | A/B profiles/review, A observations, B identity mapping, T9 coverage, T6 recipes, T13 roster and governed Scope quantity basis (PR #233); do not rebuild them |
| Completed correction / verification in progress | I1: PR #255 passed and merged as 7847288; current-main run 34664119693 remains live. PR #254 merged before CI finished; main protection is not enforced at the inspected endpoint |
| Upcoming immediate | I2: separately authorized Word trial activation and actual user confirmation/package acceptance; I3: owner decision on enforced merge protection |
| Blocked on external interaction | N1 actual Excel trial needs client tool refresh/attachment/human confirmation. Word activation needs approval. These are not code-absence claims |
| Near term | N2 representative technical recipe/quantity/commercial meaning acceptance before expanding derived rates |
| Reordered | Complete visible evidence-to-Scope-to-package acceptance before broad format/scale/prediction work; retain technical/pricing work as an independent track |
| Superseded | Reimplementing/publishing the already merged PDF/Excel/Word client features; repeating OAuth setup; creating the first governed quantity basis; accumulated old “next session” instructions |
| Deprecated | Mandatory autonomous fleet/one agent per capability; chat or OpenClaw memory as canonical state; automatic approval from imported claims; root recovery checkout as publication source |
| Planned/dependency-bound | L1 wider document/corpus/physical-model coverage and full portable history; L2 calibrated methods, operations, production gates and protected OpenClaw retirement |

## Ordered next actions and acceptance

The complete objective, evidence, components, dependencies, acceptance, validation and
uncertainty for I1-I3, N1-N2 and L1-L2 are maintained together under
[Recommended Next Actions](./PROJECT_STATE.md#recommended-next-actions).
The next session starts with I2 preparation: a concrete Word activation/acceptance
plan. PR #255 is already merged; monitor current-main CI as an activation prerequisite.
Do not start another implementation merely because
an existing run is slow. The handoff carries the exact current task and commands.

Each published change must have observed successful checks on the exact head, required
reviews and no unresolved correctness/security concern before an ordinary merge.
`--auto` is not proof of enforcement. Do not change repository protection without
owner authorization. Record merge commit and post-merge CI separately.

## Detailed retained technical and production backlog

The following catalogue preserves the approved dependencies and exit criteria.
Historical PR references describe bounded increments; the current status table above
and project state supersede older timing/priority statements. No full production
phase is promoted to complete by this documentation reconciliation.

### Technical-corpus and dual-pricing delivery stages

**Status: active implementation.** The minimum visible part of T1/T5/T7 and early-T12
review are merged; the stages remain incomplete until reviewed ingestion,
mapping, capacity and their stated acceptance evidence exist. Existing
technical intake, release governance, Package 14 records and Draft pricing are foundations to extend,
not proof of this new end-to-end capability. Detailed contracts and methods belong in
[Technical Corpus and Dual Pricing Design](./TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md).

T1-T14 are dependency labels, not a requirement for fourteen large sequential builds.
The pre-model T13 grouping/leakage rules are merged, PR #218 adds reviewed Dataset A
row identity, PR #220 adds B identity mapping, PR #222 persists the target-blind roster
and PR #224 adds T9 coverage visibility. PR #227 adds frozen v4 recipes, immutable
review links and guarded T9 bottom-up support. Representative-data
lineage validation, access-separated target opening and evaluation execution remain later.
Every exposed slice includes its UI, minimum persistence and tests.

| Delivery band | Included work and dependency gate |
| --- | --- |
| **First visible corpus/pricing slice** | **A/B profile merged PR #212; review merged PR #214; pre-model T13 contract merged PR #216:** minimum T1 + T5 + T7 identity/profile history, early-T12 exact-profile decision and leakage rules with synthetic data; no library publication or price inference. |
| **Reviewed vertical slice** | **Dataset A observation PR #218, Dataset B mapping PR #220, target-blind T13 roster PR #222, read-only T9 coverage PR #224 and T6 recipe review PR #227; combined B/T9/T13 browser-restart proof complete; broader T2-T8 upcoming.** Reuse applicable source-review infrastructure while keeping commercial and technical authority separate. |
| **Controlled breadth and scale** | Expand T2-T8 through bounded resumable imports, deduplication/reprocessing, proper pagination and representative retained sources; T9 coverage exposes gaps. Measure capacity before declaring hundreds/thousands supported. |
| **Explainable estimating prototype** | **T10 first slice merged PR #229 and real-browser/restart proof complete; governed Scope-bound quantity merged PR #233:** read-only sell-price calculation now consumes immutable saved Scope quantities in the normal UI path, with line evidence, withholding and exact JSON. Next validate representative recipe/quantity semantics, then add yield/productivity/recovery inputs, separate comparable proposals, T12 review UI and T13 evaluation. T11 comparison remains later. |
| **Validated operation** | T13 establishes approved method/stratum gates; T11 combined proposals use that evidence; T14 operations, feedback, drift and controlled release extend the demonstrated path. |

#### T1. Minimum canonical schema and version contracts

**Status:** minimum Draft source identity/version/profile and early-T12 decision contracts
merged; first Dataset A normalized observation is in PR #218 and first Dataset B
mapped/unmatched/ambiguous identity is in PR #220. Broader records remain active.

- **Objective/scope:** distinguish source identity, normalized technical facts and
  observed versus derived commercial data without redesigning the application.
- **Work:** map existing records; add only the SourceDataset/DatasetVersion,
  locator, price-basis and revision fields required by the first profile UI.
  Define compatible extensions for system/configuration mappings and later immutable
  component/labour/proposal snapshots. These are logical contracts, not a mandate
  for separate tables or a complete schema before the first screen.
- **Dependencies:** ADRs 0001/0002, existing source containment and release contracts;
  early T12 review states and T13 evaluation lineage/split rules.
- **Deliverables:** reviewed schema changes, migration/compatibility notes and synthetic
  A/B profile fixtures consumed by the UI.
- **Acceptance:** dataset types cannot be confused; missing units/basis stay explicit;
  original bytes and historic artifacts still validate; no imported authority activates.
- **Risks/data quality:** unverified source layouts, identifier collisions and old
  defaults; preserve historical records rather than silently normalizing them.

#### T2. Bulk technical-document intake and processing

- **Objective/scope:** retain and track technical reports, assessments and certificates
  from one demonstrated source through controlled batches at the requested scale.
- **Work:** extend retained storage, quarantine and the necessary job/run/stage
  contracts for manifests, duplicate-byte detection, retries, cancellation, resource
  limits and per-document outcomes; distinguish new bytes from reprocessing.
- **Dependencies:** minimum T1, source rights and scan policy; pilot one document
  before scaling; provider execution remains separately controlled.
- **Deliverables:** intake/status UI, immutable batch/source manifest and resumable
  worker outcomes with safe diagnostics.
- **Acceptance:** each submitted member is accepted, refused or pending with a reason;
  retry/restart loses no source or outcome and never duplicates publication; measured
  batch/resource evidence precedes any hundreds/thousands capacity claim.
- **Risks/data quality:** corrupt, encrypted, duplicated or superseded files; malicious
  payloads, confidential content, OCR quality and unbounded worker cost.

#### T3. Structured technical extraction

- **Objective/scope:** propose source-backed systems, components, materials,
  dimensions, configurations, installation requirements, performance and limitations.
- **Work:** begin with one supported retained page/table and a reviewable extraction
  result; retain document/page/table/figure locators, contradictions and uncertainty.
  Deterministic parsing is the default; any AI/OCR adapter remains optional and bounded.
- **Dependencies:** T1/T2 source identity and clean-byte access; T12 review contract;
  rights/egress authorization before any real provider use.
- **Deliverables:** versioned extraction proposals and a source-alongside-facts UI;
  later batch extraction reuses this same service.
- **Acceptance:** a reviewer can inspect every proposed material fact against retained
  evidence; unsupported content remains unresolved and no extraction approves a system.
- **Risks/data quality:** table layout, units, crossed-out clauses, drawings, missing
  pages and confidence that overstates what the evidence actually supports.

#### T4. Entity resolution and durable provenance

- **Objective/scope:** resolve documents, systems, variants and components without
  losing distinct configurations, contradictory facts or historical evidence.
- **Work:** use namespaced exact identifiers and reviewed aliases first; stage
  deterministic/fuzzy alternatives for human merge/split review. Preserve per-fact
  source locators, resolution method/version and supersession/reprocessing lineage.
- **Dependencies:** T1 and the T3 pilot; current technical review/publication controls.
- **Deliverables:** identity/provenance review UI, explicit mappings and immutable
  resolution decisions with stale dependency propagation.
- **Acceptance:** repeated input is idempotent; aliases resolve reproducibly; ambiguous
  configurations stay separate; reprocessing preserves all former facts and locators.
- **Risks/data quality:** similar names with different approved conditions, duplicated
  reports and accidental erasure or elevation of historical evidence.

#### T5. Dataset A ingestion: general products and services

**Status:** bounded A identity/version/profile preview-save-reopen and exact-profile
review are merged through PR #214. PR #218 implements one exact reviewed
product/material/labour/service row observation; bulk normalization, richer mapping and
commercial activation remain upcoming.

- **Objective/scope:** profile, then normalize `pricelist.xlsx` as a distinct source
  of products, materials, labour and services; do not assume all rows are buy costs.
- **Work:** first deliver retained A identity and sheet/header/count/anomaly preview;
  subsequently add explicit mappings, unit/pack basis, currency/tax, effective dates,
  price meaning, duplicate policy and reviewed staged import through existing models.
- **Dependencies:** minimum T1 for preview; actual workbook availability/handling and
  verified commercial semantics before real import; T12 review and source lineage.
- **Deliverables:** A profile/import UI and versioned row/cell observations with an
  explicit mapping to Product/Labour/service concepts.
- **Acceptance:** every processed row has an outcome and exact provenance; unknown or
  invalid costs/units remain unusable; no missing rate becomes zero or automatic approval.
- **Risks/data quality:** supplier packs, mixed cost/sell rows, inconsistent dates,
  formulas and legacy Package 14-derived products mistaken for independent A evidence.

#### T6. Component and labour/activity mapping

**Status:** bounded user-visible increment merged in PR #227. New v4 technical releases
freeze bounded component/labour recipes while v3
readers remain supported without fabricated recipe approval. Authorised users can
preview/save/reopen/download immutable linked or unresolved outcomes. T9 requires every
frozen requirement to have a current confirmed complete link before bottom-up support.
Representative recipe semantics, richer units, activation and package membership remain
active/upcoming breadth.

- **Objective/scope:** connect reviewed technical requirements to identifiable
  materials and installation activities before computing their quantities or cost.
- **Work:** map components to A product/service revisions and activities to labour
  bases; define explicit quantity, unit conversion, waste, procurement and productivity
  inputs. Preserve component requirements and labour/activity snapshots per revision.
- **Dependencies:** reviewed T3/T4 requirements, staged/reviewed T5 prices and sufficient
  physical measurements or explicitly limited manual inputs; no Phase 8 gate bypass.
- **Deliverables:** reviewable mapping UI, unresolved mapping list and versioned
  component/activity requirements suitable for a bounded bottom-up calculation.
- **Acceptance:** each cost driver has an identified source and basis or is withheld;
  no defect-count-to-quantity-one shortcut or invented hours; shared work is identified.
- **Risks/data quality:** incomplete bills of materials, hidden installation labour,
  unit mismatches, unsupported productivity and duplicated recovery.

#### T7. Dataset B ingestion: Firefly system prices

**Status:** bounded B identity/version/profile preview-save-reopen and exact-profile review
are merged through PR #214. PR #220 adds one exact reviewed mapped/unmatched/ambiguous
system decision. Verified real semantics, scale and bulk normalization remain upcoming.

- **Objective/scope:** profile, then ingest `pricing_library.xlsx` as distinct observed
  Firefly system-price evidence, including the requested 1,000+ entries when verified.
- **Work:** first deliver B identity/profile/anomalies beside A; later provide bounded
  bulk parsing, pagination, exact cell provenance, source namespaces, deduplication,
  price/scope/date semantics and immutable reviewed versions.
- **Dependencies:** minimum T1 for preview; actual input availability and T12 review;
  capacity-contract extension and T13 holdout lineage before full processing/evaluation.
- **Deliverables:** B profile/import UI and versioned observations, separate from
  derived price proposals and from subsequent system mappings.
- **Acceptance:** supported source counts reconcile without truncation; duplicate keys
  are handled explicitly; supersession preserves prior observations; no row publishes
  merely because the user identifies the workbook as authoritative input.
- **Risks/data quality:** the current 1,000-row including-header parser/retained-contract
  cap and 897-record pricing list; mixed commercial scope, duplicate systems and missing dates.

#### T8. Firefly price-to-system matching

**Status:** one exact human-reviewed mapping path is merged in PR #220. Deterministic
alias candidate generation, fuzzy proposals, bulk review and representative real-source
validation remain upcoming.

- **Objective/scope:** bind B observations to the correct technical system/configuration
  revision without using a price or similar description as proof of suitability.
- **Work:** implement exact namespaced ID/approved-alias resolution, deterministic
  candidates and optional fuzzy proposals with method, confidence, alternatives and
  explicit ambiguity review; check unit, configuration and inclusion compatibility.
- **Dependencies:** T4 resolved technical identities, T7 retained observations and T12
  review states; approved technical evidence for any authoritative application.
- **Deliverables:** side-by-side source/system matching UI and immutable mapping decisions.
- **Acceptance:** repeated matching is reproducible; ambiguous rows remain unresolved;
  changed sources/mappings mark dependent proposals stale; duplicates do not create
  multiple independent observations or overwrite an older mapping.
- **Risks/data quality:** shared names, broad prices covering several configurations,
  source aliases and technically incompatible but textually similar systems.

#### T9. Pricing coverage and missing-data status

**Status:** bounded read-only coverage is merged in PR #224. PR #227 extends it with
guarded bottom-up A support only after every frozen recipe requirement
has a latest current confirmed complete link. Missing/provisional/unresolved/stale links
remain blocked, and stale or ambiguous B evidence takes precedence. Comparable/combined
routes and project-specific applicability remain upcoming.

- **Objective/scope:** make the available pricing routes and unsupported work visible
  before a user requests an estimate.
- **Work:** derive coverage from exact dependencies: direct observed Firefly price,
  bottom-up general-price support, comparable-system support, combined support,
  insufficient evidence and review needed. Keep primary method and review status
  separate so approval never relabels a derived price as a direct observation.
- **Dependencies:** T6/T8 mappings; sufficient scope/unit/basis for the declared route.
- **Deliverables:** coverage summary and per-system/component reasons in the UI/API.
- **Acceptance:** every target is represented, including unpriced targets; missing,
  stale or unapproved inputs cannot disappear behind a total or a green status.
- **Risks/data quality:** false completeness, circular dependency checks and treating
  an existing commercial row as sufficient physical or technical evidence.

#### T10. Explainable estimation methods

**Status:** first bounded slice merged in PR #229; first governed project-quantity
increment merged in PR #233. The merged slice covers one deterministic bottom-up method
for a T9-eligible target. PR #233 binds one explicit saved Scope service
quantity/unit to each frozen requirement through no-write preview and immutable save,
then makes normal T10 consumption require the newest current compatible record. Missing,
stale or incompatible quantity evidence withholds the total. Manual input remains a named
test/comparison mode. Multiple observations, representative quantity semantics,
yield/productivity, waste/pack, recovery, margins, comparables, approval and calibration
remain upcoming.

Synthetic real Chrome 152 UAT on 2026-09-09 proved navigation from coverage, blank
quantity withholding, exact `2 each x $300 = $600.00` arithmetic, dependency identities,
canonical download, lower-privilege denial and byte-identical output after restart. The
merged PR #231 removes the browser-only required constraint and exposes
existing dependency hashes; no calculation, schema or authority boundary changes.

PR #233 Chrome UAT additionally proves Scope-service selection, no-write preview,
immutable save/history/download, visible quantity hashes, HTTP 403, exact
`2 each x $300 = $600.00` arithmetic and byte-identical quantity/proposal downloads
after a process restart. Migration 0046 is additive and refuses downgrade. This evidence
uses synthetic data and does not establish representative recipe or quantity meaning.

- **Objective/scope:** implement separate bottom-up and technically comparable
  proposed prices/ranges for supported cases; retain direct observed pricing distinctly.
- **Work:** calculate explicit quantities times materials/services plus evidenced labour;
  apply waste/pack rounding and commercial margins separately. Select comparables with
  hard technical/commercial filters and versioned differences, weights and adjustments.
  Retain immutable input/BOM/labour/calculation/recovery snapshots and abstention reasons.
- **Dependencies:** T6-T9, T12 proposal/review contract and an already sealed T13 holdout
  assignment. Experimental methods do not imply approved accuracy thresholds.
- **Deliverables:** independent method proposals and UI breakdowns with sources,
  assumptions, scope, limitations and reproducible arithmetic.
- **Acceptance:** missing quantities/productivity remain withheld; no mixed cost/sell
  or tax/unit comparison; recovery is once per component/activity; calculations reproduce.
- **Risks/data quality:** unsupported adjustment factors, sparse comparables, correlated
  costs and currency precision mistaken for evidence of predictive accuracy.

#### T11. Method comparison and controlled combination

- **Objective/scope:** compare the independent T10 results and combine only when their
  commercial scope and calibration evidence justify it.
- **Work:** show discrepancies first; align units/date/tax/cost-versus-sell and recovery
  scope; propose a versioned weighted blend or documented component-level combination
  using validation evidence, with preserved component contributions and alternatives.
- **Dependencies:** T10 prototypes and T12 review; experimental comparison may precede
  T13, but enabling calibrated combination depends on T13 evidence/approved thresholds.
- **Deliverables:** comparison/review screen and immutable method/version/weight records.
- **Acceptance:** do not add two complete system prices; material unresolved differences
  require review or abstention; intervals and weights have measured support, not invented
  percentages; original method predictions remain available after approval.
- **Risks/data quality:** double recovery, correlated errors, scope mismatch and a blend
  that hides disagreement or appears more precise than either input.

#### T12. Confidence, proposals and human review

**Status:** early exact-profile decision UI/service/persistence merged in PR #214;
mapping, price-proposal, override and confidence review remain upcoming.

- **Objective/scope:** make uncertain prices and technical mappings inspectable and
  correctable without silently converting proposals into commercial/technical truth.
- **Work:** define states, reasons, actors and immutable correction/approval events early;
  extend the UI with source/method/assumption breakdown, discrepancy review, overrides
  and separate confidence dimensions for source, mapping, quantity and price prediction.
- **Dependencies:** minimum contract alongside T1/T5/T7; richer UI follows T8-T11;
  calibrated confidence/interval claims depend on T13 rather than reviewer preference.
- **Deliverables:** review contract first, then a working proposal/compare/approve-or-
  reject/override history flow using existing authority and release services.
- **Acceptance:** approvals do not rewrite original proposals or source evidence;
  observed, derived, expert-adjusted and actual values remain separately typed; stale
  inputs and insufficient support block the corresponding authoritative transition.
- **Risks/data quality:** confidence conflated with approval, automation bias and
  review actions unintentionally enabling system compatibility or Human Release.

#### T13. Holdout validation and calibration

**Status:** the pure schema/leakage contract is merged in PR #216 and the first persisted
target-blind roster UI is merged in PR #222. It inventories current reviewed B mappings,
excludes stale/unmatched/ambiguous records, assigns whole connected groups without target
values, requires all three splits, retains immutable revision/hash history and exposes
exact download. Representative-data policy validation, access-separated target reveal,
evaluation, calibration and threshold approval remain upcoming.

- **Objective/scope:** measure each pricing method against independent known Firefly
  observations and set defensible release/abstention thresholds before accuracy claims.
- **Work:** establish a sealed manifest/split policy before modelling; group connected
  target-price/system lineage, aliases, near-duplicate configurations and version copies
  within supported families, not entire workbooks. Run unseen-family and forward-date
  stress tests separately, reporting abstention. Backtest direct-match correctness,
  bottom-up, comparable and candidate combined methods on
  the same scope/basis; measure bias, absolute/relative error, interval coverage,
  confidence calibration and abstention by relevant technical and commercial strata.
- **Dependencies:** lineage contracts start with T1/T7; execution requires verified B
  labels and T10/T11 candidates; threshold approval requires adequate independent data.
- **Deliverables:** reproducible versioned evaluation reports, failure examples,
  sample-size/coverage limitations and an explicitly approved threshold-setting decision.
- **Acceptance:** benchmark labels never reach prediction inputs; exclude held-out
  prices hidden in Package 14-derived products or corrected predictions. No fixed
  accuracy, confidence percentage or release cutoff is claimed before this evidence.
- **Risks/data quality:** small/biased samples, zero or mismatched price bases,
  near-duplicate leakage and training/calibration decisions informed by the final holdout.

#### T14. Operations, monitoring and preserved feedback

- **Objective/scope:** operate the demonstrated corpus/pricing workflow reliably and
  improve it from separately retained reviewer and actual-cost evidence.
- **Work:** add appropriate job/queue/index visibility, throughput/cost/failure and
  quality-drift metrics, retry/recovery/backup/restore controls, versioned reprocessing
  and feedback linking predictions, human revisions, later outcomes and actual costs.
  Reuse existing services across standalone and client adapters; no parallel rules engine.
- **Dependencies:** the supported T2-T13 path and its measured gates; baseline audit,
  permissions and safe diagnostics apply from the first slice, not only at T14.
- **Deliverables:** operational runbooks/dashboards, replayable source/version lineage,
  feedback review UI and controlled evaluation/release/rollback process.
- **Acceptance:** restart/retry and restored snapshots preserve exact provenance;
  monitoring contains no confidential rows; actual cost is not confused with sell price;
  feedback never rewrites the original prediction or silently trains/approves a model.
- **Risks/data quality:** drift, selective feedback, missing actuals, supplier confidentiality,
  storage/index growth and production retention/tenant isolation not proven by a prototype.

### Capacity, migration and decision gates

- Extend the current XLSX resource policy and retained row contract deliberately;
  the existing parser supports at most 1,000 rows **including the header**, ten
  sheets, 50 columns and 20,000 rectangular cells. Reconcile this with B capacity,
  the 897-record pricing list and small client previews. Keep bounded previews and
  confidentiality while adding paginated processing; never silently truncate.
- Preserve Package 14 CSV records and derived-product lineage. Its missing-rate
  zero/default-unit/default-active behavior is not the new ingestion policy.
  Raw-file release hashes and minimal manifests do not satisfy the pinned release
  reader's canonical manifest-hash/record-inventory checks; reviewed publication
  and compatibility fixtures must close that migration gap before using new releases.
- Add explicit source namespaces, cost-versus-sell/unit/pack/scope semantics and
  immutable BOM/labour snapshots before broad automated estimation. Existing JSON
  requirements, manual quantities and a selected unit sell rate do not supply them.
- Actual workbooks, rights, layouts, counts, effective dates and commercial meanings
  remain unverified inputs; no imported confidential rows belong in repository
  fixtures, prompts or documentation. These block real-data acceptance, not the
  synthetic first UI slice or this documentation amendment.
- Technical corpus authority, rate applicability, measurement/productivity rules,
  comparable features/adjustments, blending policy and confidence/error thresholds
  require explicit evidence and the applicable review. No thresholds are approved
  by this roadmap. Unsupported results remain unpriced or visibly provisional.

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

**Remaining:** the root checkout is conflicted recovery evidence. Current validation is recorded in PROJECT_STATE.md. On 2026-09-12 the GitHub
main protection endpoint returned "Branch not protected". PR #254 merged while
validation was running; explicitly verify completed checks before any merge.
Changing repository protection requires owner authorization. Clean-machine and release
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

**Remaining / prioritised amendment:** minimum T1/T5/T7 source identity/profile contracts,
early-T12 profile review, the T13 roster boundary, bounded T9 coverage and governed T6
recipe links are merged through PR #227. The first read-only T10 bottom-up proposal is
merged in PR #229 and its real UI lifecycle is proven. The first Scope-bound quantity
basis is merged in PR #233. Validate T6 recipe meanings and the T13
grouping/split policy against authorised representative Dataset B sources next; only
then broaden governed yield/productivity, waste/pack and recovery inputs. Continue
T2-T8 processing/fact review,
resolution/provenance and breadth in parallel with representative-source validation.
Extend existing technical/product/labour/pricing/release models; no source filename,
profile approval, mapping or roster grants downstream authority.

The legacy Package 14 CSV path is not either new XLSX importer. Close its release
manifest/pinning compatibility gap for the new staged/publication path, preserve
historical rows and derivation lineage, and require explicit price meaning and source
namespaces. Clean-machine import/recovery, corpus-scale evidence and full commercial
inclusion/recovery rules remain unproven. New source authority and immutable releases
must pass their applicable review before canonical use.

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

T2/T14 extend the native visibility only as needed for retained-source batch progress,
per-member outcomes, retries and measured cost/throughput. Neither the bounded PDF/Excel
Scope UI nor the retained A/B profile requires a complete general scheduler, agent
fleet or OpenClaw retirement.

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

T2-T4 add the retained technical-corpus intake, extraction/review and per-fact
resolution/provenance track. T5/T7 reuse the same security principles for A/B workbook
source revisions; they must not turn confidential libraries into redistributable
project evidence. The P1b PDF/Excel Draft review workflows remain separate from
technical-library acceptance. Corpus reprocessing preserves prior source/fact versions
and makes dependent results stale rather than overwriting historical evidence.

The accepted hybrid target also adds a distinct `ProjectPackage` portability
boundary. Selected Draft package download/import/re-export is implemented under P5;
the complete versioned schema, deterministic whole-project
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

T3/T4 improve the reviewed source/variant foundation; T8 maps B price observations
to exact technical configurations only after identity and applicability checks.
Fuzzy resolution remains a review proposal. T9 coverage may expose candidates or
commercial gaps independently, but cannot label an unresolved technical match as
approved because a direct price exists. The Draft mapping prototype is allowed;
its result does not satisfy Phase 9's authoritative exit.

### Phase 10 - Quantity and labour

**Status:** Authoritative exit blocked by Phase 9; bounded P3 development is allowed

Derive component quantities and labour from selected systems with explicit
inputs, units, waste, rounding, procurement, access, productivity, crew, and
shared-work rules. Missing productivity fails closed.

T6 must first produce reviewed component/activity mappings and sufficient measured
inputs; T10 then calculates the supported bottom-up method. Immutable requirements,
BOM, labour/productivity inputs, formulas, units and source revisions must travel with
the result. Existing free-text/JSON technical requirements and manual Draft quantity
entry are foundations, not a completed quantity/labour engine. No defensible
measurement means no invented quantity, crew hours or material recovery.

### Phase 11 - Commercial recovery

**Status:** Authoritative exit blocked by Phases 9-10; bounded P3 development is allowed

Recover each required component once through an authorised pricing hierarchy
and explicit inclusion/recovery ledger. The desk-quote prototype remains a
parallel assumption-led allowance and does not satisfy this exit.

T5/T7 preserve the two pricebooks and cost-versus-sell meaning; T6/T8 establish
reviewed component/system mappings; T9-T12 supply explicit coverage, separate method
proposals, discrepancy review and only evidence-calibrated combination. Keep direct
observed, bottom-up, comparable, combined, expert-adjusted and unresolved values
identifiable after approval. Component/activity recovery must include shared work
exactly once. A whole-system rate cannot be silently applied to the existing
service-only Draft line when its commercial inclusions cover additional work.
T13 evidence gates method claims; none of these proposals alone grants release authority.

### Phase 12 - Independent validation and immutable snapshot

**Status:** Authoritative exit blocked by Phases 8-11; Draft artifact identity work is allowed

Snapshot V2 now keeps volatile generation metadata out of the semantic hash and
binds the complete document with a separate integrity hash; V1 snapshots remain
verifiable. Independently validate physical, technical, quantity, labour,
commercial, formula, recovery, and release integrity.

T13 adds independent pricing holdouts/backtests and confidence/interval calibration;
prepare split/lineage contracts early so known B prices cannot leak through aliases,
Package 14-derived products, older versions or reviewer-corrected predictions.
Offline synthetic/research evaluation is distinct from the Phase 8C real physical-model
accuracy programme and does not require bypassing its gates. Pricing thresholds must
be justified and approved per supported stratum. Saved estimates/reports/packages bind
exact dataset, mapping, BOM/labour, method and review revisions without recalculation.

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

T2/T14 make corpus/pricing throughput, memory/storage, retry/restart, failure isolation
and content-safe observability measurable. Validate the requested corpus/pricebook
scale with representative authorised inputs only when available. Retain predictions,
corrections and actual costs as distinct immutable feedback; no online learning or
automatic promotion of corrected prices into independent benchmark truth. Production
privacy, tenancy, retention and release readiness remain separate evidence gates.

### Phase 16 - Structural steel and full duct runs

**Status:** Planned / deferred

These domains require separate physical taxonomies, source authority,
calculations, libraries, benchmark evidence, and acceptance criteria. Do not
import them into the active fire-seal/penetration runtime prematurely.

## 6. Deprecated and superseded work

- Infrastructure/schema perfection before an interactive prototype.
- The former package-exporter-first handoff as the current next task.
- Workbook-client publication as the immediate task: PR #207 is merged.
- The former A/B-profile-first ordering ahead of the visible report-to-Scope path.
  PDF/Excel graph review is merged and optional suggestions are active; keep the A/B design and
  T1-T14 requirements as a separate retained track.
- Blanket deferral of technical corpus and dual-source pricing: replace it with
  the T1-T14 dependency-ordered delivery plan.
- Copying legacy CSV default-zero/auto-active assumptions into a new workbook
  pipeline, treating a fuzzy price match as technical approval, or treating a
  reviewer-approved derived price as an independent observed benchmark label.
- Treating the full canonical chain as a compulsory user session sequence.

- The conflicted root checkout as a publication, deployment, or bulk-merge path.
- Draft PRs #9-#13 as current-main candidates without selective reconstruction.
- PR #75 as open work; it merged at `348bce5` and remains a bounded
  proposal-only prototype, with PR #103 evidence-read hardening on shared main.
- "Obtain authority and run the approved assessment" as the immediate task; the
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
15. Source A general products/services and source B observed Firefly system prices
    retain separate identities, versions, provenance and commercial meaning.
16. Human approval does not erase whether a price was observed, derived, adjusted
    or an actual cost. Preserve original predictions and the evidence behind changes.
17. Holdout membership and provenance precede model/calibration decisions. Confidence,
    blend weights and accuracy thresholds require measured independent support.

## 8. Related documents

- [Product Goal](../GOAL.md)
- [Engineering Guidance](../AGENTS.md)
- [ADR 0002 - Independent Capabilities](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md)
- [Current Project State](./PROJECT_STATE.md)
- [CLASSIFIRE Architecture](./CLASSIFIRE_ARCHITECTURE.md)
- [Technical Corpus and Dual Pricing Design](./TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md)
- [Architecture Decision 0001 - Hybrid CLASSIFIRE Architecture](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md)
- [Current Session Handoff](./SESSION_HANDOFF.md)
- [Desk Quote Assumption Contract](./DESK_QUOTE_ASSUMPTION_CONTRACT.md)
- [Phase 8 Representative Run Package](./PHASE8_REPRESENTATIVE_RUN_PACKAGE.md)
- [Admission-Bound Writer Deployment Runbook](./ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md)
