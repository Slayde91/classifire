# CLASSIFIRE Project State

## Evidence-based current snapshot

Verified 2026-09-09 on shared main
`dc5884bee30443af7ffc034e7d4d5a8ef50b0742`, merge commit for PR #231.
PR #231 head `8a714059eef4294f47732aaa797a98e461395fe3` passed run 34256909957
with 1,915 tests, full Ruff, full Mypy on 217 source files, Bandit and the one-head
Alembic check. Post-merge main run 34259076280 passed the same gates on the exact
merge commit, including 1,915 tests. PR #230 run 34246140519 and post-merge main
run 34248498975 passed the same repository gates on the prior documentation baseline,
including 1,915 tests.
PR #229 head `af01adefea9e03fdee298f0b2bc7289dd17492b9` passed run 34241209469,
and post-merge run 34243723658 passed the same repository gates on
`6046376c0f29252527b31c9cd8ffe00eddcc5d76`, including 1,915 tests.
Exact PR head `069a2a82f5296577fa19bceaa730518eef415efc` passed run
34223161569 with 1,913 tests, Ruff, Mypy on 216 source files, Bandit and
one-head Alembic checks. Post-merge main run 34224663080 passed the same 1,913-test
and repository-gate workflow on the exact merge commit.

PR #227 implements the first governed T6 component/activity recipe-review UI and
guarded T9 bottom-up consumption rule described below. The approved cleanup removed
formatter-only churn from five backed-up files. No OpenClaw or AI path is involved.

ADRs 0001/0002 remain accepted. CLASSIFIRE is one modular deterministic application
with independently callable Scope, System Match, Estimate and Reporting capabilities,
portable versioned artifacts and optional bounded AI. OpenClaw remains transitional;
this pricing increment neither invokes it nor proves retirement parity.

| Capability | Implemented and usable within the declared Draft scope | Known remaining breadth |
| --- | --- | --- |
| Scope | Manual graph; retained PDF page/entity review; Excel row/cell/image mapping; optional one-page text/image suggestions with explicit human save | Real-report accuracy, bulk/cross-page reconciliation, broader formats and richer physical relationships |
| System Match | Saved candidates/notes, partial measured checks and client commands | Complete authorized applicability, corpus extraction and multi-source fact resolution |
| Estimate | Manual/history, explicit retained workbook-row application, confirmed client proposals, A/B source profiles, immutable exact-profile decisions, reviewed Dataset A row observations, governed Dataset B mappings, a persisted target-blind T13 roster, T6 recipe-link review, read-only T9 coverage and one bounded T10 explicit-quantity bottom-up sell-price preview; none changes an Estimate implicitly | Governed scope quantities, multi-observation/yield/productivity arithmetic, comparable methods, holdout execution and calibrated proposals |
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
destructive downgrade and remains the shared-main head before candidate migration 0045.

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

Current reviewed Dataset A observations are exposed as unlinked evidence until an
authorised reviewer connects them to a frozen recipe requirement. T9 grants
`bottom_up_a_support` only when every frozen requirement has a latest current, confirmed,
complete link. Missing, provisional, unresolved, stale or corrupt links do not qualify;
stale or ambiguous Dataset B evidence still forces review. The service does not infer a
relationship from names, prices or mutable technical JSON.

The pricing page renders the same ordered service result and provides an exact canonical
JSON download. Both declare all price calculation, proposal, library, Estimate, technical,
evaluation, deployment and release effects false. PR #224 added no migration; the T6
linkage described next uses additive migration 0045 and adds no orchestration dependency.

## Implemented T6 component/activity recipe review

New technical publications use manifest v4 and freeze bounded component/labour source
fields plus stable individually addressable requirements. Existing v3 manifests remain
readable and byte-compatible but correctly report that no frozen recipe is available.
Both pricing and system-match readers require v4 records to contain a valid recipe and
forbid recipe injection into v3 records. Invalid or oversized recipe shapes fail
publication.

An authorised pricing reviewer with technical read access can open a target from T9,
select one frozen component or activity requirement, select up to three current reviewed
Dataset A observations, and record unit, quantity/yield or productivity basis, recovery
boundary, evidence state, unresolved fields and reason. Preview performs no write.
The page exposes each frozen source value/path/hash and the selected observation identity
and hashes before save.
Explicit save locks and rechecks every dependency, appends immutable canonical JSON, and
supports reopen/history and exact download. Foreign, changed, stale, replayed and corrupt
inputs fail closed. Canonical recipe JSON rejects non-finite values; confirmed links
require confirmed observations; authority-effect flags are isolated from caller mutation;
and retained review time is bound to the stored row. Migration
`0045_draft_pricing_recipe_links` is additive and refuses
destructive downgrade.

The link records evidence and interpretation only. It calculates no price, activates no
library, changes no Estimate, approves no technical applicability, runs no evaluation and
releases no output. Representative real recipe meanings, yields, productivity and recovery
rules remain unvalidated.

## Implemented bounded T10 bottom-up proposal preview

PR #229 adds a deterministic service and visible reviewer screen for
targets that T9 marks `bottom_up_a_support`. A reviewer enters an explicit numeric
quantity for each frozen recipe requirement. CLASSIFIRE then reloads current coverage,
recipe links and exact reviewed Dataset A rows, and shows quantity x unit sell rate with
two-decimal half-up rounding. Every line exposes its requirement, link, observation,
unit, price meaning and calculation; the total is withheld if any required line cannot
be calculated. The canonical JSON download recomputes the preview and requires the
expected hash, so changed evidence or inputs cannot be downloaded as the old result.

This first prototype supports exactly one reviewed observation per requirement and only
an explicitly declared `sell_price`. Quantities are preview-only manual inputs; recipe
notes are never parsed into numbers. Cost/list/quoted/actual meanings, multiple rows,
yield, productivity, waste, pack rounding, margin and project-specific applicability are
withheld or remain future work. The service performs no database write and grants no
Estimate, library, technical, evaluation or release authority. Thirteen focused T6/T9/
T10 PostgreSQL tests passed locally. Exact-head GitHub CI passed 1,915 tests plus full
Ruff, Mypy, Bandit and Alembic checks before merge.

Real Chrome 152 UAT on 2026-09-09 then exercised the actual loopback application and
synthetic PostgreSQL state. It found two presentation defects: browser validation blocked
blank-quantity submission before CLASSIFIRE could explain why the result was withheld,
and the screen hid hashes that were already present in the proposal. PR #231
removes the HTML-only required flag and displays coverage, release, target, recipe-link
and observation hashes. It does not change pricing rules, persistence or authority.

The browser journey proved reviewer login, navigation from pricing coverage, visible
blank-quantity withholding, `2 each x $300 = $600.00`, exact dependency display,
canonical JSON download, lower-privilege HTTP 403, application restart and byte-identical
download after restart. Both 2,999-byte downloads have SHA-256
`53fa19cf9fdfc68ca504d4431edb4a73c05a5a7046bab88d1360e28b4f4aeac7`;
the embedded proposal hash is
`faca050aa216b559921b578b6f52cfc4f06cb855181c861beefeabe7e971dadf`.
Screenshots were visually inspected and show the approved CLASSIFIRE logo.

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
- T6 local evidence after the approved cleanup: **130 affected tests
  passed in 267.31 seconds** on the disposable PostgreSQL database, including technical
  release v4/v3 compatibility, recipe contract/service, authenticated TestClient UI, T9
  completeness/precedence, migration packaging and deployment lineage. PostgreSQL
  lifecycle tests exercised locking, access, replay, staleness, timezone/timestamp
  binding, confirmed-source certainty, canonical finite numbers, immutable effects,
  invalid-recipe no-write publication, early combined recipe-count rejection, v3/v4
  recipe-presence coupling in both readers, visible exact review evidence and corrupt
  bytes/evidence.
  Repository Ruff, targeted Mypy, Bandit, `git diff --check` and the single Alembic head
  `0045_draft_pricing_recipe_links` passed. AST comparison confirmed the five restored
  files matched the pre-cleanup T6 semantics after cleanup; a later CI regression then
  deliberately limited strict recipe-presence coupling to v3/v4 so legacy v2 releases
  remain readable. Repository-wide Mypy remains locally blocked
  by pre-existing missing ReportLab/PyYAML stubs; the full pytest run was stopped at 11%
  without failures because its projected runtime was about one hour.
- Exact PR head run 34223161569 passed **1,913 tests**, full Ruff, Mypy on 216
  source files, Bandit and the single Alembic-head check.
- Post-merge main run 34224663080 passed **1,913 tests**, full Ruff, Mypy on 216
  source files, Bandit and the single Alembic-head check on
  `ca875437fd1d7ab8701117e0c0f1a381efc56300`.

The synthetic demo directory is
`C:\CLASSIFIRE\.tmp\pricing-source-profiles-demo-20260907`. Temporary smoke harnesses,
logs, database state and workbooks stay under `.tmp` and are not repository source.

## Known gaps and active work

The prototype is usable for explicit source classification, profile retention,
exact-profile human review, governed Dataset A row observations, exact reviewed Dataset
B identity mappings, immutable target-blind T13 rosters and deterministic T9 coverage.
Those records have no downstream authority. The roster freezes the implemented v1 split
policy, but its synthetic lineage derivation and fixed assignment cycle have not been
accepted against representative real data. One bounded explicit-quantity bottom-up
calculation now exists, but it is preview-only and has no governed persisted project
quantity basis. There is no commercial activation, comparable calculation, holdout
execution, calibrated confidence or production release.

PR #227 resolves the first T9 dependency with a forward-only v4 release snapshot
and explicit human recipe-link review. It does not backfill v3 releases or turn mutable
technical JSON into historical approval. Remaining T6 breadth is representative recipe
semantics, richer units, more than three observations in the current UI, activation and
package membership.

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
exact evidence, explicit uncertainty and narrow user-visible increments. PRs #224/#227/#229 reuse
the existing pricing UI, mapping integrity checks, technical-release governance and
canonical JSON/hash approach without creating another importer, rules engine, agent
fleet, database or prediction path. T10's actual browser, download and restart lifecycle
is now proven with synthetic data; PR #231 only changes and tests presentation.

The recovery root remains on `gpt/phase8-linked-original-images` at `de0cc5a`, with
46 unstaged tracked modifications, 14 staged additions and four DU conflicts. Its
untracked/ignored recovery material is not fully inventoried. It was inspected only;
no root file was staged, reset, cleaned, resolved or published.

## Recommended Next Actions

1. Add the first governed project-quantity basis, bound to the selected saved Scope
   revision and exact frozen recipe requirement. Provide no-write preview plus explicit
   immutable save/reopen/download, and make T10 consume only a current compatible basis.
2. Validate the T6 recipe meanings and roster grouping/split policy against authorised
   representative Dataset B files before any evaluation execution or scale claim.
3. Add governed yield/productivity, waste/pack and recovery inputs only after the
   project-quantity basis is proven; never parse descriptive notes or double count.
4. Perform a real-process browser/restart/exact-download check for the Dataset B mapping,
   T13 roster and T9 coverage UI when browser control is available; keep TestClient proof
   separate.

[SESSION_HANDOFF.md](./SESSION_HANDOFF.md) contains the self-contained next-session task.
