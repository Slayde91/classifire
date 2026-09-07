# CLASSIFIRE Project State

## Evidence-based current snapshot

Verified 2026-09-08 on shared main
`75817f04f4ff5433b7cfc348daf8454a6b243b3d`, merge commit for PR #224.
Exact PR head `463682f826b789cdfd4843ed22b0f771b6e2a34a` passed run
34148949367 with 1,877 tests, Ruff, Mypy on 212 source files, Bandit and
one-head Alembic checks. Post-merge main run 34150861778 passed the same
1,877-test and repository-gate workflow on the exact merge commit. The governed
Dataset B mapping, target-blind T13 roster and read-only T9 coverage UI are on
shared main.

ADRs 0001/0002 remain accepted. CLASSIFIRE is one modular deterministic application
with independently callable Scope, System Match, Estimate and Reporting capabilities,
portable versioned artifacts and optional bounded AI. OpenClaw remains transitional;
this pricing increment neither invokes it nor proves retirement parity.

| Capability | Implemented and usable within the declared Draft scope | Known remaining breadth |
| --- | --- | --- |
| Scope | Manual graph; retained PDF page/entity review; Excel row/cell/image mapping; optional one-page text/image suggestions with explicit human save | Real-report accuracy, bulk/cross-page reconciliation, broader formats and richer physical relationships |
| System Match | Saved candidates/notes, partial measured checks and client commands | Complete authorized applicability, corpus extraction and multi-source fact resolution |
| Estimate | Manual/history, explicit retained workbook-row application, confirmed client proposals, A/B source profiles, immutable exact-profile decisions, reviewed Dataset A row observations, governed Dataset B mappings, a persisted target-blind T13 roster and read-only T9 coverage; none changes an Estimate implicitly | Component/activity recipes, bottom-up/comparable calculations, holdout execution and calibrated proposals |
| Reporting | Four independent PDF/XLSX profiles over saved snapshots | Production acceptance and governed close-out/Human Release |
| Packages | Selected ZIP export, new-project import and retained-origin re-export | A/B profile/source-body membership, full history, existing-project merge and production retention |
| ChatGPT boundary | Optional MCP identity mapping and independent client reads/proposals | Real OAuth/HTTPS linking; report intake and A/B profile commands lack client parity |

## Current implemented A/B pricing-source profile and review increment

The Draft Estimate pricing screen now asks the user to declare one of two different
source meanings before upload:

- `general_pricelist` (A): general products, materials, labour and services;
- `firefly_system_prices` (B): Firefly system-price observations.

The declaration is explicit. A filename never selects the kind or proves commercial
meaning. Exact duplicate bytes are idempotent for the same kind and fail on a conflicting
kind. Replacement bytes keep the stable dataset ID and increment the source version;
A and B keep different dataset identities.

Existing bounded XLSX retention, PostgreSQL ownership, content-addressed bytes, ClamAV
scan, shared quarantine and deterministic parser limits are reused. A clean source page
shows source/dataset identity, exact hash and worksheet cells. The user selects a sheet,
header row, field mapping and price meaning. Preview performs no write and visibly lists
row anomalies, mapped/unmapped fields and current A/B semantic gaps.

An explicit save appends an unapproved profile revision bound to the Draft, source bytes,
parsed document, dataset ID/kind/version, worksheet/header, exact header cells, mapping,
price meaning and diagnostics. Each revision has a hash and parent hash. Stale source,
stale revision, changed preview, foreign access, corruption and replay fail closed. A
saved profile can be reopened and downloaded as exact JSON. The profile has explicit
false effects for library activation, Estimate change, system matching and price
inference. Existing explicit workbook-row application remains a separate action.

Migration `0040_draft_pricing_source_profiles` adds nullable A/B identity fields to
historical Draft pricing sources and an append-only profile table. Historical sources
remain valid but unclassified. The downgrade refuses retained-profile destruction.
There is exactly one Alembic head.

The current T12 slice adds one immutable human decision per exact saved profile.
An administrator with `pricing:approve` can approve, reject or request revision with
a required reason. The decision envelope records reviewer, UTC time, profile revision,
exact profile JSON hash, explicit false effects and its own exact hash. Users with
normal read access can reopen and download the exact decision JSON. Saving a newer
profile leaves the old decision unchanged and visibly stale; the newer profile may
receive its own decision. A decision replay, stale profile, changed hash, foreign
project, missing permission or corrupted stored envelope fails closed.

Migration `0041_draft_pricing_profile_decisions` adds the append-only decision table,
enforces one decision per exact profile and refuses destructive downgrade. Review
serializes on the retained source row with profile saving. This decision reviews the
source interpretation only: it does not ingest rows, activate a library, grant technical
approval, match systems, infer prices, alter an Estimate or release output.

PR #218 adds an append-only row observation for a current approved
`general_pricelist` profile. An authorised reviewer sees the exact normalized values and
retained source cells, classifies a usable row as product, material, labour or service,
declares a normalized reference, evidence state, reason and explicit unresolved fields,
then previews without a write before saving. Confirmed observations cannot retain
unresolved fields; provisional observations can.

The saved canonical envelope binds Draft, dataset/version, source/document hashes,
profile revision/hash, approval-decision hash, worksheet/header/row, exact cells and row
hash, price meaning, reviewer and UTC time. It can be reopened and downloaded byte for
byte. Changed/stale/foreign/replayed/corrupt inputs, unapproved or unknown-price profiles,
unusable rows and formula/error mapped cells fail closed. A later source keeps old
history and marks it stale. Migration `0042_draft_pricing_row_observations` adds the
append-only table and refuses destructive downgrade.

PR #220 adds an append-only human mapping for one exact usable row from a current
approved firefly_system_prices profile. An administrator with pricing:approve and
technical:read can preview without a write, then record mapped, ambiguous or
unmatched. A mapped result requires one exact eligible variant and populated
non-price identity evidence. Ambiguous retains at least two exact candidates plus
unresolved fields. Unmatched retains no candidate and explicit unresolved fields.
Price, currency and unit cannot prove system identity.

The mapping envelope binds the Draft, B dataset/version, retained source/document,
approved profile/decision, exact worksheet row/cells, active technical release hash,
variant identity, current technical-field snapshot, release-record snapshot, exact
technical source binding and verified source bytes. Reviewer, reason, uncertainty,
canonical JSON and hashes are immutable. Stale source/profile/decision/release, changed
row/variant, replay, foreign access, invalid/formula rows, corrupt JSON and price-only
identity fail closed. Old valid bytes remain available and visibly stale when a
dependency changes. Migration 0043_draft_pricing_system_mappings adds the journal
and refuses destructive downgrade.

This is the minimum T1/T5/T7/T8 plus early-T12 visible slice. Neither A observations nor
B mappings activate a commercial library, approve technical applicability, create a
System Match, infer a price, reprice an Estimate or place their source bodies in a
ProjectPackage.

## Implemented T13 pricing-evaluation roster

PR #216 adds a deterministic, provider-neutral contract for the benchmark manifest that
later pricing methods must use. It accepts Firefly B observations only and binds every
member to exact dataset/version, source/hash, profile/revision/hash, worksheet row/hash,
target hash and availability time. The target price itself is not stored in this roster.

The builder computes transitive groups across system identity, alias cluster,
near-duplicate configuration cluster, source derivation and workbook-version lineage.
Every connected group must stay wholly in training, validation or holdout, and all three
splits must exist. The fixed policy allows only declared technical, independently sourced
A/labour or training-observation features. It rejects known target descendants, any
validation/holdout member used as an input, and any feature unavailable at the frozen
cutoff.

Canonical bytes, the exact manifest hash, actor/time, append-only parent linkage,
foreign-Draft checks, policy tampering, noncanonical JSON, duplicate keys, stale lineage
and caller-supplied replay history fail closed. Explicit effects confirm that the
contract performs no prediction, row ingestion, library activation, Estimate change or
release.

PR #222 wires that contract to current reviewed Dataset B mappings. A user with
`pricing:approve` and `technical:read` can preview the complete mapping inventory,
explicit stale/unmatched/ambiguous exclusions and deterministic proposed groups without
a write. Only current mapped records are eligible. The fixed target-blind assignment
keeps every transitive system, alias, configuration, source-derivation and workbook-
version group in one split; fewer than three independent groups returns a visible
insufficient-evidence result and cannot save.

An explicit save locks the Draft and every relevant dependency, rebuilds the exact
preview, limits preview age, and appends an immutable roster revision. The canonical
JSON binds the inventory and hash, exclusions, fixed policy, cutoff, actor/time,
connected groups, training/validation/holdout membership, manifest and parent hashes.
It stores a commitment to each mapped row and target field, not the price value.
Unchanged inventory replay, changed inputs, stale dependencies, foreign access and
corrupt stored bytes fail closed. History shows current versus stale, and exact JSON can
be downloaded. Migration `0044_draft_pricing_evaluation_rosters` is additive, refuses
destructive downgrade and is the single Alembic head.

This remains a split-governance workflow, not evaluation execution. It does not read or
reveal target prices, select features, train or run a model, compute metrics, activate a
pricing library, change an Estimate, approve technical applicability or release output.
There is no calibration or accuracy claim.

## Implemented T9 pricing coverage

PR #224 adds a deterministic, read-only coverage view over every target in the current
active technical release. It reuses current Dataset B mapping integrity checks and binds
each result to the exact target, release and mapping hashes. Current mapped B evidence
produces direct support; ambiguous mappings require review; stale mappings remain stale;
and targets without governed evidence report insufficient evidence.

Current reviewed Dataset A observations are exposed as unlinked evidence at the coverage
level. No target receives bottom-up A support because no versioned component/activity
recipe currently connects those observations to a frozen technical requirement. The
service refuses corrupt mapping envelopes and does not infer a relationship from names,
prices or mutable technical JSON.

The pricing page renders the same ordered service result and provides an exact canonical
JSON download. Both declare all price calculation, proposal, library, Estimate, technical,
evaluation, deployment and release effects false. No database migration or new
orchestration dependency was added.

## Verification checkpoint

- Pricing/profile/UI/client-pricing plus migration, packaging, deployment-lineage and
  related compatibility suite: **85 passed** in 351.31 seconds against the explicitly
  opted-in disposable PostgreSQL database. One existing Alembic `path_separator`
  deprecation warning remains.
- Regression coverage includes invalid dataset kind, exact-byte idempotence, A version
  1/2 stable identity, separate B identity, source-kind conflict, no-write preview,
  two-revision parent history, stale source/revision/preview, replay, foreign access,
  exact old bytes, restart reopen, invalid HTTP revision syntax, corruption detection,
  and no Estimate/LibraryRelease/TechnicalVariant creation.
- Full Ruff passed. Full Mypy passed on 205 source files. Bandit passed. `git diff
  --check` passed. Alembic reports only `0040_draft_pricing_source_profiles`.
- Real loopback HTTP prototype at `http://127.0.0.1:8819` used its own marked storage
  and database `classifire_draft_pricing_profiles_demo`, with real local ClamAV on
  port 13311 and synthetic workbooks only. The harness created the Draft through the
  UI, seeded one Estimate through the same domain services, then exercised A and B
  upload/scan/preview/save/reopen/download through HTTP. A source version 2 was retained
  and profile saves left the Estimate at revision 2.
- After a real application process restart and fresh login, both saved profile pages
  reopened. Exact A download SHA-256 remained
  `23c778595610c35d4213f1b2a70cfbdfa22750bc464fed4f0f8835e55982b06b`; exact B
  download SHA-256 remained
  `a829417da5ea4469e23dc3f71ff2c0cebb704f5d709abaae483a08bfdb88db46`.
- The live prototype serves the approved CLASSIFIRE logo: 224,170 bytes, SHA-256
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.
- Native visual browser control could not initialize because its Windows sandbox helper
  exited during setup. Real HTTP forms, cookies, CSRF, uploads, redirects, rendered HTML
  assertions and downloads were exercised; visual layout still needs a browser check
  when that helper is available.
- Review publication evidence: 67 focused pricing/profile/UI/client/migration/lineage
  tests and 44 complete migration/preflight rehearsals passed locally. Required PR CI
  then passed 1,847 tests plus all static, security and migration-head checks.
- Early-T13 evidence: 12 focused contract tests passed; the existing
  pricing/profile/review/UI/client/migration regression selection completed at 100%.
  Full Ruff and Bandit passed locally, the changed module passed Mypy and Alembic
  remained at 0041. Exact PR #216 CI passed 1,859 tests, full Ruff, full Mypy on 207
  source files, Bandit and one Alembic head.
- PR #218 local evidence: 43 focused row-observation/service/UI/migration/deployment
  tests passed; all 62 changed/new migration consumers passed. Repository-wide Ruff and
  Bandit passed, targeted Mypy passed on five changed source files, `git diff --check`
  passed and Alembic reports the single head `0042_draft_pricing_row_observations`.
  Required PR run 34058657496 passed all test, Ruff, Mypy, Bandit and one-head Alembic
  steps before merge. Visual browser inspection and a separate-process restart remain
  to be verified. Post-merge main run 34059650587 passed the same repository gates.
- PR #220 local evidence: the full Draft Pricing regression group passed; all modified
  migration/lineage consumers passed; the final service/UI/migration selection passed
  37 tests with three environment-specific skips. Repository-wide Ruff and Bandit,
  targeted Mypy on all six changed production files, git diff --check and the single
  Alembic head 0043_draft_pricing_system_mappings passed. TestClient covered rendered
  Dataset B permission denial, no-write preview, explicit save, reopen and exact download.
  A separate visual-browser/restart journey was not run. Exact PR-head run 34127607174
  passed 1,868 tests and all repository gates; post-merge main run 34127945847 passed
  the same validation workflow.
- PR #222 local evidence: 16 focused T13 contract/service/rendered-UI tests passed;
  the full Draft Pricing regression group and all changed migration/deployment-lineage
  consumers passed. Repository-wide Ruff and Bandit, isolated Mypy on the three changed
  evaluation service modules, `git diff --check` and Alembic head 0044 passed. The
  local full Mypy command was blocked by missing ReportLab stubs in unrelated PDF output
  modules. Exact PR-head run 34140315496 passed 1,875 tests, full Ruff, Mypy on 211
  source files, Bandit and one-head Alembic. TestClient covered permission denial,
  no-write preview, all three splits, insufficient evidence, explicit save, current/
  stale history, a fresh client session and exact JSON download. A visual browser and
  separate application-process restart were not run.
- PR #224 local evidence: two focused coverage service/UI tests and eight pricing
  regressions passed. Repository-wide Ruff and Bandit passed, targeted Mypy passed on
  both changed source files, `git diff --check` passed and Alembic remained at the
  single head `0044_draft_pricing_evaluation_rosters`. Exact PR-head run 34148949367
  passed 1,877 tests, full Ruff, Mypy on 212 source files, Bandit and one-head Alembic.
  TestClient covered the rendered status inventory and exact canonical JSON. The local
  full Mypy command found missing third-party ReportLab/PyYAML stubs in unrelated
  output/Mission Control modules; CI's complete Mypy run passed. A visual browser and
  separate application-process restart were not run.
- Post-merge main run 34150861778 on
  `75817f04f4ff5433b7cfc348daf8454a6b243b3d` passed 1,877 tests, full Ruff,
  Mypy on 212 source files, Bandit and the migration-head check.

The synthetic demo directory is
`C:\CLASSIFIRE\.tmp\pricing-source-profiles-demo-20260907`. Temporary smoke harnesses,
logs, database state and workbooks stay under `.tmp` and are not repository source.

## Known gaps and active work

The prototype is usable for explicit source classification, profile retention,
exact-profile human review, governed Dataset A row observations, exact reviewed Dataset
B identity mappings, immutable target-blind T13 rosters and deterministic T9 coverage.
Those records have no downstream authority. The roster freezes the implemented v1 split
policy, but its synthetic lineage derivation and fixed assignment cycle have not been
accepted against representative real data. There is no commercial activation or
versioned component/activity recipe, bottom-up/comparable calculation, holdout execution,
calibrated confidence or production release.

The main dependency exposed by T9 is deliberate: `TechnicalVariant` has mutable
`component_requirements` and `labour_requirements`, while the current v3 technical
release snapshot omits both. Reading those fields directly would imply a costing basis
was released when it was not. A forward-compatible recipe/claim contract and explicit
human review must freeze that basis before Dataset A evidence can support a target.

Real A/B workbook layouts, ownership, redistribution rights, price meanings, tax/date/
inclusion semantics and supported record counts have not been verified. The current
parser is deliberately limited to 10 MiB, 10 visible sheets, 1,000 rows including the
header, 50 columns and 20,000 cells. It cannot support a claimed 1,000-plus data-row B
source until measured capacity and contract changes are proven.

Profile reads verify stored JSON hashes and current source/dataset bindings. Preview and
save additionally re-read the exact clean retained source. Database constraints and
application services preserve version identity, but production tenant isolation,
retention, backup/restore, immutable database enforcement and operational monitoring
remain unproven.

The full production goal, canonical Phase 8-14 acceptance, live provider use, real
ChatGPT linking, OpenClaw retirement, deployment and Human Release remain incomplete.

## Project health

The product has a growing, testable standalone Draft workflow with shared services,
exact evidence, explicit uncertainty and narrow user-visible increments. PR #224 reuses
the existing pricing UI, mapping integrity checks, technical-release governance and
canonical JSON/hash approach without creating another importer, rules engine, agent
fleet, database or prediction path. It is merged on shared main.

The recovery root remains on `gpt/phase8-linked-original-images` at `de0cc5a`, with
46 unstaged tracked modifications, 14 staged additions and four DU conflicts. Its
untracked/ignored recovery material is not fully inventoried. It was inspected only;
no root file was staged, reset, cleaned, resolved or published.

## Recommended Next Actions

1. Add the first bounded T6 recipe-review interaction. Freeze one technical target's
   explicit component or labour/activity requirement in a versioned artifact, then let
   an authorised human link it to current reviewed Dataset A observations with units,
   quantity/productivity basis, recovery boundary, exact hashes and unresolved fields.
   Do not calculate or approve a price.
2. Validate the roster grouping/split policy and parser capacity against authorised
   representative Dataset B files before any evaluation execution or scale claim.
3. Perform a real-process browser/restart/exact-download check for the Dataset B mapping,
   T13 roster and T9 coverage UI when browser control is available; keep TestClient proof
   separate.

[SESSION_HANDOFF.md](./SESSION_HANDOFF.md) contains the self-contained next-session task.
