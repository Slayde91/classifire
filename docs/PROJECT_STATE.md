# CLASSIFIRE Project State

## Current candidate: Word evidence inspection

Branch `feat/scope-word-evidence-20260912` extends the existing Draft intake and
worker with Word upload, explicit malware scan, paragraph/table-cell inspection,
static-picture previews, reopen and exact-original download. It is implemented
locally, not yet a merged or deployed capability. PR #251 documentation merged
as e2fcd15 after CI; the running Excel test app remains unchanged on port 8820.

Verification: 80 integrated Word/UI/migration/lineage/Excel checks passed. Ruff,
Mypy (227 source files), Bandit and the single Alembic head check passed. The
synthetic Edge/Playwright journey passed upload/scan/picture/reopen/exact download;
the rendered screen was inspected. The initial browser harness used an immediate
count before navigation settled; it now waits for visible prepared evidence.
Earlier fixture-login, expected-table-list and callable-annotation failures were
corrected; they are not product successes or unresolved blockers.

Health: candidate is bounded evidence inspection, not complete Word scope analysis.
Word-to-Scope human review, portable Word evidence references/package membership,
ChatGPT Word tools, formatted page rendering and broader document layouts remain
missing. Existing PDF/Excel paths and canonical authority are preserved. Forward
migration 0047 adds only a Draft-owned Word source table; no live database migration
or app activation has been performed for this candidate.

### Recommended Next Actions

Complete this candidate's CI-gated publication. Then extend retained Word evidence
into the existing explicit source-linked Scope review, with versioned provenance
and portable original-bearing packages. Do not turn image placement into semantic
ownership or infer quantities. The separate real ChatGPT Excel acceptance remains
pending refreshed tools and user confirmation; resume it when those are available.
The full production-platform goal remains incomplete.

The earlier workbook checkpoint below describes the preserved running app.

## Current checkpoint: workbook code merged and synthetic app updated

PR #249 adds the Excel client tools (merge a02e895). PR #250 adds optional original
Scope workbook inclusion and ProjectPackage v4 (merge
27cd8bf114cb39caff42ae7150be0d66505fd01f). Required CI run 34609140246 passed before
PR #250 merged at 2026-09-11 14:45:12 UTC. Source, tests and merge are verified.

The user explicitly approved updating the existing synthetic app after merge.
It now runs tested head 8fc4855 in the package-workbook worktree on loopback 8820;
startup completed with process 23084. Existing database, OAuth policy and tunnel
were preserved. Playwright signed in, inspected the updated package screen and
read revision 3 with unchanged Scope hash. An actual authenticated Classifire Test
read through ChatGPT returned the same revision/hash and one defect, two openings,
two services. No project content was created or changed during readiness checks.

### Verification and project health

Affected package/PDF/workbook and import regressions passed, including 27 package/
import/browser checks and seven final integrated client/workbook/schema checks.
Ruff, Mypy (223 files) and Bandit passed locally; required hosted CI also passed.
The synthetic Playwright package journey selected, saved and downloaded a ZIP with
byte-identical workbook bytes. Its ASGI test screenshot and the live read-only
package screenshot were visually inspected. These are distinct forms of evidence.

Full refreshed-ChatGPT Excel upload/review/download acceptance remains unproven.
The tool list in this session still lacks new Excel actions; refresh was requested.
The synthetic workbook is prepared locally but has not been uploaded. Broader input
formats, complete project history, richer technical/pricing capability coverage and
production exits remain incomplete. OpenClaw retirement is not claimed.

Known presentation debt: the immutable legacy v1 package notice still says import
is unavailable, although the current UI supports it. Correct presentation separately;
do not rewrite frozen historical package bytes to change that text.

### Recommended Next Actions

Refresh Classifire Test's tools, then prove a separate synthetic Excel project:
upload -> scan -> inspect cells/pictures -> explicit Scope proposal -> human
confirmation -> package including original workbook -> verified download. Preserve
the existing PDF trial. Do not widen grants, infer quantities, approve technical
systems or calculate prices automatically. Earlier checkpoints below are historical.

Final local validation checkpoint: 51 existing client regressions passed. The three
workbook cases passed after restoring fixture registrations; the selected review-image
endpoint now has an explicit PNG assertion. Playwright rendered the evidence screen,
loaded its picture and confirmed the form, producing revision 2/four source references
in disposable PostgreSQL. The screenshot was visually inspected. This is an ASGI-test
browser proof, not a real hosted/ChatGPT Excel trial. The earlier 37-case workbook/
retrieval/deadline suite passed. Full Ruff, Mypy (223 files) and Bandit passed.
No required CI/merge or activation is claimed yet. Older failure notes below explain
resolved fixture setup and route-order corrections; they are not current blockers.


## Current increment: Excel evidence through the client

Shared main includes PR #248 at bd591384 (required CI passed). Its schema/error
correction is running in the synthetic app. Actual connected invalid proposals
returned redacted field paths and left Scope revision 3 unchanged. Playwright/Edge
verified local login and the saved Scope. ChatGPT cached-schema refresh is still
pending user action; do not claim refreshed discovery has been accepted.

The separate Excel candidate adds client upload, scan, bounded row/image reads,
explicit mapping preview and a source-linked human-reviewed Scope proposal. It
reuses existing workbook parsing, retained evidence, revision and review services.
No price/library adoption, technical matching or downstream execution is automatic.
The browser review shows selected cells, item-to-row/picture associations and the
proposed graph before confirmation. Existing Scope v5 provenance remains unchanged.

Verification: the initial workbook/download suite passed 37 tests. The broader
client suite passed 51 tests; three workbook cases hit missing pytest fixture
registration after import cleanup. Explicit fixture bindings were restored; their
rerun and the separate Playwright review check are active. Ruff, Mypy (223 source
files) and Bandit passed before that test-only fixture correction. Required CI,
publication and real refreshed ChatGPT Excel acceptance remain outstanding.

### Recommended Next Actions

Finish the corrected workbook tests and Playwright review proof, inspect the scoped
diff, then commit/push/PR/merge after required checks. Keep this candidate separate
from the running PDF trial. After publication, obtain real client upload/inspection/
proposal/human-confirmation acceptance using a synthetic XLSX. Do not widen grants,
use customer workbooks or count this Draft slice as a production phase completion.

Earlier checkpoints below are historical and superseded by this current increment.


Validation checkpoint: 44 affected tests passed; six PostgreSQL-dependent tests
were skipped locally. Full Ruff, Mypy (222 files) and Bandit passed. Required
current-head CI/publication and refreshed-client acceptance remain pending.

## Current milestone: connected synthetic Scope package proven

PR #247 is merged at `5c8ee72d27a9a6370cafaa70c8a061f845a804e4`; required
Python validation passed. The user reported actual authenticated ChatGPT discovery,
PDF upload/clean scan, text and page-image inspection, separate human confirmations
and Scope revision 3. This proves one synthetic journey, not production readiness.

The downloaded ZIP was independently inspected: three members, five evidence
references, original PDF byte-identical, Scope revision 3/package revision 1.
ZIP SHA-256: `e52ce4a512604abc66c0b55690f21f5b9d5ede0bc1b5f915e0ad4cc0842819c0`.
The local verification receipt records PASS, 13,437 bytes and no application import.
Scope contains one defect, two separate openings and two services linked only to
O-01; O-02 is blank. Missing dimensions and service quantities remain unknown.
No technical matching, pricing, estimating, report rendering or human release was
proven by this trial. One observation retains stale wording about reviewing page 2;
correcting saved content requires a normal reviewed revision.

### Project health and active work

The trial needed manual JSON repairs after DRAFT_PAYLOAD_INVALID and
PACKAGE_SELECTION_INVALID. Source inspection confirms that nested Scope content
and package selections were advertised as unconstrained dictionaries. The exact
rejected arguments were unavailable, so their individual causes are not asserted.
Current candidate derives discovery schemas from existing domain contracts and
returns bounded, redacted field paths for these two errors. Domain authorization,
validation, request bytes and separate human confirmation remain unchanged.
Publication and refreshed-client acceptance of this candidate must be verified.

### Recommended Next Actions

Finish validation/publication of the schema-discovery correction, refresh the
connected client's tools, and verify a synthetic proposal using the advertised
fields without manually prepared JSON. Then extend the existing Excel intake/review
services to the client as the next visible capability. Keep read/propose/export grants;
do not expand technical/estimate permissions or restart the test runtime implicitly.
Production phase gates and conditional OpenClaw retirement remain incomplete.

The older setup sections below are historical checkpoints, not current blockers.

## Current connected-trial preparation

Verified shared baseline: PR #244 merged at `255e3c6`; required validation run
34496922963 passed. Post-merge run 34499154918 was last observed running; verify its
terminal result before claiming a pass. PR #243 required and post-merge CI passed.
Exact Auth0 issuers and the approved optional-nbf contract are implemented.

The external-policy demo launcher is implemented, not pending development. It prepares
an isolated active estimator without starting a listener, then accepts an exact external
policy through the existing ClientAuthority/main.py hook. Restart preserves policy bytes;
identity, scope, role and marked database/directory checks fail closed. The original
administrator/local-token demo remains separate. No domain schema or migration changed.

Evidence: three launcher tests passed, covering actual application startup through
TestClient, restart, authentication/role/policy refusals and legacy mode. Required CI
passed. The two optional-nbf regressions also passed on recheck. The dedicated PostgreSQL
trial was prepared/reopened with one active estimator and zero projects.

Operator preparation: the existing Auth0 CLI login works; a dedicated human code-flow
client and exact loopback callback are configured. The synthetic API defines only draft
read/propose/export; the machine probe grant remains read-only and unmapped. A local
PKCE helper passed invalid-state rejection with a concurrent idle connection. These are
setup observations, not successful human sign-in, app startup or ChatGPT acceptance.
Credentials and operator artifacts stay outside Git; no customer evidence was processed.

### Project health and active gaps

The merged launcher has passing required CI. Real human authorization, exact account
binding, ChatGPT callback registration, tunnel/app readiness and the visible end-to-end
journey remain unverified. Browser automation was unavailable during setup; user login
is pending. Broader production phases and OpenClaw retirement remain incomplete.

### Recommended Next Actions

Finish the approved synthetic human OAuth trial, then prove one PDF -> inspected evidence
-> proposed Scope -> same-user browser confirmation -> exact package download journey.
Inspect any existing callback process/receipt before restarting. Never map the M2M probe
as a human. Use the actual connection-specific callback supplied by ChatGPT; do not guess
IDs or broaden allowlists. Tenant-wide issuer-response settings remain unchanged.
Do not rebuild the merged launcher or weaken authentication to make the trial pass.

Earlier checkpoints below are historical.

## Pre-merge client permission correction

PR #241 follow-up fixes the client grant check for v3 packages containing retained foreign
archives. Both technical and estimating grants are required regardless of archive version;
native v3 without an origin does not acquire unrelated grant requirements. Ten client-capability
tests passed in 41.20 seconds, including six actual-token scope combinations. Full Ruff and
Mypy (222 files) and the affected-file Bandit scan passed. Current-head CI must pass before
merge; the earlier d452d33 run does not validate this correction. No deployment occurred.


## Active package PDF evidence candidate

Shared main `8164d29` (PR #240) passed required run 34365672716 and post-merge run
34368312777. PDF image access and human-confirmed source-linked Scope saves are merged;
real ChatGPT linking and browser acceptance remain unverified.

Current isolated work adds opt-in inclusion of up to four reviewed project PDFs in a v3
package, an existing-UI selection, semantic source membership and imported attachment
scan/download/re-export checks. Empty source selection retains v1/v2 serialization.
No migration, canonical writes, supplier-workbook export or provider execution is added.

Local validation: the final three PDF-evidence tests passed in 57.58 seconds, including
HTTP selection/save/download, two import generations, exact-byte retention, semantic tamper
refusal, foreign access denial, shared quarantine and active-PDF rejection. Earlier package,
import and UI regression passed 28 tests; the stricter attachment-policy run passed seven
(overlapping coverage). Ruff, Mypy and Bandit passed. Browser acceptance remains unverified.
The 15 intended files are ready for scoped publication; required PR CI and merge remain.

PR #239 and PR #240 are merged, with required and post-merge checks passed. Older validation
entries below are historical evidence, not current publication blockers.


Integrated validation after reconciling PR #239 into PR #240: **40 tests passed in
75.74 seconds**, covering download deadlines, retrieval, PDF client intake/images and
human-confirmed Scope review. Linux-targeted Mypy passed all 222 source files with local
untyped-import diagnostics disabled. Ruff and Bandit passed. Both test additions are retained.
Required PR #240 current-head GitHub validation and merge remain pending.

Latest image/client validation: **6 PDF intake and Scope-review tests passed in 59.21 seconds**.
The image test verifies native PNG content and exact shared-renderer bytes/hash, read-only
access, refusal before scan, invalid page/foreign user/missing read scope and changed-source
refusal, with no Scope revision or pending request. Full Mypy (222 files, local untyped-import
diagnostics disabled), Ruff, Bandit and diff checks passed. Real ChatGPT image consumption
and browser visual acceptance remain unverified.

## Current client PDF-to-Scope increment

The candidate now includes a read-only native MCP page-image response with exact source,
page locator and PNG hash, using the existing renderer and retained-evidence guards.
It supplies visual evidence to a client without creating Scope content or approvals.

The current candidate adds `review_pdf_scope` to the existing typed client proposal
flow. It uses the shared PDF preview/save services to bind selected defects, openings and
services to one retained page. Proposal preparation writes only a pending client request;
confirmation rechecks exact Scope, source, scan, page and target inputs before appending a
Scope revision with server-generated human-review references. Existing operations retain
their original input-hash shape. No migration or downstream capability runs.

Three focused PostgreSQL/MCP tests passed: successful human-confirmed source linkage,
source-change refusal, and ownership/scope/forged-target refusal. The 57-test client/page-review regression passed in 294.69 seconds; publication is pending. The rendered HTTP page and PNG passed checks; browser automation
failed to initialize with a sandbox helper error, so visual browser inspection is unverified.


## PDF download deadline correction

PR #238 is merged at `215028664775eeb1bc84828475f1393da1a598be`; its final PR run
34356058264 passed all gates. This correction fixes a verified gap: the original total-time
check ran only after blocking network calls returned. Production retrieval now uses a fixed
disposable Python process. The parent enforces the deadline across DNS, connection, headers,
body and redirects, then kills and reaps the worker on timeout. Existing URL/content and
socket controls remain. The signed URL travels on stdin; application credentials and config
are excluded from the child environment. The parent rechecks returned PDF bytes and hash.
This is process isolation, not an OS sandbox. It adds one short-lived process per upload;
there is no dependency, migration, domain-service change or authority expansion.

The immediate correction requires real-process stall/success tests, a no-persistence MCP
regression and normal required CI/publication. The next product task remains the real
ChatGPT PDF-to-Scope journey; this fix does not authorize deployment or customer evidence.

Current correction validation: **71 tests passed in 217.00 seconds**, including real child
process termination during DNS/header/body stalls, successful exact-byte transfer, invalid
policy/output refusal and no persisted source/proposal/Scope change on MCP timeout.
Ruff, Mypy (222 source files with untyped-import diagnostics disabled locally), Bandit and
`git diff --check` passed. Required PR CI and publication are still to be verified.

## Evidence-based current snapshot

Verified 2026-09-09 from shared baseline
`d477ff724f3eb6f0229c376728ddba9bea1e75e9`, merge commit for Dataset A
row-observation client PR #237. Exact head
`4ed44ec7543af95541d0d584f8aaa078ad300fde` passed run 34345679363:
the full test suite, Ruff, Mypy, Bandit and the one-head Alembic check all passed.
Post-merge main run 34348938960 passed the same full repository gates on the exact merge commit.
Prior main run 34342328239 reached the workflow's configured 30-minute timeout while
tests were still running; it neither passed nor reported a failing assertion. Earlier
run 34281851774 executed zero steps during a temporary GitHub billing/spending-limit
block; successful later runs prove that historical event is no longer the active blocker.

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

PR #233 adds the first governed T10 project-quantity basis described below. The full local suite
passed **1,919 tests** with two skips. Ruff and Bandit passed; focused Mypy passed on
the five changed Python modules with unavailable third-party stubs ignored, and Alembic
reports the single `0046_draft_pricing_quantity_bases` head. Strict full Mypy could
not run locally because the environment lacks ReportLab and PyYAML stub packages; the
clean PR runner subsequently passed full Mypy on all 220 source files.

Merged PR #235 adds `preview_pricing_coverage` plus bounded read-only list/read
access to persisted T13 evaluation-roster history. All three tools reuse existing
deterministic services, require owned-project read plus estimating and technical client
scopes, and recheck current local role permissions. Roster pages contain at most 20
summaries with an older-revision cursor; exact reads verify canonical bytes and expose
both semantic and content hashes without revealing target prices. The tools create no
request, roster, Estimate, price, approval, evaluation, release or other database record.
The related PostgreSQL regression selection passed **46 tests** and the exact PR head
passed every required repository check before merge.

Merged PR #236 adds bounded read-only list and exact-read MCP access to persisted
T6 recipe links through the existing shared service. Existing standalone callers keep
their ascending history behavior; client pages return at most 20 newest-first summaries
with a stable older-link cursor. The tools expose dependency hashes, evidence state and
current/stale status, create no database record and grant no price or approval authority.
Focused tests passed 3 cases, the related PostgreSQL selection passed **56 tests**, and
final exact-head run 34340361136 passed every required repository gate before merge as
`aca75415`.

Merged PR #237 adds bounded list and exact-read access to reviewed Dataset A
observations through the same deterministic service used by the standalone pricing
screen. Existing no-argument UI calls remain unbounded in worksheet order; client pages
return at most 20 rows with an exact continuation cursor. Exact reads verify canonical
bytes and hashes. The 48 affected PostgreSQL, client and UI tests passed locally, then
the exact PR head passed every required repository check before merge.
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
| Estimate | Manual/history, explicit retained workbook-row application, confirmed client proposals, A/B source profiles, immutable exact-profile decisions, reviewed Dataset A row observations, governed Dataset B mappings, a persisted target-blind T13 roster, T6 recipe-link review, read-only T9 coverage, a bounded manual T10 preview, and an immutable Scope-bound quantity workflow; none changes an Estimate implicitly | Representative quantity semantics, multi-observation/yield/productivity arithmetic, comparable methods, holdout execution and calibrated proposals |
| Reporting | Four independent PDF/XLSX profiles over saved snapshots | Production acceptance and governed close-out/Human Release |
| Packages | Selected ZIP export, new-project import and retained-origin re-export | A/B profile/source-body membership, full history, existing-project merge and production retention |
| ChatGPT boundary | Optional MCP identity mapping and independent client reads/proposals; merged parity through PR #237 reaches exact Dataset A evidence; the current implementation adds PDF upload/scan/list/page tools over shared services | Real OAuth/HTTPS linking, actual provider file transfer and representative report interpretation remain unproven |

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
destructive downgrade and was the shared-main head before recipe-link migration 0045.

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

## Merged MCP access to T9 coverage and T13 roster history

`preview_pricing_coverage(draft_id, technical_release_id)` exposes the exact same
service result to an authenticated ChatGPT-compatible MCP client. The adapter contains
no pricing or matching rules. `list_pricing_evaluation_rosters(draft_id,
before_revision)` returns at most 20 newest-first summaries plus a cursor for older
revisions. `read_pricing_evaluation_roster(draft_id, roster_id)` returns the exact
validated target-blind roster, its canonical byte hash and byte count. Summary output
distinguishes the roster's semantic hash from the hash of its exact stored bytes.

All three tools require read, estimate and technical client scopes, strict external-
client project ownership, an active local user and the existing pricing-review plus
technical-read domain permissions. Under the current owner-only client policy,
successful use therefore requires a Draft owned by an administrator; an estimator-
owned Draft remains denied even with all three client scopes.

Tests compare client results with direct shared-service data, rebuild a fresh FastAPI/MCP
application over the same PostgreSQL state and require identical exact roster output.
A 22-revision case proves the 20-item bound, older-page cursor and correct current marker.
Missing scopes, foreign ownership, insufficient local role, invalid cursors, missing IDs
and corrupt bytes fail closed, while audit and domain table counts remain unchanged. The
roster carries only target-field commitments and hashes, never target prices. This merged client access creates no proposal or roster, approves no evidence, calculates
no price, runs no evaluation and does not connect a real ChatGPT account.

## Merged MCP access to T6 recipe-link history (PR #236)

`list_pricing_recipe_links(draft_id, before_link_id)` returns at most 20 newest-first
summaries and a stable cursor for older links. `read_pricing_recipe_link(draft_id,
link_id)` returns one exact validated canonical link, its content hash and byte count.
The adapter uses `draft_pricing_recipes`; it does not reproduce current/stale, integrity,
recipe or evidence rules. Existing UI calls retain their ascending unbounded behavior.

Both tools require read, estimate and technical client scopes, strict project ownership,
an active local user and existing pricing-review plus technical-read permissions. They
surface exact release, technical-target, recipe, requirement, observation, interpretation
and content hashes without calculating or activating a price. Missing scopes, foreign
ownership, estimator role, missing IDs, invalid cursors and corrupt content fail closed.
A changed technical dependency remains readable but is explicitly reported not current.

Tests build 22 valid links to prove the page bound and cursor, compare exact bytes and
hashes after a fresh FastAPI/MCP application is constructed, and prove relevant audit and
domain counts do not change. The merged change adds no migration, dependency, database
write, approval, evaluation, Estimate change, release, agent or OpenClaw path. Real
OAuth/HTTPS and representative source semantics remain unproven.

## Merged MCP access to Dataset A row-observation history (PR #237)

PR #237 registers `list_pricing_row_observations` and
`read_pricing_row_observation` over the existing intake service. Lists are limited to
20 records, remain stable in worksheet-row and ID order, and use an exact observation as
the continuation cursor. Exact reads return validated canonical JSON, its SHA-256 and
byte count. Existing standalone callers keep their original unbounded ordering.

The tools require read and estimate client scopes plus existing local project, estimate
and library read permissions. They expose row-level provenance, review, uncertainty and
current/stale state without adding technical-read scope to commercial evidence. Tests
prove restart-stable bytes, profile-revision staleness, pagination, access failures,
corruption refusal and zero writes. The change adds no schema, migration, price,
Estimate, approval, evaluation, release, AI or OpenClaw authority. Exact-head CI
passed before merge; post-merge main run 34348938960 passed the same repository gates.

## Implemented ChatGPT-compatible PDF evidence intake

The current implementation adds four authenticated MCP
tools over the same Draft PDF services used by the standalone UI: select/upload one PDF,
list retained sources, explicitly scan/parse a source, and read one page with its locator
and hashes. `upload_draft_pdf` declares the official `openai/fileParams` metadata and
accepts the current `download_url`, `file_id`, optional MIME type and filename shape.

Remote retrieval fails closed unless an operator configures exact lowercase DNS hosts.
It requires HTTPS and public DNS, pins TLS to the checked address, revalidates redirects,
bounds time and bytes, refuses credentials/compression/wrong media/PDF magic and never
retains or returns the signed URL. Retained evidence starts pending. Scan uses the existing
ClamAV/quarantine and disposable parser boundary. Upload and scan change unapproved
evidence-processing state only; no observation, defect, opening, service or saved Scope is
created. Saving interpreted Scope data still uses a separate human-confirmed proposal.

Synthetic validation currently proves 19 safe-retrieval/configuration cases and a combined 56-test
client/PDF/PostgreSQL selection, including the exact MCP schema, pending-to-clean lifecycle,
page text/locator/hash, unchanged Scope revision, zero client proposals, permissions and
empty-policy refusal. Ruff, focused Mypy and focused Bandit pass. Real ChatGPT/OAuth/HTTPS
file transfer, representative reports and interpretation accuracy remain unproven.

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

## Implemented governed T10 project-quantity basis

PR #233 replaces retyped browser quantities with an explicit review
of an exact saved Scope service. An authorised pricing reviewer selects one service from
the current saved Scope revision for one frozen recipe requirement. Preview performs no
write. Save appends canonical JSON bound to the Scope revision/hash, service identity and
quantity/unit/state, technical release/target/recipe hashes, exact recipe-link hash,
requirement identity, reviewer, time and reason. History and exact JSON remain available.

T10's normal UI/service path now consumes only the newest current compatible saved basis.
It withholds the whole proposal when a basis is absent or stale. A Scope revision, recipe
link, requirement, unit or retained hash change invalidates the prior basis. Foreign,
missing, changed, replayed, corrupt and unit-incompatible cases fail closed. The old
explicit-number calculation remains available only as a named `manual_preview`
compatibility mode for tests/comparison; the browser rejects typed quantity fields.

Migration `0046_draft_pricing_quantity_bases` is additive, adds database unit/size and
Scope-revision constraints, becomes the one deployment head and refuses destructive
downgrade. The record grants no Estimate, library, technical, evaluation or release
authority and adds no AI or OpenClaw path.

Real Chrome 152 UAT used synthetic database
`classifire_draft_quantity_uat_20260909_03`. It proved missing-basis withholding,
no-write preview, explicit save, reopen/history, correct `2 each x $300 = $600.00`,
visible hashes, exact downloads, HTTP 403 for an estimator and process-restart
persistence. The 1,994-byte quantity JSON stayed byte-identical with SHA-256
`7ae8c65575233d932e192a4d250b0c4b001c25c90cee2a0fc6edfeb091684a7d`;
the 3,793-byte proposal stayed byte-identical with SHA-256
`ac8b341a2cbbef9cd499e3363d4012c48f26d93f0bc770180a32dd66fc6be153`.
The screenshot was visually inspected, and the served logo is byte-identical to the
user-supplied file at SHA-256
`fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.

## Verification checkpoint

- Active ChatGPT PDF intake: **55 combined client/PDF/PostgreSQL tests passed** in
  133.59 seconds; the included hardened retrieval/configuration suite passed 19 tests. Focused Ruff,
  Mypy on four production files and Bandit on the new boundary passed. This is synthetic
  local evidence, not a real ChatGPT file transfer or production deployment.

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

- Follow-up real-process Chrome 152 UAT closed the combined visual/restart gap for
  Dataset B mapping, T13 roster and T9 coverage. A loopback FastAPI process and dedicated
  PostgreSQL database used one synthetic four-row B workbook: an administrator previewed
  and saved three exact mapped rows and one explicit unmatched row; coverage reported
  three direct-B targets; the roster placed one independent group in each of training,
  validation and holdout and excluded the unmatched row. No prediction or evaluation ran.
- The estimator received HTTP 403 for mapping, coverage and roster mutation. Coverage and
  both save previews stated that no write had occurred. Final state contained four mapping
  records and one roster, with zero activated pricing-library records and zero canonical
  Estimates. Three focused PostgreSQL UI tests passed.
- A fresh application process and fresh Chrome profile reopened all four current mappings
  and the current roster. Mapping SHA-256 values remained
  `115e0b1811b696d087d1af25ba764ac9794993ec8fdf516eb245b5a04fc44930`,
  `f800681590aa2a6fa1153bad59e959ed3fb59f90777d1f85c0e12e09a8987cc8`,
  `48a628235ea5396efa90bac869b05cdffa8798ed7134a14a2fa3f5f057361dac`
  and `cf3c6341a26362f7cfca0468bbf43e62565cfe5c67e9bec2c4e13b792089945e`.
  Roster SHA-256 remained
  `96dd273e2cf09f9b1f86c960558a3cd0deeaa668f5f793e3c87673e6a0e919b6`; recomputed
  coverage remained byte-identical at
  `6dfdcea053bfa30f5373a2299894442a8a43f89381ed5497d5d5a68756fd2ac4`.
  Served logo bytes matched the supplied logo at
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.
  Screenshots were visually inspected and server logs contained no traceback, exception,
  error or HTTP 500. The unavailable local ClamAV service was replaced only for seeding
  this synthetic source; malware-scanner integration was outside this browser proof.

The synthetic demo directory is
`C:\CLASSIFIRE\.tmp\pricing-source-profiles-demo-20260907`. Temporary smoke harnesses,
logs, database state and workbooks stay under `.tmp` and are not repository source.

## Known gaps and active work

Shared main now exposes deterministic T9 coverage and bounded T13 roster, T6 recipe-link
and Dataset A row-observation history. The current implementation adds ChatGPT-compatible PDF
file transport and shared upload/scan/page reads. Real OAuth/HTTPS/ChatGPT execution,
Excel file parameters and representative report interpretation remain unproven.

The prototype is usable for explicit source classification, profile retention,
exact-profile human review, governed Dataset A row observations, exact reviewed Dataset
B identity mappings, immutable target-blind T13 rosters and deterministic T9 coverage.
Those records have no downstream authority. The roster freezes the implemented v1 split
policy, but its synthetic lineage derivation and fixed assignment cycle have not been
accepted against representative real data. The merged quantity-basis slice makes one
Scope service quantity persistent and auditable, but representative mapping semantics,
yield, productivity, waste, pack and shared-recovery arithmetic remain absent. There is
no commercial activation, comparable calculation, holdout
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
remain unproven. Full CI duration is also close to the configured 30-minute job timeout;
run 34342328239 timed out during tests and requires follow-up even though later PR checks
may pass.

The full production goal, canonical Phase 8-14 acceptance, live provider use, real
ChatGPT linking, OpenClaw retirement, deployment and Human Release remain incomplete.

## Project health

The product has a growing, testable standalone Draft workflow with shared services,
exact evidence, explicit uncertainty and narrow user-visible increments. PRs #224/#227/#229 reuse
the existing pricing UI, mapping integrity checks, technical-release governance and
canonical JSON/hash approach without creating another importer, rules engine, agent
fleet, database or prediction path. T10's actual browser/download/restart lifecycle and the
combined Dataset B mapping/T9 coverage/T13 roster lifecycle are now proven with synthetic
data. The merged quantity slice reuses those same boundaries and adds one purpose-specific
append-only table rather than another pricing engine.

The current PDF-intake increment adds only an interface and hardened remote transport over
the existing retained PDF lifecycle. It preserves the human Scope gate and adds no new
agent, database, parser, inference provider or downstream authority.

The recovery root remains on `gpt/phase8-linked-original-images` at `de0cc5a`, with
46 unstaged tracked modifications, 14 staged additions and four DU conflicts. Its
untracked/ignored recovery material is not fully inventoried. It was inspected only;
no root file was staged, reset, cleaned, resolved or published.

## Recommended Next Actions

1. Verify this PDF-intake commit is on shared `main` with exact-head required CI, then prove
   the visible journey through a real operator-controlled HTTPS/OAuth ChatGPT connection:
   select a synthetic PDF, upload, scan, inspect pages, propose a Scope edit, complete browser
   review/save and stop. Record the actual provider file host for the explicit allowlist.
2. Add Excel defect-report file parameters through the same hardened retrieval and shared
   retained-XLSX services after the PDF journey is proven.
3. Define and prove the next ProjectPackage evidence-membership increment, including exact
   pricing-review records and explicit source-body inclusion/withholding rights.
4. Validate T6 recipe meanings and T13 grouping/split policy against authorised representative
   files before evaluation execution, yield/productivity or any scale/accuracy claim.

[SESSION_HANDOFF.md](./SESSION_HANDOFF.md) contains the self-contained next-session task.