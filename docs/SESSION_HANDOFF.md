# CLASSIFIRE Session Handoff

Reconciled 2026-09-14. Current code, Git, CI and runtime evidence override this
checkpoint. Read [PROJECT_STATE.md](./PROJECT_STATE.md),
[architecture](./CLASSIFIRE_ARCHITECTURE.md), [roadmap](./CLASSIFIRE_ROADMAP.md) and
root GOAL.md. The four independent capabilities and full production objective remain
unchanged and incomplete.

## Latest local rejection permission correction

`fix/native-proposal-rejection-rights-20260914` extends `c2a5157`. Rejection now
rechecks current write permission after source/Draft waits before saving a decision.
The actual PostgreSQL15433 HTTP race reproduced an unauthorized rejection, then
passed with 403 and an unchanged database snapshot after correction. All five
selected regressions passed in 244.48s (18 deselected, no skips, one warning).
Full Ruff, Mypy over 240 files, format and scoped Bandit passed. No schema or authority
change. Private before/after outputs and receipts are in
`native-proposal-rejection-rights-validation-20260914` under .tmp.

Current PR271 remains open at the exact approved 12-file `d864c51`, with failed CI
and no recorded review. The tested `8bce0b0` correction needs its separate public
approval; no later local stack is authorized for publication. Preserve live8820
and the conflicted root. Continue the remaining full-range review and browser
acceptance; this isolated permission regression is not production acceptance.

## Prior local native proposal concurrency correction

`fix/native-proposal-lock-order-20260914` extends `af6e75a`. Publication review
found opposite source/Draft lock ordering between proposal retention and linked
review/rejection. The actual PostgreSQL15433 race reproduced `DeadlockDetected`;
pytest stopped after that first failure. Linked review and rejection now acquire
retained-source locks first and preserve all subsequent under-lock checks. The
two synthetic review/rejection races passed in 109.42s. Full Ruff, Mypy240 and
scoped Bandit passed. This is a locking correction, with no schema, provider or
authority change. All 16 selected regressions passed in 686.35s: both races plus
14 confirmation/authority/rollback cases. Six unchanged decision-integrity cases
were deliberately deselected. The four generated Word/PDF/Excel/manual-edit Scope
bodies match the exact hashes in their separate decisions. Tests used the selected
checkout PYTHONPATH, fresh basetemp and owned PostgreSQL15433 only.

Private reproduction, review and results are in
`native-proposal-lock-order-validation-20260914` under .tmp. The manual route/
confirmation/service review covers 14 files and found this corrected defect.
Separate evidence/transport, package and decision-test reviews bring recorded
manual review to 56 of the current 84-file range, including the prior 24-file
migration/readiness review. Each private ledger entry records its scope and hashes.
Full-range manual review and rendered-browser acceptance remain incomplete.
Public approval remains limited to `d864c51`; newer work is still unpublished.

## Latest local saved-proposal list correction

`fix/native-history-list-order-20260914` extends `23ab398`. Repeated list refreshes
could let an older success or failure replace a newer result, including restoring
proposal buttons after a newer session refusal. Three synthetic cases reproduced
the defect. Only the latest refresh now updates the saved-proposal list and status.
All 32 shipped-script Node VM checks and 16 nearby template/navigation/wrapper tests
passed, with no skips; pytest used this checkout's PYTHONPATH and fresh SQLite
basetemp. The script cache version is advanced. No schema or authority change.

Private evidence is in `native-history-list-order-validation-20260914` under .tmp.
The separate `native-range-review-23ab398-20260914/migration-readiness-review.json`
records manual review of 24 changed migration/model/readiness files, unchanged
from the earlier full-suite candidate `1aeded3`. Full-range manual review and
rendered-browser acceptance remain incomplete. Public approval still covers only
`d864c51`; this correction and its newer ancestors remain unpublished.

## Latest local package form correction

`fix/native-history-package-choice-20260914` extends `3bdc27d`. Users can explicitly
exclude a saved proposal, export it without its decision, or include its exact recorded
decision. The missing proposal-only choice was reproduced after a decision existed.
Two focused cases and exact ZIP/HTML-structure inspection passed; Full Ruff and Mypy240
passed. Schema, archive format and confirmation authority are unchanged. Continue
full-range review and rendered-browser acceptance. Public approval remains `d864c51`
only; all newer feature ancestors and this correction remain unpublished.

The ten existing history, compatibility and package-page regression cases passed
with no failures or skips in 398.79s. All 7 generated regression ZIPs were
inspected successfully. Together with the two focused cases, this is 12 passing tests;
full Ruff, Mypy240, format, scoped Bandit and 33 local document-link checks passed.

## Latest local panel correction

`fix/native-history-stale-open-20260914` extends `0dccc61`. It prevents a delayed
saved-proposal read from restoring cleared context or overriding a newer choice.
Three baseline failures reproduced; 29 Node VM checks pass with the correction.
The 42 nearby chat/navigation/template/wrapper tests passed without failures or skips.
Only the panel script, its cache version, synthetic tests and evidence docs change.
Continue full-range review and browser acceptance; the public approval still covers
only `d864c51`, and PR271's Word-only correction remains separately unapproved.

## Latest local acceptance checkpoint

`test/native-stack-publication-review-20260914` extends `7778166` with direct Word/PDF
original-bearing package and foreign-history import tests. Both passed in195.41s
on disposable15433, with one warning and no skips. ZIP/original/JSON equality and
imported HTML structure were inspected; see PROJECT_STATE.md for evidence limits.
No production source or schema changed. The 83-file ancestor range is inventoried
privately, but its full manual confidentiality review is not complete. Continue that
review and rendered-browser acceptance before presenting a broader publication scope.
The approved public PR remains pinned to `d864c51`; this checkpoint does not expand it.

## Local selected native package history

The isolated `feat/portable-native-history-20260914` branch extends `c837ce5`. Existing
package preview/save now optionally pins saved native proposals and exact decisions,
including an explicit no-selected-decision choice. ProjectPackage v7 carries these records;
empty history preserves v1-v6. Saved/imported pages expose read-only history and exact JSON.
Original imported archives and nested history remain retained without creating local native
proposal/decision records. Scope and package confirmation stay separate. No database
migration, dependency, provider or live change is included; current schema remains0049.

Four synthetic PostgreSQL15433 HTTP/service cases passed, with one warning, in261.72s.
Three SQLite compatibility/bounds cases passed in8.24s, including pending/rejected history,
exact multi-review/Estimate/report bytes and denied sensitive-context export after rights
changed. The selected generation no longer depends on an unselected later corrupt decision;
the failing reproduction is preserved. Selected corrupt history remains blocked. A test-only
response-field mistake also remains in the private evidence; the corrected permission case
passed without changing the application. Full Ruff, Mypy240 and scoped Bandit passed.

The 77-case native-decision/package/import regression passed, with two warnings, in989.64s
on separate owned PostgreSQL15433. A subsequent negative case reproduced a saved re-export
page refusing its own retained nested history. The page/download now reuse the existing
recursive reader. The final eight-case HTTP/UI run passed with one warning in278.29s.
Expired source scans correctly refuse page, ZIP and history access without extra writes.
The full run pinned at `1aeded3` completed: 2,593 passed, two Windows symlink skips and
386 warnings in 7,243.62 seconds. It covers the 0049 decision candidate, not the later
script/claim fixes or this package feature. Those have separate targeted results above.
No job was restarted on observation timeout. Private feature outputs are in
`portable-native-history-validation-20260914` under .tmp.

Exact application commit `23f5110` passed real `classifire.main:app` HTTP startup/restart
on an owned synthetic PostgreSQL15433 clone and loopback8837. Separate package previews
and saves produced history-only and original-bearing v7 ZIPs; separate import preview/
confirmation created a new Draft, then re-export retained both histories in its original
archive. A second server process reopened byte-identical ZIP/JSON, source Scope3 and
imported Scope2. Both blank openings kept unknown dimensions and Unresolved state, with
zero Services. Bad CSRF, missing confirmation, consumed/session-mismatched import tokens
and undeclared history members were refused. Only explicit new Draft/package rows,
login fields and accounted audit entries changed; all original rows were preserved.
Provider, scanner, matching, estimating and report-generation guards recorded zero calls.
Both owned server processes stopped; live8820/15432 and the source fixture were untouched.

A fresh backup restored all 71 tables and76 rows exactly, with matching1179 columns,
450 constraints and398 indexes. The retained original and all three ZIPs matched through
first process, restart and restore. Fresh application readers made346 reads, including26
source locks, with zero SQL mutation attempts; all source/restored rows and schema stayed
unchanged. The initial PostgreSQL read-only-mode attempt refused the existing source-row
locks. Its follow-up retained those quarantine guards, rejected non-read SQL and compared
all rows instead; no application guard changed. Database owner/ACL restoration was excluded.

Private receipts are in `native-history-http-restart-23f5110-20260914`: `attempt3` passed;
`recovery/continuation-receipt.json` completes the exact restore's reader verification.
The earlier failed harness receipts remain: missing confirmation returns422; an old-session
CSRF returns403, while a current-session token with an old import approval returns409.
All three failures were verification-harness mismatches, not changes to application rules.
Seven targeted artifacts, three real-app ZIPs across restart/restore, six HTTP HTML outputs
and74 local document-link targets were inspected. Browser initialization still fails before
interaction; no rendered-browser or live acceptance is claimed. See
[the complete history contract](./NATIVE_PROPOSAL_PACKAGE_HISTORY.md).

PR #271 remains open at approved `d864c51`, with failed CI and no merge. Local Word-only
correction `8bce0b0` still awaits separate public approval. All newer feature ancestors and
this local extension remain unpublished; do not mix them into the 12-file approval.

## Local decision claim consistency correction

The clean base `9b65cfb` is extended in `fix/native-decision-claims-20260914`. Rehashed
contradictory changed flags and malformed submitted hashes must be withheld. Two HTTP
failures reproduced on the base; all 20 corrected decision HTTP cases passed, with one
warning and no skips, on disposable PostgreSQL15433. Static checks and read-only compatibility
with prior 0049 decisions, Scope and the original ZIP passed. See [current evidence](./PROJECT_STATE.md#local-native-decision-claim-consistency)
and the [decision contract](./NATIVE_WORKSPACE_PROPOSALS_V1_CONTRACT.md).
The 2,595-case full run remains pinned at `1aeded3` and does not cover later corrections.
The subsequent selected package-history extension is recorded above. It reuses existing
package confirmation and retained import origins; its broader acceptance remains incomplete.
Public approval remains only `d864c51`; PR #271 CI failed and `8bce0b0` still needs separate
publication approval. Keep later local work separate, with no live/provider execution.

## Local assistant session-error correction

The actual main-app HTTP rehearsal established that an expired browser login returns
303 to the login page. The native scripts previously treated the final200 HTML as JSON,
showing parser details. The isolated session-error correction now shows a fixed sign-in
instruction for same-origin login redirects and401 responses. Unexpected content types
or malformed JSON produce fixed messages; unauthorized attachment cards are cleared.
Known service errors and normal responses are preserved. No authentication, authority,
API, migration, model, confirmation, retry or redirect policy changes are included.

The regression executes both shipped scripts with a minimal event/DOM surface. Its final
expectations reproduced16 failures against unchanged0ef73d0 assets, then all25 cases
passed on the correction. The pytest wrapper and nearby UI tests passed42 cases, with
one warning and no skips. Node.js is an optional test tool: pytest explicitly skips this
script test when Node is unavailable; run the standalone script check where available.
These are script behavior checks, not browser rendering or live acceptance.
The full2595-case run remains pinned at1aeded3 and cannot cover this later script fix.
All newer work remains local; public approval still covers only d864c51.

## Real-app restart and full-suite checkpoint

The parent d33f5ec/0048 full suite completed: 2,574 passed, two skipped, 386 warnings
in 6,264.19 seconds. Both Windows symlink skips remain recorded. A separate network-disabled
Linux arm64/Python 3.12.14 storage run now passed 18 cases with no skips, including both
file and directory symlink protections. The storage service/test files are unchanged
since d33f5ec. Declared dependency ranges, pip check and mounted source hashes passed;
this is not a full Linux suite or deployment certificate. The parent result does not
cover the newer decision schema. The first full 0049 run completed from pinned `1aeded3`:
2,593 passed, two Windows symlink skips and386 warnings in7,243.62 seconds, using selected
PYTHONPATH and fresh basetemp on disposable15433. Its terminal exit and XML were verified;
it does not cover later changes. No timed-out CI job was restarted.

Actual `classifire.main:app` startup and restart passed over HTTP on isolated8837,
using a separate migrated synthetic15433 clone. Two distinct Uvicorn processes reopened
both decisions, exact Scope revision 3 and the unchanged original-bearing Scope2 ZIP.
The served JavaScript matched the checkout. Startup metadata/bootstrap changed no rows
or tables. Unauthenticated history redirected to the exact login return path; repeated
rejection returned409 without new writes. Each fresh login/download session changed only
login fields and the two expected Scope/package download audits. Both owned processes
stopped cleanly, port8837 was released and the source recovery fixture remained unchanged.
No provider, scanner, new Scope/package confirmation, live activation or OAuth/tunnel ran.

The private `native-decision-http-restart-20260914/attempt3` receipt records this pass.
The first two private-driver failures remain preserved: the full app translates401 to
303 login redirect, and the two separate downloads produce two audits. Their assertions
were corrected to the exact existing behavior; application code/guards were unchanged.
This verifies HTTP and actual server restart in test mode, not rendered browser behavior
or production configuration. Browser automation still fails initialization with
helper_unknown_error; visual interaction and browser reopening remain unverified.

## Local native proposal decisions (targeted validation complete)

`feat/native-proposal-decisions-20260914` extends local `d33f5ec` in an isolated
worktree. It links explicitly saved proposals to their later human Scope confirmation
or explicit rejection through the existing Word/PDF/XLSX/manual review paths. A separate
immutable decision record references the exact saved revision; original generation is
unchanged. Matching manual content without a link never implies acceptance. Rejection
and failures save no Scope change; package and canonical authority remain separate.

Forward migration0049 adds the decision table and required integrity constraints.
Readiness and only audited current-head test expectations advance; historical0048/0047
targets stay intact. This is not deployment approval. The prior full suite completed
on d33f5ec/0048; the newer pinned1aeded3/0049 run completed2,593 passes and two skips,
with386 warnings. Later changes retain their separate targeted validation.

Local validation passed 16 distinct new HTTP/provenance cases across the targeted runs,
96 existing native regression cases, 49 SQLite migration/readiness/packaging cases,
25 affected current-head caller/migration cases and all three PostgreSQL history cases.
The final seven-case run passed in 334.723 seconds. The initial failures are preserved:
the disabled-actor expectation needed the existing exact 401 denial, and the PostgreSQL
downgrade expectation needed the new 0049 refusal message. Neither production guard was
weakened. All three PostgreSQL history cases passed after that expectation correction.

Full Ruff, Mypy (239 source files), Bandit, JavaScript syntax and diff checks passed.
The exported synthetic decision and Scope bytes were inspected: exact generation and
Scope hashes, actor/Draft/revision bindings, two retained source references and disabled
repeat-review controls matched. The blank opening still has zero Services, unknown
dimensions/substrate and Unresolved state; Scope remains an unreviewed Draft.
The private `native-proposal-decisions-validation-20260914` receipt retains actual results.
The selected environment satisfies declared dependencies; PostgreSQL work used only
owned disposable 15433 databases/schemas. No real provider/scanner, customer report,
live database, activation, OAuth or tunnel change occurred.

Browser automation failed during initialization with `helper_unknown_error`, including
a reset/retry. That attempt started no test server. A later actual-app HTTP/server
restart passed as recorded above; visual interaction and browser reopening remain unverified.
Keep this limitation visible before publication or activation. Public approval still
covers only d864c51 and its12 files; the one-file8bce0b0 correction and all newer local
ancestors require their own exact publication scope. No C2/C3 or production exit is claimed.

## Synthetic 0049 recovery checkpoint

Local implementation `b3c2203` passed a matched backup/restore rehearsal using three
newly owned databases on disposable PostgreSQL15433. Actual pg_dump/pg_restore archives
restored the 0048 baseline (70 tables/23 rows) and 0049 candidate (71 tables/32 rows)
with all table row hashes matching. Restored application schemas also matched, including
1,179 candidate columns, 450 constraints and 398 indexes; row-security definitions matched.
Existing data survived migration; copied retained storage was recovered at its exact owned
path. Source fixtures remained unchanged.

The existing HTTP review paths explicitly rejected one historical synthetic proposal
and separately confirmed another into Scope revision 3. One scripted reply, no real
provider or scan, supplied the new proposal. Both decisions and unchanged original
generations reopened identically in a fresh Python process. The exact original-bearing
ZIP stayed at Scope revision 2; no new package was implicitly approved. Unknown opening
facts and zero Services remained. Duplicate confirmation was refused without new writes.

Downgrade refused retained-decision deletion. Prior d33f5ec code accepted the restored
0048 backup and refused the newer0049 schema. Restoring0048 loses the post-backup Scope
revision/decisions unless separately preserved and reconciled; code-only rollback is
not assumed. Dump options excluded owner/ACL restoration, so this is not production
roles/grants recovery evidence. This is a synthetic HTTP/new-process check, not browser
or server-restart acceptance, live backup, activation or technical/customer validation.
The private `native-decision-recovery-rehearsal-20260914` receipt and archives preserve
actual results. Complete new-control visual/browser acceptance and candidate CI next.
The later HTTP/server-restart proof and distinct parent/candidate full runs are recorded above.

## Preceding integration and deployment-readiness correction

The preceding saved-history stack reached `5d00b6c` (38 files versus shared `97c0778`).
The closed-review attachment test was already reconciled for Word/PDF/XLSX in
2fea699/8441195; do not rebuild the public Word-only correction in this stack.
PR271 remains at approved d864c51 with failed CI; one-file8bce0b0 still needs its
separate publication approval. Neither approval covers the newer feature range.

Integration inspection found that the read-only deployment-lineage service still
expected 0047 and omitted the new proposal table. Four regression cases reproduced
its disagreement with the packaged 0048 migration, rejection of valid 0048 and false
readiness for 0047. The local `fix/native-history-startup-lineage-20260914` correction
now requires 0048 and `draft_workspace_proposals`; 0047 and 0046 remain recognized
migration-required histories. Canonical preflight/admission callers retain all
other guards. The architecture remains the same deterministic core; this aligns
existing readiness checks with the already-added migration, without changing an
operational database or granting operational authority.

Only audited current-head expectations and the current-model test fixture change.
Historical Word0047 targets and all deployed migration files stay unchanged. The
packaged-head agreement regression prevents this production constant drifting
silently at the next migration. Validation results belong in the private integration
and correction receipts. The later parent full-suite result is recorded above; hosted CI
and the newer0049 candidate full run remain separate gates.
The earlier immutable-baseline full run was stopped after 225 logged passes because
of the reproduced version defects, not an observation timeout. Its partial log is
preserved; it is not a passing full run. Complete validation on the corrected version
before preparing the exact full-range publication request. No live PostgreSQL15432, provider,
activation, OAuth or tunnel changes are included.

The shared test environment was found to have pytest9 and cryptography50, outside
the declared pytest<9/cryptography<46 ranges. It is preserved. A separate environment
under `.tmp/native-stack-test-env-20260914` now satisfies every declared dependency
constraint, with pytest8.4.2/cryptography45.0.7 and a clean pip check. All74 affected
checks passed there (252.285s; two warnings reported), including actual
PostgreSQL15433 readiness and retained-history checks. Full Ruff, Mypy238 and
Bandit passed. The corrected d33f5ec full suite later passed2,574 cases with two Windows
symlink skips; the newer0049 candidate run remains pending.

## Native saved-proposal history checkpoint

Local `feat/native-proposal-history-20260914`, based on `eae7ee0`, adds explicit
**Save proposal for later** and **Saved AI proposals** within the existing assistant.
Word/PDF/XLSX additions and selected Scope replacements retain their exact disclosed
context, included conversation, validated generated fields and prepared review data.
Generation remains read-only; retention is a separate Draft write and Scope/package
confirmations stay separate. Current ownership, rights, source integrity and scan
checks apply on reopening; changed revision/context disables the old review controls.

The [history contract](./NATIVE_WORKSPACE_PROPOSALS_V1_CONTRACT.md) defines the
1 MiB/100-per-Draft limits, 15-minute signed save authorization and forward migration0048.
This is a local, unpublished schema change, not an activation. Prior source head0047
and live runtime receipts below are historical; no live database or runtime changed.
The synthetic browser passed explicit retention, exact review reopening, separate
Scope/package confirmation and byte-identical original-bearing ZIP download. Restart
reopened the exact historical record and ZIP with no scan/model/save replay. See the
private validation receipt for final checks and limitations. The 23 new history/migration
checks passed without failures or skips (651.156s). Narrow browser inspection also
found and corrected scrollbar-related mobile clipping; the panel now fits inside
the 390px viewport with no horizontal overflow. The affected existing proposal/chat
regression added 107 passes (523.680s), for 130 distinct passing
cases overall. Full Ruff, Mypy over238 files, full Bandit and JavaScript syntax
also passed. This is targeted validation, not a full-suite or hosted-CI pass. Retention does not yet
link later decisions or include proposal history in ProjectPackage; full AI lineage
and operational acceptance remain incomplete.

PR271 remains open at approved `d864c51`: its existing CI failed after639 passes on
an obsolete closed-review form count. The isolated one-file correction `8bce0b0`
passed30 affected checks but still needs publication approval. All newer feature
commits and this history slice remain local. Preserve the conflicted root and the
live rollback checkout. Do not fold the unpublished stack into the approved12 files.

## Earlier native Excel proposal checkpoint

Use `.tmp/native-xlsx-scope-proposals-20260914`, branch
`feat/native-xlsx-scope-proposals-20260914`, based on local8441195. Explicit worksheet,
header, data rows and pictures now reuse the selected-evidence preview/consent and
proposal transport. Mapping and typed additions go through the existing signed
workbook review, then a separate save. Package confirmation stays separate. The
synthetic browser saved unknowns and a blank opening without Services and downloaded
an exact original-bearing ZIP; a fresh browser after restart returned identical bytes.
Inspect the private validation receipt for final test and visual evidence. No provider,
live database, schema/migration, activation or public push is included. Existing human
row/entity references are durable; raw AI claims and unsaved controls are not.
Review the complete local stack after the pending PR271 correction approval/CI;
decision/revision linkage is now implemented in the later local checkpoint above.
Selected portable history now has targeted regression, actual-main HTTP/server restart
and exact synthetic recovery evidence. Visual/browser and operational acceptance remain;
actual-app HTTP/server restart passed in the later checkpoint above.

## Earlier native Excel panel checkpoint

Use `.tmp/native-xlsx-attachments-20260914`, branch
`feat/native-xlsx-attachments-20260914`, based on local0c6767a. Supported XLSX
attachment/scan and five-row worksheet/cell/image inspection now use the existing
native adapter/driver, with exact original download and selected-sheet mapping links.
No workbook data enters AI requests yet. Formula values remain unevaluated, picture
anchors are not physical ownership, and Scope purpose never adopts pricing authority.
The existing closed-review test now expects three independent attachment forms.
Inspect the private validation receipt for actual final tests and browser results.
This branch and its parents remain local. No provider call, live change or activation
is included. Next add explicit workbook model selection and source-bound typed review.

## Earlier native PDF proposal checkpoint

Use `.tmp/native-pdf-scope-proposals-20260914`, branch
`feat/native-pdf-scope-proposals-20260914`, based on local2fea699. Explicit PDF page
text/image selection now reuses the native context/consent transport and typed
additions composer. The separate signed PDF page review saves the exact graph;
a separate package confirmation includes the exact PDF. Synthetic browser acceptance
and reopening after test-server restart passed. Unknowns and blank openings remain.
The existing human page/entity references are saved; raw AI claims and unsaved proposal
controls remain transient. Inspect the private validation receipt for final tests.
No new writer, migration, provider call, live change or public push is included.
Broader XLSX coverage, durable AI lineage and operational acceptance remain.

## Earlier native PDF panel checkpoint

Use `.tmp/native-pdf-attachments-20260914`, branch
`feat/native-pdf-attachments-20260914`, based on localb330266. The Word attachment
adapter/driver now also exposes retained PDF upload, explicit scan, paged text/PNG,
exact original download and selected-page navigation to existing review. It adds
no parser, provider configuration, migration or write authority. PDF evidence is
not yet part of native chat model context. Initial six native tests passed; the
browser found missing evidence-block styling for narrow PDFs, which was corrected.
100 affected tests, full Ruff/Mypy236, scoped Bandit and JS syntax passed. Final
browser desktop/narrow checks and test-server restart preserved exact PDF bytes,
Scope revision1 and zero provider calls. The earlier collapsed-text harness assertion
was corrected without changing the review page. Inspect the private receipt for detail.

This branch locally extends the closed-review form assertion for separate DOCX
and PDF uploads. PR271 still needs its own approved correction publication/CI;
no new branch has public approval. The newer checkpoint above implements explicitly
selected PDF context and typed review using existing PDF contracts. Preserve all
separate consent/confirmation gates. Do not rebuild the plugin or PDF parser.

## Current selected-record edit checkpoint

Use `.tmp/native-selected-scope-edits-20260913`, branch
`feat/native-selected-scope-edits-20260913`, based on local9d64bd1. The explicit
selected-Scope action returns complete selected-record replacements and a field diff.
Review only validates in the existing manual editor; a separate save creates a
revision. Unselected rows and source references remain, with changed claims marked
for review. No migration or new write authority was added. 147 distinct checks passed (145 affected regressions plus two added cases); full
Ruff/Mypy236, scoped Bandit and JS syntax passed. Browser restart and unsaved-edit
guards passed, with exact saved bytes and no extra writes. Desktop/narrow/unsaved-editor
outputs were inspected. The private receipt retains earlier fixture/harness failures.
No real provider or live activation was performed.

Keep this increment and its unpublished parents separate from the exact12-file
approval for d864c51. Resolve the pending8bce0b0 correction approval for PR271, then
review the full local commit stack before publication. Scope proposals are locally
implemented; broader report formats, non-Scope actions, durable AI proposal lineage
and operational acceptance remain. Do not rebuild the proven synthetic journeys.

## Current native proposal checkpoint

Use `.tmp/native-word-scope-proposals-20260913`, branch
`feat/native-word-scope-proposals-20260913`, based on local8bd0d7f. The composer
prepares new Word-derived Defects/Openings/Services for the existing session-bound
Word review; the model never saves. All existing rows and unknown values survive.
127 checks passed (126 affected regressions and one added contract test); full
Ruff/Mypy, scoped Bandit and JS syntax passed. The final synthetic Chrome journey
proved separate evidence consent, Scope confirmation and original-bearing package
confirmation/download. Screenshots and ZIP bytes were inspected. Exact results and
limits are in PROJECT_STATE.md and EMBEDDED_WORKSPACE_CHAT.md.

This branch and selected-evidence8bd0d7f remain unpublished. The new increment adds
no migration, dependency or runtime change. New Word observation claims, durable
raw model history, real-model accuracy and operational acceptance remain incomplete.
Resolve the PR271 correction publication gate, then review the complete local stack
before publishing. Broader formats remain roadmap work; the newer selected-record checkpoint is above.

## Earlier native evidence checkpoint

Work is isolated in `.tmp/native-word-chat-evidence-20260913`, branch
`feat/native-word-chat-evidence-20260913`, initially based on d864c51. It adds selected
Word text/PNG evidence to the existing preview/consent/advice path.94 affected tests,
full Ruff/Mypy, scoped Bandit and a synthetic browser/restart journey passed. Final
desktop/narrow screenshots were inspected; zero real provider calls or live changes.
See PROJECT_STATE.md for the newer typed proposal acceptance and remaining operational boundaries.

PR271 contains approved d864c51. Run34757320145 failed after639 passes on an obsolete
closed-review form assertion. Local correction8bce0b0 adds one test file and passed30
affected checks; approval to publish that extra file is pending. Do not merge the
failed head or treat local tests as hosted CI. CI logging commitbf700bc remains local.

Diagnostic PR270 is merged, but post-merge34753856708 cancelled at45 minutes; it was
not restarted. Live8820 remains rollback6c1e2a4 with chat disabled. Separate exact
operational approval and successful applicable CI remain required.

## Verified publication

- Workspace PR #260 merged as `3eabb23`; exact-head and post-merge CI passed 2,113
  tests. PR #261 merged as `095ee3d`; both runs passed 2,127 tests.
- Row authoring PR #262 merged as `48b4b11`; both runs passed 2,134 tests.
- Packages PR #263 merged as `d5c19d7`, equal in tree to tested `469a57f`.
  Exact-head run 34711480773 and post-merge run 34712796245 passed 2,199 tests.
- Scope multi-review reporting PR #264 merged tested `ccaff7a` as
  `e96c6928ffdbc11a9bd2fb890105e83f05c87625`. Exact-head run 34713651083 passed
  2,251 tests and all checks. Full merged tree equality was verified. No required
  reviews were configured; no human GitHub review is claimed. Post-merge run
  34715038796 passed 2,251 tests and all remaining checks.

## Latest publication and CI

- The four owner-approved workspace commits merged through PR #265 as `0e9bf98`.
  Its PR CI passed 2,399 tests; post-merge run `34726463470` failed a midnight-sensitive
  test and hit the 30-minute limit. That failed result remains preserved.
- PR #266 merged the separate clock/CI-limit repair `7c9b570` as `96fdf7a` after
  2,399 passing tests and the remaining checks. Its post-merge run `34729555434`
  cancelled at 45 minutes without a final test summary. The broad slowdown's cause
  remains unestablished; the run was not restarted or counted as a pass.
- Documentation PR #267 merged candidate `6c1e2a40a6448cc1facda2436f7780651408741d`
  as `6012d159f0669e704a45d12db2eaf81b1d4cac80`, with exact full-tree equality.
  PR CI [34729664769](https://github.com/Slayde91/classifire/actions/runs/34729664769)
  passed 2,399 tests in 1,701.99 seconds; post-merge
  [34731006875](https://github.com/Slayde91/classifire/actions/runs/34731006875)
  passed 2,399 in 1,769.11 seconds. Both passed the remaining required checks.
  No human GitHub review was required or claimed. Publication did not grant activation.

## Verified workspace activation

The owner separately approved and activated tested `6c1e2a4` on 2026-09-13 after
successful exact CI and a fresh matched backup/disposable restore. The private
`activation-result.json` records `activated_verified`; its 20 referenced artifacts
were rehashed during this reconciliation. The 8820 listener was observed as PID
33032 (parent 13708) at acceptance; process IDs are historical observations.

The fresh backup/restore matched 69 tables and 80 rows. Fourteen raw CHECK strings
required the individually allowed cast-placement proof; 28 typed evaluations passed.
Other schema, objects, required roles/grants/ownership and retained files matched.
Metadata/bootstrap were no-ops. No migration or stamp ran: the observed demo still
has no Alembic version table. This is not a migration-history certification.

Reopening retained Scope revision 2, native Word evidence and the original-bearing
Word ZIP passed; the older Excel package also matched exact bytes. Domain rows and
storage remained unchanged. The only accounted changes were login timestamps and
two package-download audit events. The expired one-time confirmation URL stayed
expired; the normal saved-project route worked. No confirmation was repeated and no
new Scope, package, Match, Estimate or report was created.

At the earlier 6c1e2a4 activation, workspace chat/PDF suggestions stayed disabled
and no provider, OAuth/tunnel, host allowlist, role or grant change occurred. No saved Match, Estimate, report or imported
project existed in this demo, so those operational histories were not exercised.
This is retained synthetic-state acceptance, not customer accuracy, production
certification, storage relocation or full-cluster disaster recovery. Historical
activation plans stay preserved; recovery retains the approved compatibility and
no-lost-work conditions for the older `e2e8292` rollback source.

## Current embedded-chat and documentation checkpoint

PR #268 is merged: tested 7dbc1cc13b2501b6a449990abc36e330932b42c0 became
a7e2e7aadd8860636432cb68127a0e83e3a9785c with identical full trees. PR validation
34736343454 passed 2,428 tests and the remaining checks. The earlier PR test-contract
failure remains recorded; no production guard was weakened. Local acceptance
comprised 147 affected cases and a synthetic browser journey using injected replies.

The owner subsequently supplied protected server-side gpt-5-mini configuration and
approved one synthetic connection test plus conditional activation of tested 7dbc1cc.
Exactly one real request passed strict response/reference checks and preserved unknown
quantity/substrate without claiming a write. The complete reply was inspected.
Preparation also reran 55 chat tests and passed 47 activation plus 47 rollback guards.
No live database was used for those tests; this is not customer accuracy or real
browser upload/assistant acceptance.

Post-merge run34737578361 attempt1 remained queued without a runner for over three
hours. After the owner explicitly requested a retry, it was cancelled and attempt2
started on the exact same merge commit. Attempt2 passed
2,428 tests (385 warnings) in 1,971.54 seconds plus full Ruff, Mypy (233 source
files), Bandit and the single migration-head check; exact hosted output was read.
This authorized retry is distinct from restarting because observation timed out.

The approved 7dbc1cc activation was attempted after successful CI and fresh
backup/disposable 15433 restore. Startup and the first browser reply passed; the
follow-up returned HTTP 502. No retry occurred. Both browser sends are consumed.
The transport erased the failure category, so the historical cause is unknown;
neither billing nor a timeout is established.

Rollback to 6c1e2a4 with chat disabled passed fresh recovery, restart and browser
checks. Scope revision 2, Word text/image and the original-bearing ZIP remained exact.
All domain rows, schema and storage were preserved; only login timestamps and one
package-download audit event changed. No migration or live database restore occurred.
Existing project, Scope and package confirmations remain complete. The first reply
also broadened uncertainty about source-described separate openings; that unverified
wording did not change saved records or establish report accuracy.

The current diagnostic fix records fixed failure category, elapsed time, received
byte count, HTTP status when available and a random per-request reference. No
exception text, body/header, conversation, context or credential is logged.
Browser errors, model, time/token limits, no tools, no retries and confirmation
boundaries are unchanged. Offline validation passed 77 chat cases, including the
reproduced missing-diagnostic regression and synthetic follow-up/partial-read failures.
Any further provider test and activation need a fresh explicit approved plan.

Private exact approval/test/activation receipts are retained under
.tmp/workspace-chat-activation-7dbc1cc-20260913; no credential values or customer
evidence are included in these documents. Reobserve actual CI/runtime facts before
execution rather than treating this checkpoint as a fresh activation proof.

### Clarified product intention and current gap

The owner requests defect-report upload through the ChatGPT integration inside
CLASSIFIRE and interaction with the data on the current page. The native panel is
merged and can discuss selected saved data; its endpoints currently accept only
context/message; the original selected-record increment had no attachment input or write action. Existing PDF/Word/XLSX
intake, scan, review, typed client requests and package services are foundations.

The [architecture](./CLASSIFIRE_ARCHITECTURE.md#native-chat-as-a-working-interface),
[C1-C3 roadmap](./CLASSIFIRE_ROADMAP.md#embedded-chat-delivery-sequence) and
[assistant contract](./EMBEDDED_WORKSPACE_CHAT.md#approved-target-experience) now
describe the same target: attach and inspect a retained report, explicitly request
analysis, review a source-bound typed Draft proposal, confirm separately, refresh
the page and reopen/download exact saved artifacts. Later selected-record actions
reuse that review path. Uploaded content never becomes instructions or authority;
original-file transfer is excluded; selected Word text/PNG transfer is now implemented
and synthetically validated in the checkpoint above.

Accuracy preparation is separate. The existing comparator fix is already merged in
PR #261. Twenty-four unchanged synthetic comparison/blocked-run checks passed in
this checkout with explicit PYTHONPATH and a fresh basetemp. The private reference,
original and photo hashes and authority limits are retained in a private run plan.
No customer-report analysis, photo inference, real provider or database evaluation
ran during this preparation; no accuracy score exists. [Reference readiness](./PHYSICAL_REFERENCE_READINESS.md)
records the incompatible unresolved-topology contract and remaining Phase 8/8C gates.

## Merged imported-original navigation

Separate checkout `.tmp/imported-evidence-navigation-20260913`, branch
`feat/imported-evidence-navigation-20260913`, base `1de68b9`. Connect a selected
imported evidence reference to its exact retained-original review card through the
existing validated package mapping. Preserve lineage, foreign unverified claims,
current access and explicit scan/download actions. No inline imported preview,
new parser/schema or approval is implied. All 94 distinct affected cases passed:
30 core (seven new), eight new HTTP and 56 existing UI cases. Full Ruff, Mypy (233
files), Bandit and single 0047 head passed. Final read-only source review found no
issue. Private logs retain the corrected harness failures and formatting-only hash
drift; no application guard or assertion about required behaviour was weakened.

Browser acceptance retained all 67 checked domain tables before explicit scan,
refused an unprocessed download, then returned exact DOCX/original ZIP bytes after
explicit scan. Imported claims stayed unverified. Desktop/mobile, original identity
and ZIP members were inspected. Restart preserved the same review link/anchor,
DOCX, ZIP, Scope revisions 2/3 and all 67 tables without rescanning or package writes.
Only the new isolated demo 8847 and disposable 15433 database were used.

Private artifacts: `.tmp/imported-evidence-navigation-uat-20260913`,
`.tmp/imported-evidence-validation-20260913`,
`.tmp/imported-evidence-core-validation-20260913`, and
`.tmp/imported-evidence-ui-validation-20260913`. Earlier completed fixtures and
runtimes remain untouched. Nine files are classified: four application, two synthetic
test and three documentation files. The local commit message is:
Link imported evidence to exact retained original review cards.
Resolve its exact hash from this branch and the private finalization receipt.

All four pinned commits are published through PR #265. Explicit owner approval
resolved the public-destination block. Source `9cdc4a4` tracks its published branch;
the earlier separate candidate checkouts are preserved. Publication is not activation
approval, and failed post-merge CI blocks the old activation bundle.

## Merged Defect-only source inspection

Source `.tmp/defect-source-evidence-20260913`, branch
`feat/defect-source-evidence-20260913`, based on clean pinned `51e3666`. It extends the
existing read-only Evidence service and panel to select a Defect without an Opening
or Service, returning only its own references. Missing relationships stay unresolved;
no physical record is invented. No schema, parser, provider or authority changes.

All 89 affected cases passed (23 native/core, 52 HTTP, 14 workbench/history), plus
full Ruff, Mypy (233 files), Bandit, JavaScript syntax and single 0047 head checks.
The native/core receipt pins the service/test hashes. The HTTP pass was observed in
the test session; no JUnit XML or test-time hash manifest was captured for that run.
Edge acceptance checked exact own-source selection, stale/history retention, keyboard
focus, unsaved-edit exclusion, desktop/mobile output and refusal of a deliberately
mismatched Defect fragment. Restart retained five image URLs, Scope revisions 1-4
byte-for-byte and all 67 checked domain tables. No invented Opening/Service, provider
call or live 15432 contact. Synthetic sources do not prove real-report accuracy.

Private evidence: `.tmp/defect-source-evidence-uat-20260913` and
`.tmp/defect-evidence-validation-20260913`. Use only the existing disposable 15433
`classifire_defect_evidence_demo_20260913` database and port 8846 demo. Preserve
completed fixture receipts and earlier pinned source/activation plans.

Final source review found no actionable issue. The reviewed change contains six
application files, two synthetic test files and three documentation files. The local
commit message is: Allow source inspection for Defects with unresolved relationships.
Resolve its exact hash from this branch and the private finalization receipt.
Commit `1de68b9f41582fc5297260d3a838e2851a4defbb` remains pinned and is included
in merged PR #265. The later exact `6c1e2a4` approval and verified activation above
supersede earlier pending-activation instructions.

## Merged register source evidence increment

Source: `C:/CLASSIFIRE/.tmp/register-source-evidence-20260913`, branch
`feat/register-source-evidence-20260913`, based on local `6d4793b`.
The read-only [Evidence tab](./REGISTER_SOURCE_EVIDENCE.md) is implemented; 122 unique
affected cases and static checks passed. Mixed-source Edge acceptance passed including
stale, blank/unlinked and unsaved-edit checks with unchanged domain state. Restart
retained 12 image URLs, three Scope downloads and all 67 checked domain tables exactly;
source-cell F2 passed. Continue from private `.tmp/register-source-evidence-uat-20260913` and
`.tmp/register-evidence-validation-20260913` receipts.
The marked demo uses only PostgreSQL15433 and port8845; never use live15432 for tests.

The separate Complete-report checkout remains pinned at `6d4793b`. It and register
Evidence are published in PR #265. No repository visibility/protection setting or
operational runtime changed during publication.

## Merged Complete report increment

Checkout: `C:/CLASSIFIRE/.tmp/complete-multi-review-reports-20260913`.
Branch: `feat/complete-multi-review-reports-20260913`, based on merged `e96c692`.
Source `6d4793b` is locally verified and published through PR #265. The pinned
ccaff7a checkout is preserved; its old plan does not cover this Complete format.

[Complete contract](./DRAFT_COMPLETE_REPORT_CONTRACT.md) and
[multiple-review contract](./MULTI_REVIEW_REPORTS.md) describe the actual change:
explicit exact review collections for Complete reports, snapshot v3/render 12,
unchanged Estimate arithmetic/dependencies, separate confirmation, technical grant
checks and package import mapping-v4 reuse. No model or migration changes.

Focused checks passed 53 core/package/legacy cases, 24 UI, 18 outputs, 13 client
collection and 10 existing client cases. Full Ruff, Mypy (233 files), Bandit and
single 0047 migration-head checks passed. Final combined verification passed all 62 new cases in 185.29 seconds, including
actual disposable PostgreSQL import/scan checks.

Actual Edge UAT on port 8844 retained Scope 2 and Estimate 4 with three selected
reviews. Original rate 1.005 and override 1.505 yield partial subtotal 3.01; another
line remains unknown. Report creation and package save were separate. PDF/XLSX/ZIP
bytes matched retained originals. All 21 PDF pages were visually inspected in
overviews, pages 1/3 at readable size, plus desktop/mobile screens. No clipping or
page errors observed. Native Excel was not visually inspected.

An actual restart preserved Scope/PDF/XLSX/ZIP and 66 domain-table hashes. The first
Estimate comparison used a fixture's reformatted JSON; diagnosis proved identical
values and the original ZIP's exact Estimate bytes. A second restart retained raw
Estimate 2/4 downloads byte-for-byte. Keep the original failed verifier and diagnosis;
no application guard or assertion was weakened.

Private evidence: `C:/CLASSIFIRE/.tmp/complete-multi-review-reports-uat-20260913/`
contains browser/restart receipts, screenshots, PDF/XLSX/ZIP, original diagnosis,
verification scripts and synthetic SQLite data. Related output validation is in
`complete-multi-review-output-checks-20260913/`; UI tests in
`complete-multi-review-validation-20260913/`. Do not rerun creation scripts against
these completed fixtures.

## Runtime and approval boundaries

Live 8820 was restored to 6c1e2a4 with chat disabled after the failed 7dbc1cc
follow-up. Preserve both private activation/rollback receipts and failed observer
attempts; corrected read-only checks passed. The original single connection request
and both browser sends are consumed.

The current user authorized diagnosis, evidenced fixes, offline tests and normal
Git publication/merge after successful CI/reviews. New provider requests and activation
require a separate exact approved plan. Preserve pinned runtime checkouts and old
plans; no OAuth/tunnel/allowlist or customer-report operation is included.

Other preserved synthetic demos: 8840 integrated workspace,8841 row authoring,
8842 packages,8843 Scope reports. Only 8844 was restarted for this Complete acceptance.
PostgreSQL tests use disposable 15433/classifire_containment_test, never live 15432.

## Classification and next action

The approved six-document commit 95d90de was pushed and merged through PR #269 as
89e58ef after successful PR CI 34747466912. No post-merge run for that merge was visible
at diagnosis; do not claim it passed or trigger another job to replace missing evidence.

Diagnostic commit `5454b36` is published through PR #270 as `97c0778`; preserve
its pinned checkout and unapproved operational plan. The new attachment branch
contains the thin Word browser adapter, native panel controls, synthetic tests and
six reconciled documents. Private browser fixtures, screenshots, retained originals
and CI receipts stay outside Git. The root retains 46 unstaged modifications,
14 staged additions and four DU conflicts; preserve its unrelated untracked files.

Native typed Word additions now reach the existing separate human review from the
panel. The synthetic package journey also passed; operational gates remain separate.
Inspect exact branch/PR status before publication or merging. Do not count the first
attachment interaction as complete C2, representative accuracy or production readiness.

## Copy-ready next-session prompt

Continue CLASSIFIRE from current repository evidence. Read AGENTS.md, GOAL.md,
docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md, docs/CLASSIFIRE_ROADMAP.md,
docs/EMBEDDED_WORKSPACE_CHAT.md and docs/NATIVE_WORKSPACE_PROPOSALS_V1_CONTRACT.md.
The shorter architecture/roadmap aliases are absent. Preserve the conflicted root,
pinned runtime and private receipts. Reconcile Git/worktrees, exact upstreams and
PR/CI before selecting work; newer local evidence outranks old checkpoints.

Start with feat/portable-native-history-20260914, based on c837ce5. Inspect its current
status, the selected-history contract and private portable-native-history-validation-20260914
results. The 77-case regression, eight final HTTP/UI checks and three compatibility cases
passed. Application23f5110 also passed actual-main HTTP restart and exact synthetic recovery;
read native-history-http-restart-23f5110-20260914/attempt3 and recovery/continuation-receipt.json.
Preserve the earlier harness failures, source locks and rendered-browser limitation. Do not
repeat completed recovery work. Review the entire unpublished ancestor range before any
public approval request; the Word-only8bce0b0 correction remains separately approval-blocked.
The candidate uses0049. Parent d33f5ec completed2,574 passes/two Windows symlink skips;
the full0049 run at1aeded3 completed2,593 passes/two skips,386 warnings, with terminal exit0
and XML verified in native-decision-full-validation-20260914. Neither full run covers later
fixes or portable history; preserve their separate targeted evidence. The same
native panel retains/reopens proposals and now links optional saved identities through the
existing four review transactions. Confirmation records the actual reviewed Scope revision;
explicit rejection records no Scope change. Original generation is unchanged, and a later
matching manual revision never infers a decision. Source preview signatures bind the identity;
current owner/rights/context, atomicity and one-decision checks remain required. Package
confirmation and canonical authority are separate. New-control visual interaction and
browser reopening remain unverified because the browser helper failed initialization.
Actual classifire.main app startup/restart on isolated8837 passed over HTTP, with exact
decisions and Scope/ZIP bytes and accounted login/download audits. It does not prove UI clicks. The private0049 recovery rehearsal
passed exact baseline/candidate database and retained-file restores plus both decisions
in a fresh Python process; it did not verify browser/server restart or production grants.
Both migrations are forward-only.
Activation needs a new exact approved backup/restore/restart/rollback plan and successful CI.
Never rehearse on live15432. Selected portable native history is implemented locally;
its remaining acceptance and full operational/history coverage are not complete.

PR271 contains approved d864c51 and12 files. Its CI failed after639 passes on an
outdated form assertion; local one-file8bce0b0 passed30 checks but needs separate
publication approval. Do not publish the newer feature stack through that approval.
Reconcile all unpublished ancestors before preparing a new exact publication scope.
PR270 merged5454b36 as97c0778; post-merge34753856708 cancelled without a full test
summary. Poll existing live jobs; observation timeout is not permission to restart.
Live8820 remains rollback6c1e2a4 with chat disabled; old provider allowances are
consumed. No real provider, customer evidence or activation is implicitly authorized.

Use the selected checkout's PYTHONPATH, fresh basetemp and disposable15433. Keep
blank openings without Services and unresolved links/quantities explicit. Inspect
browser/ZIP outputs, classify explicit files, publish only within approved scope and
merge only after observed successful CI and required reviews. The full production
objective, technical/commercial validation and Phase8-16 gates remain incomplete.
