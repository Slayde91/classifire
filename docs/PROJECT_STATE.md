# CLASSIFIRE Project State

Reconciled 2026-09-14 during local saved-proposal history validation. Selected-record edits and
Word proposal evidence are retained below. Live chat remains rolled back.
[Workspace acceptance](./INTEGRATED_WORKSPACE_ACCEPTANCE.md) records implemented
behaviour and unmet redesign criteria. [The earlier Word record](./WORD_ACCEPTANCE_ACTIVATION.md)
retains its original acceptance evidence. Private operator receipts and customer
material remain outside Git. This is not a production-readiness certificate.

## Local native proposal concurrency correction

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

## Local saved-proposal list ordering correction

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

## Local package-history choice correction

`fix/native-history-package-choice-20260914` extends `3bdc27d`. Review reproduced a
missing UI choice: once a decision existed, the package form offered the proposal
only together with that decision. Each proposal now has an explicit excluded,
proposal-only or proposal-with-decision choice. Existing preview/save and versioned
history formats remain unchanged; Scope and package confirmation remain separate.

Two focused synthetic HTTP/form and query cases passed on disposable15433 in 82.60s.
Both ZIPs and page structures were inspected: generation and Scope bytes are identical,
with decision membership exactly as selected. No unselected originals were added;
local decisions and earlier downloads remain unchanged. Blank form choices preserve
legacy selection encoding, while malformed, duplicate and over-limit references fail.
Full Ruff and Mypy240 passed. Private evidence is in
`native-history-package-choice-validation-20260914` under .tmp. The first reproduction
was too specific about control type; its replacement demonstrated the missing user
choice on unchanged source. Both failures remain recorded. Browser acceptance and
full-range manual publication review remain incomplete; this work is unpublished.

The ten existing history, compatibility and package-page regression cases passed
with no failures or skips in 398.79s. All 7 generated regression ZIPs were
inspected successfully. Together with the two focused cases, this is 12 passing tests;
full Ruff, Mypy240, format, scoped Bandit and 33 local document-link checks passed.

## Local saved-proposal display race correction

Review of the unpublished native panel reproduced delayed saved-proposal replies
restoring cleared conversation text and an older reply replacing the newest choice.
`fix/native-history-stale-open-20260914` checks the current context and latest explicit
proposal choice before displaying either content or errors. Three baseline checks
failed; all 29 shipped-script Node VM checks pass after correction, including four
race cases. The script cache version is advanced. No backend, schema, provider or
confirmation boundary changed. Private reproduction and verification evidence is in
`native-history-stale-open-validation-20260914` under .tmp. Browser initialization
still fails before interaction; rendered acceptance and full-range manual publication
review remain incomplete. This correction and its newer ancestors remain unpublished.

The 42 nearby chat, navigation, template and JavaScript-wrapper tests also passed
with no failures or skips using this checkout's PYTHONPATH and fresh basetemp.
JavaScript syntax, diff and 35 documentation-link checks passed. No live database,
provider, activation or public Git action was performed.

## Local Word/PDF package-history acceptance

The isolated `test/native-stack-publication-review-20260914` branch adds direct Word
and PDF coverage to the existing native-history HTTP tests. Both cases passed on
owned PostgreSQL15433 with selected-checkout PYTHONPATH and fresh basetemp: two
passes, no failures or skips, one warning, 195.41 seconds. Each separately confirms
Scope, package creation and import; the older pending package stays byte-identical.
Selected original report and history JSON remain exact in the ZIP and imported
history download. Imports create no local native proposal/decision authority.

The two ZIPs, JSON downloads and imported HTML structure were inspected. The first
standalone inspection script used the wrong schema-name literal; the preserved
failure was corrected against the existing v7 constant without application changes.
Private receipts and synthetic outputs are in
`native-stack-publication-review-validation-20260914` under .tmp. These tests use
injected replies/scanner results; browser rendering and real-report accuracy remain
unverified. This is test/documentation work only, with no migration or live change.
The larger local range's automated confidentiality screen found no configured
markers; manual full-range review remains incomplete and publication is unapproved.

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

## Local native decision claim consistency

An isolated correction based on `9b65cfb` now cross-checks the recorded changed flag against
original/submitted graph hashes and requires a valid lowercase SHA-256 string. Two new
HTTP cases reproduced HTTP 200 responses for inconsistent rehashed claims on the unchanged
reader. The corrected full decision HTTP suite passed 20 cases, one warning and no skips
in 917.11 seconds on disposable PostgreSQL15433 with selected PYTHONPATH and fresh basetemp.
Full Ruff, Mypy over 239 source files and changed-service Bandit passed. Fresh-process
reads reopened the earlier confirmed/rejected decisions, Scope 3 and the exact original-
bearing Scope 2 ZIP unchanged; all 71 tables and 32 rows matched before/after. The first private
snapshot harness stopped on incomplete imported ORM metadata; reflecting the actual
schema corrected that harness only. Its failure is retained in the private receipt.
No schema, authority, provider or live change is included. The subsequent local package
history increment is recorded above.

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

The isolated `feat/native-xlsx-scope-proposals-20260914` branch extends local
`8441195`. Users select one worksheet, one header, up to 10 data rows after that
header and up to two retained PNG pictures (4 MiB combined). Exact selected cells,
header and pictures are disclosed before separate provider consent; original files,
other sheets and omitted rows/pictures are excluded. The shared transport validates
all 12 nullable mapping fields and typed additions. Text claims must quote a selected,
mapped, non-formula/non-error data cell; a picture claim still needs a selected row.

**Review proposed Excel Scope** opens the existing signed workbook review. Mapping,
relationships, images and unknowns remain human review decisions. Only a separate
confirmation saves a revision; the package has its own confirmation. Existing records
are preserved, blank openings can have zero Services, and unresolved values stay
unknown. Formula values, row count and image placement do not establish quantities.
This reuses existing services; no new writer, parser, dependency, schema, migration,
provider configuration or implicit downstream capability is included.

Confirmed references retain existing `human_xlsx_row_entity_review` provenance,
mapped source cells and image identities. Raw AI claims/rationale and unsaved proposal
controls remain transient, not a durable AI suggestion batch or complete history.

The synthetic browser journey passed selected header/row/picture preview, consent
refusal, a proposal without writes, separate Scope/package confirmations and exact
original-bearing ZIP download. The ZIP has exactly the original XLSX, saved Scope
and manifest, with matching member hashes and sizes. After test-server restart a
fresh browser downloaded identical ZIP bytes with no repeated scan, model or save.
The injected clean scan and scripted reply do not establish malware or real-model
accuracy. Final regression/static and visual evidence is recorded in the private
validation receipt; these local checks do not grant publication or activation.

Validation: 157 affected Excel/Word/PDF/chat/edit/review tests passed
without failures or skips in 1003.864s. After the evidenced route fix,
84 affected context/Excel/concurrency tests passed in 281.045s,
including both tests that failed before correction (188 distinct cases across the
two passing runs). Tests used this checkout's PYTHONPATH, fresh basetemp and
only disposable PostgreSQL15433 or isolated SQLite. Full Ruff, Mypy236, scoped
Bandit, JavaScript syntax, diff and67 local document-path checks passed. Desktop,
390px, Scope and package outputs were inspected; a read-only recapture verified the
lazy-loaded picture. Header/format selection changes invalidate old selection and
consent. The final browser preserved exact ZIP bytes and zero additional saves,
scans or model calls. The test server was stopped; live8820 remains PID24324.

An additional read-only browser check exposed a source-lock wait blocking the
async request loop. The same defect was reproduced for both context endpoints with
bounded HTTP responsiveness tests. Context resolution now runs in the existing
thread pool, like model responses; source locks, rights and transaction cleanup are
preserved. This prevents a blocked reader from stopping unrelated requests and
cleanup. It does not add workers, queues or automatic retries. Final diff review
also restored UTF-8 chat labels corrupted during editing. The review screenshot
needed a later capture after the lazy-loaded picture became visible.

This increment and its local parents remain unpublished. PR271 still has approved
head d864c51 and failed CI34757320145; local one-file correction8bce0b0 awaits
separate public approval. Diagnostic post-merge CI34753856708 is cancelled. The live
8820 build, live15432, credentials, OAuth/tunnel and activation settings are unchanged.

## Earlier native Excel attachment checkpoint

The isolated `feat/native-xlsx-attachments-20260914` branch extends local `0c6767a`.
The shared native attachment adapter/driver now also exposes supported XLSX defect
registers. Upload retains the original; scanning remains an explicit action. The
panel shows five rows at a time, worksheet choice, cell coordinates/types/values and
verified picture previews with their structural anchors. Formula text stays text;
cached formula results do not become quantities. Original download and the existing
selected-sheet mapping/review remain available under current access and scan checks.

This increment does not send workbook evidence to a model or create mappings, Scope,
pricing, packages or technical decisions from inspection. Scope workbooks retain
their existing purpose and cannot be adopted as pricing sources. Word/PDF model
selection remains separate. No new parser, writer, schema, migration, dependency or
provider configuration is included. The closed-review test explicitly accounts for
the third independent attachment form while preserving no stale Scope save.

Validation: 99 affected Excel/Word/PDF/review/package tests passed, no failures or
skips, in 609.397s. Tests used this checkout's PYTHONPATH, fresh basetemp and
only disposable PostgreSQL15433. Full Ruff, Mypy236, scoped Bandit, JavaScript syntax,
diff checks and67 local documentation links passed. Browser upload, explicit scan,
row/worksheet navigation, verified PNGs, exact original and mapping-review links passed
with chat disabled and no Scope/package/model work. A fresh browser after test-server
restart reopened the same evidence/original without upload or scan. Word text/picture
selection and original download still work; loading Excel preserves the Word preview.
The first screenshots showed adjacent row/cell labels; separate row headings corrected
them, and fresh desktop/390px screenshots were inspected without horizontal overflow.
The synthetic scanner is not real malware acceptance. No model accuracy is established.
This increment and its local parents are unpublished; PR271 still needs successful
CI and the pending approval for its additional test-only correction. The live app,
live15432, credentials and activation configuration remain unchanged.

## Earlier native PDF proposal checkpoint

The isolated `feat/native-pdf-scope-proposals-20260914` branch extends local
`2fea699`. The panel now selects one retained PDF page's text and/or rendered PNG
for exact context preview and explicit provider consent. Other pages, the original
PDF and external links stay excluded. Selecting Word or PDF clears the other format
and invalidates old preview/consent; the request contract rejects mixed formats.
The existing transport and additions composer validate source-bound Defect, Opening
and Service proposals, preserve existing records and reject unsupported claims.
**Review proposed PDF Scope** opens the existing signed PDF page review. Only its
separate confirmation saves a revision; package confirmation remains separate.

This path records existing human page/entity references when the user confirms.
It does not persist raw model claims, rationale or a durable AI suggestion batch.
Unsaved proposal controls are transient. No new writer, parser, dependency, table,
migration, provider configuration or downstream execution is included.

The synthetic browser journey passed selected text/image preview, consent refusal,
proposal without writes, separate Scope/package confirmations, preserved unknowns
and a blank opening with zero Services. The ZIP contains exactly the original PDF
and saved Scope revision plus its manifest. After test-server restart a fresh browser
returned the identical ZIP with no repeat scan, model call, Scope or package write.
Desktop and390px proposal, Scope and package review outputs were inspected. Tests
use scripted replies and an injected clean scan, not real accuracy or malware evidence.
Validation:98 affected PDF/Word/chat/edit/package tests passed without failures or
skips in439.395s, including all21 new cases. Tests used this checkout's PYTHONPATH,
fresh basetemp and disposable15433. Full Ruff, Mypy236, scoped Bandit, JavaScript
syntax and diff checks passed. The first screenshot preceded source-image loading;
a read-only recapture verified the rendered page without another save.

The increment and its local parents remain unpublished. PR271 still has approved
head d864c51 and failed CI34757320145; no reviews or merge were observed. Local
one-file correction8bce0b0 awaits separate publication approval. Diagnostic post-merge
CI34753856708 remains cancelled. The live8820 runtime and live15432 remain untouched.

## Earlier native PDF attachment checkpoint

The isolated `feat/native-pdf-attachments-20260914` branch starts at localb330266.
The existing session adapter and attachment driver now support both Word and PDF
through their existing retained-source policies. Word URLs remain compatible. PDF
upload/duplicate reuse, explicit scan, paged retained text/PNG inspection, exact
original download and links to the selected page's existing review are exposed in
the panel. PDF pages are not yet sent through native chat context; the UI states
this limitation. Existing PDF suggestion consent and human review remain separate.
No provider/model configuration, parser, migration, schema or dependency changed.

The six initial native PDF/Word checks passed on disposable15433 in70.192s. They
cover duplicate reuse, unchanged protected tables, cross-format/foreign access,
CSRF, read-only restrictions, failed/expired scans and corrupted document identity.
The first browser journey reached both pages and exact original bytes, then found
narrow-panel overflow: the PDF content lacked the existing evidence-block class.
The correction reuses that class for text wrapping and image constraints.
Final validation:100 affected PDF/Word/chat/selected-edit tests passed without failures
or skips in432.920s. Full Ruff, Mypy236, scoped Bandit and JS syntax passed. A fresh
synthetic browser journey proved upload/duplicate reuse, explicit scan, both retained
pages/PNGs, exact original PDF bytes and the selected-page review link. Desktop and
390px screenshots were inspected; the panel fits without horizontal overflow. After
restarting the test server, a fresh browser reopened the pages and identical original
without upload, scan, provider calls, Scope revisions or package creation. An earlier
harness expected text before opening the existing collapsed text section; HTTP200 and
page2 were correct, and the corrected harness passed without a product change.
A further browser check proved Word upload/scan, text/picture selection and exact
original download still work; loading PDF sources preserves the Word preview hash.

The closed-review test now explicitly expects logout, separate DOCX/PDF uploads and
advice while preserving rejection/repeat/stale-Scope checks. This locally extends
the earlier8bce0b0 correction for the additional PDF form; it neither publishes that
commit nor changes PR271. The exact12-file d864c51 approval does not cover this
branch or its unpublished parents. No public push, activation, provider call or
live15432 operation occurred. The newer PDF model/proposal checkpoint above supersedes
that implementation gap; broader formats and operational acceptance remain.

## Selected Scope record edit checkpoint

The isolated `feat/native-selected-scope-edits-20260913` branch extends local
Word proposal commit `9d64bd1`. The panel now offers `propose_scope_edits` over
explicit saved Scope IDs. Register selection supplies the selected row identities
without copying text; related context alone does not authorize an edit. Complete
replacements are bounded to25 selected Defects/Openings/Services/observations.
The server rejects additions, deletions, duplicate IDs, unselected/global edits,
Confirmed states, undisclosed relationships and whole-graph conflicts.

The panel shows named before/after fields and reasons. **Review changes in Draft
editor** only validates through the existing manual editor; **Save new revision**
is a separate user action with current permissions, CSRF and revision checks.
Existing source claims remain retained and changed claims are marked for review.
This path does not use the Word review's signed token or create a durable AI request;
the existing manual writer remains the authority boundary. Unselected records and
global assumptions/exclusions are preserved. Technical, pricing, package and release
work never runs implicitly. No schema, migration, dependency or live change is included.

Validation completed147 distinct checks:145 affected regressions passed without
failures/skips in390.141s, plus two added multiple-record/edit-budget cases passed.
The new budget fixture initially omitted its required uncertainty field; that fixture
was corrected without changing application guards. Tests used this checkout's
PYTHONPATH and fresh basetemp on disposable15433. Full Ruff, Mypy over236 source
files, scoped Bandit and JS syntax passed. Synthetic Chrome proved selected-row
preview/consent, visible differences, no write on proposal/validation, separate save
and exact reopening after test-server restart. Local edits clear old proposals and
consent; cancelling the existing unsaved-navigation prompt retains the working edits.
Desktop,390px-panel and unsaved-editor screenshots were inspected. Earlier harness
assumptions about retained controls/empty follow-up input were corrected and recorded.
Scripted replies only: no real model accuracy or operational acceptance is established.

This increment and its8bd0d7f/9d64bd1 parents remain unpublished. PR271's remote head
is still approved d864c51; CI34757320145 failed. The one-file correction8bce0b0 is
local and requires the pending extra-file publication approval. The conflicted root
and pinned live/rollback checkouts are preserved. Full C2/C3 and production gates remain.

## Native Word proposal checkpoint

The isolated `feat/native-word-scope-proposals-20260913` branch starts at local
selected-evidence commit `8bd0d7f`. The panel now explicitly requests typed Word
additions, preserves all existing rows, checks selected quotes/pictures and prohibits
Confirmed states. Current write permission, exact revision, preview hash, consent,
source integrity and scan status are rechecked. No provider reply writes Scope.
The existing session-bound Word review saves one separately confirmed Draft revision;
the existing package page separately saves the chosen original-bearing ZIP.

Validation:126 affected Word/chat/context/diagnostic/review/package tests passed in
609.355s on disposable15433 with selected-checkout PYTHONPATH and fresh basetemp;
one added pure contract test passed in7.085s. Full Ruff, Mypy over235 source files,
scoped Bandit and JavaScript syntax passed. The final uninterrupted synthetic Chrome
journey proved upload/explicit scan, selected text/picture consent, typed proposal,
separate Scope and package confirmations, reopening after the test server restarted,
and exact Scope/original ZIP bytes. Desktop and390px-wide proposal screenshots were inspected; no horizontal
panel overflow. Scripted model and injected scan only; zero real provider calls.
Earlier harness field-order/form-selector failures were diagnosed and preserved.

The Word contract links Defects/Openings/Services; this action does not add observations,
assumptions or exclusions. Existing observations are preserved. Proposal controls and
model rationale are transient; the confirmed revision retains the existing human Word
source claims, not a durable model-response transcript. No accuracy, complete C2,
real malware, operational activation or production-readiness claim follows.

Publication is separate: this branch and its selected-evidence parent remain local.
PR271 still contains d864c51 with failed CI; test-only8bce0b0 needs the pending
additional-file approval. Do not mix these branches or bypass that gate. Live8820,
OAuth/tunnel configuration, live15432 and the conflicted root remain untouched.

## Selected Word evidence implementation checkpoint

The native panel now lets users choose up to 10 retained Word text blocks and two
pictures from one source for an exact preview. Current access, scan and integrity
checks resolve selected items on the server. The same advisory transport sends the
text and verified PNG bytes only after consent; original DOCX bytes and unselected
content are excluded. Omitted counts and structural-locator limits are visible.
Selection changes clear preview, conversation and consent. A browser-proven shared
mutable selection bug was fixed by copying the event payload.

Validation: 94 affected Word/chat/context/diagnostic tests passed on disposable15433
with selected-checkout PYTHONPATH and fresh basetemp. Full Ruff, Mypy over234 source
files, scoped Bandit and JS syntax passed. Full Mypy required the existing complete
development environment; global Python lacked optional MCP/JWT dependencies. The
isolated Chrome journey proved selection, required consent, scripted advice, exact
PNG/original bytes, unchanged Scope, restart/reopening and consent invalidation.
Final desktop/narrow screenshots were inspected. Browser replies and scan verdicts
were synthetic; zero real provider calls and no live activation occurred. Native
typed Scope proposals and separate Scope/package confirmations are covered by the
newer synthetic checkpoint above; operational C2 remains open.

Publication: approved d864c51 is pushed in PR271. Run34757320145 failed after639
passes on a closed-review test expecting only logout/chat forms. The independent
DOCX form is intended. Local test-only8bce0b0 checks all three form roles and preserves
stale/repeat-save protection;30 affected checks passed after reproducing the failure.
It adds one file beyond the exact12-file approval, so publication approval is pending.
The separate CI logging commitbf700bc also remains local. No failed job was restarted.
Reverify GitHub before publishing; these are observed results, not merge receipts.

## Native Word attachment implementation checkpoint

The first C2 interaction is implemented in an isolated checkout based on merge
`97c07786355bbe938696aee56131e3f7aefe9dc6`. The existing panel can retain a selected
DOCX in an existing Draft, show source status, explicitly scan, inspect paged text
and retained pictures, and reopen the source. Same-byte upload reuses its binding;
Scope and AI messages do not change implicitly. This adds a thin session adapter,
panel controls and regression coverage, without schema, dependency or plugin changes.

Validation passed 108 affected Word/client/chat/migration tests with the selected
checkout PYTHONPATH and a fresh basetemp on disposable PostgreSQL15433. Full Ruff,
Mypy (234 source files), scoped Bandit and JavaScript syntax checks passed. A separate
synthetic Chrome journey and server restart verified the visible controls, exact
original bytes, unchanged Scope and zero provider calls. Desktop and narrow-screen
screenshots were inspected. The scanner was injected; this is not real malware,
provider, customer-accuracy or full C2 acceptance. Verify publication from actual
Git/PR/CI evidence; these local checks are not publication or activation receipts.

C1 diagnostic commit `5454b36` merged through PR #270 as `97c0778`, with full-tree
equality and 2,450 passing PR tests. Its existing post-merge run
[34753856708](https://github.com/Slayde91/classifire/actions/runs/34753856708)
**cancelled at the 45-minute limit**. The log shows continuing progress through 52%
without a final test summary; no full pass or single-test root cause is established.
The run was not restarted. New operational test/activation approvals remain absent,
and activation is blocked. A private unapproved wrapper revision corrected an
offline-proven TLS environment mismatch; this does not explain the historical502.

Live8820 remains on rollback `6c1e2a4` with chat disabled. Preserve the conflicted
root, pinned candidate/rollback checkouts and all historical receipts. Complete
C2 operational acceptance and broader coverage remain while resolving the CI gate separately.

## Current position

The modular Draft prototype supports scope creation/review, selected technical
candidate review, independent estimates and four paired PDF/XLSX report profiles.
It has a shared authenticated client adapter and portable selected-project ZIPs.
The accepted hybrid direction (ADRs 0001/0002) remains unchanged. The full production
platform, broad document interpretation and canonical Phase 8-14 exits are incomplete.

### Publication and CI checkpoint

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

### Approved workspace activation

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

### Current embedded-chat publication and operational checkpoint

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
original-file transfer remains excluded; selected retained Word text/PNG transfer is
now implemented under the preview/consent boundary described above.

Accuracy preparation is separate. The existing comparator fix is already merged in
PR #261. Twenty-four unchanged synthetic comparison/blocked-run checks passed in
this checkout with explicit PYTHONPATH and a fresh basetemp. The private reference,
original and photo hashes and authority limits are retained in a private run plan.
No customer-report analysis, photo inference, real provider or database evaluation
ran during this preparation; no accuracy score exists. [Reference readiness](./PHYSICAL_REFERENCE_READINESS.md)
records the incompatible unresolved-topology contract and remaining Phase 8/8C gates.

### Merged imported-original navigation increment

- Separate checkout `.tmp/imported-evidence-navigation-20260913`, branch
  `feat/imported-evidence-navigation-20260913`, based on pinned `1de68b9`.
  The selected local task connects exact imported row references to their existing
  retained-original review cards; scanning and downloading remain explicit actions.
  The imported claim remains unverified, without inline text/image previews.
- Validation passed 94 distinct affected cases: 30 native/core (seven new), eight
  new HTTP cases and 56 existing register/package UI cases. Full Ruff, Mypy (233 files),
  Bandit and unchanged single 0047 migration head passed. Independent final source
  review found no actionable issue. No application correction was needed during tests.
- Actual synthetic Edge acceptance on 8847 opened the exact original card and left all
  67 checked domain tables unchanged. Download was refused before the imported binding's
  explicit source check. After an explicit scan, DOCX and original ZIP downloads matched
  retained bytes exactly; only the imported-source table changed among those 67 tables.
  The imported claim stayed unverified, with no inline source body or images. Desktop,
  mobile, original identity and the three-member ZIP were inspected.
- Restart preserved the exact review URL/anchor, DOCX, ZIP, Scope revisions 2/3 and all
  67 checked domain tables, with no rescan, package write or page error. Synthetic
  acceptance is not customer accuracy, human production acceptance or deployment.
- Retained logs disclose test-harness corrections: fixture paths/revision assumptions,
  an audited download inside a no-write check, ZIP member ordering, an overbroad form
  assertion that caught Logout, and Edge internal assets misclassified as network
  traffic. HTTP coverage passed across the original and corrected-case runs; its first
  source manifest saw only Ruff formatting drift, with route/templates stable.
- Nine reviewed files: four application files, two synthetic tests, three documentation
  files. No schema, migration, package version, parser, provider or authority change.
  All four candidate checkouts remain pinned. Publication and CI are recorded above;
  no operational activation is implied.

### Merged Defect-only source inspection

- New isolated checkout `.tmp/defect-source-evidence-20260913`, branch
  `feat/defect-source-evidence-20260913`, based on clean pinned `51e3666`.
  The existing [Evidence service](./REGISTER_SOURCE_EVIDENCE.md) now accepts an exact
  Defect-only selection, including review-queue Defects with no linked Opening.
  It returns only that Defect's references and preserves unresolved relationships;
  it creates no Opening/Service and runs no downstream capability.
- Local validation passed 89 affected cases: 23 native/core, 52 HTTP and 14 existing
  workbench/history cases. Full Ruff, Mypy (233 files), Bandit, JavaScript syntax and
  unchanged single 0047 migration head passed. Core service/test hashes match their
  validation receipt. The 52-case HTTP pass was observed in the test session; no
  JUnit XML or test-time source-hash manifest was retained for that run.
- Actual synthetic Edge acceptance on port 8846 checked each Defect's own sources,
  historical/stale claims, keyboard focus, unsaved-edit exclusion and desktop/mobile
  output. A deliberately mismatched Defect fragment was refused. Restart preserved
  five image URLs and four Scope downloads byte-for-byte; all 67 checked domain
  tables remained unchanged. No Opening or Service was invented, no provider ran,
  and no live 15432 database was contacted. This does not establish real-report accuracy.
- Final source review found no actionable issue. The change contains six application
  files, two synthetic tests and three documentation files. No model, migration,
  parser, provider or existing authority change. Commit `1de68b9` is included in
  merged PR #265. The historical `51e3666` activation plan excludes this increment
  and grants no authority for a newer candidate.

### Merged register evidence increment

- Checkout `.tmp/register-source-evidence-20260913`, branch
  `feat/register-source-evidence-20260913`, based on local Complete-report commit
  `6d4793b`. [Evidence contract](./REGISTER_SOURCE_EVIDENCE.md) defines exact saved-row
  PDF/Word/Excel inspection through existing intake readers and current access checks.
  No migration/model, provider, downstream execution or canonical writer is added.
- 54 unique core/HTTP cases passed (14 new core, 36 new HTTP and 4 existing register).
  Full Ruff, Mypy (233 files), Bandit and unchanged single 0047 migration head passed.
  Another 68 affected authoring/history/chat regressions passed: 122 unique affected
  cases in total. Actual Edge showed nine verified references across PDF/Word/Excel,
  including intact originals behind stale claims, blank and unlinked rows. Unsaved
  edits were excluded, Scope 1/4/6 downloads matched exact retained bytes and all 67
  checked domain tables stayed unchanged. Desktop/mobile output was inspected; no
  page errors or mobile document overflow. Restart preserved all 12 checked image URLs,
  Scope 1/4/6 bytes and all 67 domain tables; source-cell F2 passed.
- Parent PR #264 post-merge run 34715038796 passed 2,251 tests and remaining checks.
  Complete-report commit `6d4793b` and this increment are included in merged PR #265.
  Explicit owner approval resolved the earlier public-destination block; repository
  visibility and protection settings were not changed.
- Evidence-tab changes are published. Pinned source checkouts, the conflicted root
  remain preserved. The later separately approved workspace activation is recorded
  above; this earlier increment did not itself authorize deployment.

### Merged workspace and current runtime

- PR #260 merged the integrated workspace as `3eabb23ecddce98dc3e8583236f9cb055b218280`.
  Its source `6bc9e96` passed exact-head run 34704939887: 2,113 tests, Ruff, Mypy,
  Bandit and single migration head. No required reviews were configured. The merged
  tree matches the tested source. Post-merge run 34706301132 also passed all 2,113
  tests and remaining checks; no workspace deployment is implied.
- One Projects & estimates directory now includes accessible Draft Scopes, saved Draft
  Estimates and existing estimates. Six existing libraries share one Libraries section.
  Existing URLs, IDs, saved records and permission boundaries are retained.
- The register supports range/bulk editing and explicit saved system/price projections.
  Historical relationships remain available for review. A blank opening may have zero
  services; no placeholder Service is created. Existing graph/schema history is unchanged.
- 157 unique affected tests passed after one evidenced template-context correction.
  Isolated Edge UAT saved Scope revision 3 with five source references and null quantities,
  retained exact revision 2, and downloaded an exact original-bearing project ZIP.
- The embedded advisory panel previews selected saved Scope context. Its provider is
  disabled in the verified UAT. General accurate multimodal analysis, broader automatic
  system/pricing work and full redesign acceptance remain incomplete. Selected-row manual
  authoring is implemented in the current isolated increment described below.
- Historically, diagnostic source `e2e8292` was activated after its own backup/restore
  checks and 2,066-test PR/post-merge CI. The later approved `6c1e2a4` workspace
  activation above supersedes that runtime; the older source remains the governed
  rollback target, subject to saved-data compatibility and no lost work.
- The actual connected upload remains refused by `CLIENT_FILE_UNAPPROVED_HOST`.
  The bounded diagnostic now identifies the rejected host privately. No file was retained;
  all 69 table inventories and retained files/schema were unchanged by that probe.
  The allowlist and OAuth/tunnel configuration were not changed.

### Merged row authoring and multi-review packages

- PR #261 merged as `095ee3d`. Its exact-head run 34707202158 and post-merge
  run 34708282314 each passed 2,127 tests and remaining checks.
- PR #262 merged source `6c30361` as `48b4b111f6c8f539a9aa7d8211be5fcb2e61db52`.
  Exact-head run 34709110199 passed 2,134 tests and remaining checks. The merged tree
  equals the tested source. No required reviews were configured; no human GitHub review
  is claimed. Post-merge run 34710331473 also passed 2,134 tests and remaining checks.
- [Native row authoring](./REGISTER_ROW_AUTHORING.md) retains its 104 affected local tests
  and actual service/blank review, manual-rate override, 409 conflict and restart evidence.
  A fresh candidate rehearsal restored the existing synthetic PostgreSQL clone on 15433:
  all 69 tables/schema/rows matched, metadata startup was a no-op, and retained packages
  plus the accepted Word Scope/ZIP/original verified. This is not a fresh live 15432 backup.
- PR #263 merged tested source `469a57f` as `d5c19d74746d4ac1cd2f6e19f63278bf560e53d7`.
  Exact-head CI 34711480773 passed 2,199 tests and all remaining checks. The merged tree
  equals the tested source; no required reviews were configured. Post-merge CI
  34712796245 also passed 2,199 tests and all remaining checks.
- Preserved package checkout: `.tmp/multi-review-package-20260913`, branch
  `feat/multi-review-package-20260913`, based on `48b4b11`. It extends existing register and
  package services to retain multiple exact row reviews, explicit v6 package save/reopen,
  collection-aware imported mapping-v3 and the existing technical client-grant boundary.
  No new table, migration, model, dependency, provider or canonical writer is introduced.
- [Multi-review contract](./MULTI_REVIEW_PROJECT_PACKAGES.md) records compatibility and
  limits. The isolated 8842 Edge journey retained three row reviews, updated one without
  losing the others, separately saved/downloaded v6, and reopened the exact set. A later
  review revision did not replace the package's older selection. 109 unique affected
  tests passed, including retained DOCX and PostgreSQL import/scan/report checks on 15433.
  Final Edge restart kept the saved 2/1/1 review set despite a newer first review, exact
  Scope/ZIP/history and all non-login tables. Actual ZIP import created three mapped local
  reviews; separate re-export retained the byte-exact original archive. Desktop/mobile
  screenshots and ZIP contents were inspected; no page errors were observed. These are
  synthetic automated confirmations, not human technical or production approval.
  Full Ruff, Mypy (233 files), Bandit, JavaScript syntax and migration-head checks passed.
  Publication is verified above; operational activation remains separate.
- At this package increment, the 8820 diagnostic app and older demos were unchanged.
  The historical `6c30361` plan excluded these formats. The separately approved
  `6c1e2a4` activation above later included them after exact recovery verification.

### Merged multiple-review Scope reporting

- Checkout `.tmp/multi-review-reports-20260913`, branch
  `feat/multi-review-reports-20260913`, based on merged `d5c19d7`. The
  [report contract](./MULTI_REVIEW_REPORTS.md) extends the existing scope-and-system
  profile with exact selected reviews, report snapshot v3 and import mapping v4.
  No migration, model, dependency, pricing calculation or provider is introduced.
- Shared core, UI, typed client, package dependencies and renderer checks passed in
  their focused runs. Final combined verification passed all 52 new cases, including
  actual disposable PostgreSQL import/scan checks; final package-screen regression
  passed 18 cases. Full Ruff, Mypy (233 files), Bandit, JavaScript syntax and the
  unchanged single 0047 migration-head check passed. PR #264 merged tested source
  `ccaff7a` as `e96c6928ffdbc11a9bd2fb890105e83f05c87625` after exact-head run
  34713651083 passed 2,251 tests and all checks. The full merged tree equals the
  tested source. No required reviews were configured; no human review is claimed.
  Post-merge job 34715038796 passed 2,251 tests and all remaining checks.
- Actual 8843 Edge UAT separately saved the three-review report and ZIP. PDF/XLSX
  and ZIP bytes match retention. Restart preserved all exact downloads, Scope and
  66 checked domain tables. All 19 PDF pages and desktop/mobile views were inspected;
  XLSX values/structure were inspected programmatically, not in native Excel.
- Evidenced fixes: distinct headings for repeated client review/measurement panels,
  and Word v7 evidence labels/provenance in report views. Earlier synthetic fixture
  copying failed the absolute StoredFile-path guard; it was preserved and replaced
  with a fresh isolated fixture, without changing the guard or stored bindings.
- The 469a57f activation plan excludes this newer report format and is unapproved.
  That increment did not activate 8820; the later approved activation is above.
  The reviewed ten-defect reference remains
  Draft evidence, not measured independent extraction accuracy or system approval.

### Merged Complete report increment

- Checkout `.tmp/complete-multi-review-reports-20260913`, branch
  `feat/complete-multi-review-reports-20260913`, based on merged `e96c692`.
  The existing Complete profile now accepts up to 30 explicitly selected exact row
  reviews. It retains the full unchanged Estimate and requires its embedded review
  in any nonempty collection. Extra reviews are labelled report-only context.
- [Complete contract](./DRAFT_COMPLETE_REPORT_CONTRACT.md) records snapshot v3,
  renderer 12 and reuse of import mapping v4. No pricing arithmetic, database model,
  migration, provider or canonical-write change is introduced. Empty selection
  preserves legacy formats and client command/input hash shapes.
- Focused runs passed 53 core/package/legacy cases, 24 UI cases, 18 output cases,
  13 client collection cases and 10 existing client cases. Full Ruff, Mypy (233
  files), Bandit and single 0047 migration-head checks passed. Final combined
  validation passed all 62 new cases in 185.29 seconds, including actual disposable
  PostgreSQL import/scan checks on port 15433.
- Actual Edge UAT on isolated SQLite port 8844 saved three reviews with Scope 2
  and Estimate 4: original rate 1.005, explicit override 1.505, subtotal 3.01 and
  another line with unknown quantity/subtotal. Report and ZIP saves were separate.
  PDF/XLSX/ZIP bytes matched retention. All 21 PDF pages were inspected in overviews,
  pages 1/3 at readable size, and desktop/mobile views showed no observed clipping.
  XLSX cells/structure were checked programmatically; native Excel was not inspected.
- Process restart retained exact Scope/PDF/XLSX/ZIP and 66 domain-table hashes.
  A verification fixture initially compared pretty JSON against compact downloads;
  diagnosis proved identical values and exact Estimate bytes in the original ZIP.
  A second restart proved byte-exact raw downloads of Estimate revisions 2 and 4.
  Original failure/diagnosis are retained; no application guard or test was weakened.
- Commit `6d4793b` is included in merged PR #265. The historical ccaff7a plan
  excluded this newer Complete format. That increment did not activate 8820; the
  later approved `6c1e2a4` activation included it, without OAuth/tunnel or host changes.

### Earlier Word acceptance checkpoint

The following table retains the earlier Word milestone and its historical CI evidence;
the candidate/runtime paragraph above supersedes its then-current source and runtime.

| Evidence | Verified state at this checkpoint |
| --- | --- |
| Word checkpoint source | `origin/main` eb3ddb3f6ec23bd3ce66d7f7c82b7edaf830c4c2, merge of PR #257; tree matches tested ff0272b |
| Word inspection | PR #252 merged as c5d4774; retained DOCX parsing/pictures and migration 0047 |
| Word review/packages | PR #253 merged as 2fb422e after PR CI 34657065137 succeeded |
| Word client | PR #254 merged as c496baf; source commit 4e2a2b1. PR CI 34662617629 subsequently succeeded; main CI 34662645680 ended cancelled (not a pass). The merge preceded the PR success |
| Parent main failure | Run 34658986190: 1 failed / 1,894 passed. Test dates were collected before midnight and evaluated afterwards; this was a test timing error, not evidence of a weakened production guard |
| Correction | PR #255/18418f3 fixes only the test clock; all 23 targeted tests and hosted run 34662942874 passed. Merged as 7847288 at 2026-09-12 01:12:24 UTC; later run 34664119693 exceeded its 30-minute limit and ended cancelled, not passed |
| Runtime | Authorized synthetic trial activated tested ff0272b after successful post-merge CI; actual user-confirmed Scope and original-bearing ZIP survived an operating-system process restart |
| Migration | This operational receipt used0047; local native proposal history now adds0048. Disposable PostgreSQL history/restore checks passed. Actual trial had verified metadata-created lineage; approved startup added only the Word source table, with no fabricated Alembic stamp or downgrade |
| Documentation | PR #256 merged as 1f12e4b after successful exact-head CI; its earlier pending-activation statements are superseded by this checkpoint |
| PostgreSQL correction | PR #257 source ff0272b merged as eb3ddb3 after run 34681923704 passed. Post-merge run 34683024367 passed 2,043 tests and all checks; no job was restarted for an observation timeout |

PR #254 was merged prematurely by `gh pr merge --auto` while its checks were running.
At that checkpoint the GitHub protection endpoint reported main unprotected. This is an observed
process gap: use explicit exact-head successful-check/review verification before merge.
Do not infer that an accepted merge command proves CI passed, or change repository
protections without authorization.

## Implemented capability boundaries

| Capability | Source-backed implementation | Limits and incomplete work |
| --- | --- | --- |
| Scope | `services/draft_scope.py`: separate defects, openings, services and observations; nullable measurements/quantities; multiple service-opening links; revisions/import/export. PDF page, Excel cell/picture and Word structural text/picture review share guarded revision writing | Draft service/opening graph is narrower than the full production physical model: substrate planes, service instances, treatments and richer relationships are not all separate Draft entities |
| Evidence intake | `draft_pdf_intake.py`, `draft_scope_xlsx.py`, `draft_scope_docx.py`, shared `draft_source_intake.py`, bounded parser workers, malware/quarantine and retained-byte checks | Supported formats/layouts are bounded. DOCX structural positions are not pages; pictures expose original content, not Word layout/crop semantics. General OCR/drawings/inspection records and representative coverage remain incomplete |
| Workspace | Shared Projects/Libraries navigation, hierarchy review register, guarded bulk edits, historical selections and saved system/price display | No new domain model or migration. Multi-review packages are merged; automatic pricing/recalculation and comprehensive visual/accessibility/scale acceptance remain incomplete |
| Workspace advice | `draft_workspace_chat.py`, optional transport and UI preview bounded selected saved Scope records with their ancestors and source-reference claims | One live synthetic browser reply succeeded; follow-up failed and rollback restored chat-disabled operation. This is an advisory API panel, not an embedded authenticated external ChatGPT/MCP session. No automatic writes or implicit capability calls |
| Optional AI | `draft_pdf_suggestions.py` and suggestion contracts produce reviewable claims, with uncertainty and human decisions | No general autonomous evidence interpretation or proven replacement of every OpenClaw protection; manual workflow remains available |
| System matching | `draft_system_matches.py`: selected-target retrieval from an authorized retained technical release, immutable candidates, measured constraints/service sizes, human review and dependency staleness | Retrieval is not final suitability. Full configuration/substrate/insulation/installation constraints, bulk technical corpus and representative source coverage are incomplete |
| Estimating | `draft_estimates.py`, `draft_estimate_contract.py`: independent manual lines, explicit rate methods/overrides, decimal arithmetic, revision history and Scope/optional Match dependencies. Retained workbook rate selection exists | Full six-method automatic default derivation, validated extrapolation, yield/productivity/waste/pack/shared-recovery calculations and representative commercial acceptance are not complete |
| A/B pricing | Source profiles and review, A row observations, B system mappings, T9 coverage, T6 recipe links, T13 target-blind rosters and T10 bottom-up preview exist. `draft_pricing_quantities.py` already persists governed Scope-bound quantities (PR #233) | Do not rebuild the first quantity-basis feature. Preview is bounded to supported current confirmed sell-price evidence; unsupported inputs withhold amounts. Calibration, comparison/combination, holdout execution and production pricing activation remain later |
| Reporting | `draft_scope_reports.py` / `draft_estimate_reports.py` and versioned renderers retain paired PDF/XLSX bytes for scope-only, scope-and-system, estimate-only and complete profiles | Draft reports are not canonical release. Do not infer professional acceptance across every input from synthetic examples |
| Portable project | `draft_project_packages.py`, package inspection/materialization and imported-source services support selected revisions, imported origins and optional retained PDF/XLSX/DOCX originals | ProjectPackage v1-v6 represents selected revisions, not a full database backup or complete project/audit history; library source bodies and unselected artifacts are not automatically included |
| Client/UI | `draft_client.py`, typed capabilities, evidence tools and durable client requests reuse the same services. Word adds five tools and `review_word_scope`; exact schemas and bounded redacted field errors are exposed | Client proposals require separate same-user browser confirmation. Word application acceptance and actual connected text/image reads are verified. Dedicated connector Word upload remains host-policy blocked; successful connected scan and remote attachment retrieval remain unproven; Excel transport acceptance must be reconciled separately |

Domain services above are in `src/classifire/services/`; UI/client adapters are
in `src/classifire/`.
The authoritative architecture description is [CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md).

## Verification and health

The workspace regression receipt covers 157 unique cases across 12 files: Scope,
Word/Excel/PDF UI, templates, estimates, system matching, packages, navigation, register,
chat and register history. The first run passed 33 and failed one direct-template case;
a fail-closed empty register context corrected the defect without changing assertions.
The remaining runs passed 117 and 7 cases. Each used this checkout's `src`, disabled
pytest cache and a fresh basetemp. PostgreSQL fixtures targeted only disposable 15433.

The separate automated synthetic browser UAT used the isolated workspace app. It
exercised column selection, bulk edit, undo/redo, save/reopen, historical revision
selection, stale source warnings and selected saved chat context. The receipt reports
no JavaScript errors or mobile document overflow. An explicitly selected original DOCX
was retained in a 12,706-byte ZIP with byte-exact Scope revision 3 and original bytes.
A separate restart receipt verifies the Scope and ZIP stayed exact after restarting only
the isolated app on 8840, still using disposable database 15433.
This automated UAT is not a human production confirmation or a general accuracy study.
See [the acceptance matrix](./INTEGRATED_WORKSPACE_ACCEPTANCE.md) for precise limits.

The diagnostic activation's fresh restore receipt verified all 69 tables, five saved
Scope revisions, two packages and two stored originals. The approved restart preserved
schema/files and all Scope/package/original history; login-related changes were confined
to users/audit events. An expired one-time review link returned 403, while the saved
package route returned 200. That historical diagnostic check did not activate the
workspace; the later `6c1e2a4` acceptance is recorded above. Neither ran a migration.

The earlier controlled Word journey remains distinct:

The controlled Word journey used an actual authenticated browser upload, real ClamAV
scan, retained text/image inspection, connected typed proposal, separate human Scope
and package confirmations, browser downloads and an approved process restart. The
connected Word text/image tools became available and returned the same retained content.
Scope revision 2 retained five source references; its content matched the confirmed
proposal. Quantities and dimensions stayed null. The image was a 12x8 red placeholder,
so text assertions remained provisional rather than becoming invented visual facts.

The 12,847-byte ZIP contained exactly the manifest, saved Scope and byte-exact original
DOCX. Repeated downloads before/after restart matched. All pre-existing Scope revisions,
packages and originals remained exact; 60 other database tables were unchanged. No
matching, estimating, reporting, canonical admission, lock or release ran implicitly.
Runtime policy was unchanged; no OAuth/tunnel configuration change was made.

Preparation passed 159 affected tests, three PostgreSQL regressions, eight SQLite/history
checks, Ruff, Mypy and Bandit. Exact candidate and post-merge CI each passed 2,043 tests.
These are recorded execution results; documentation edits do not rerun or broaden them.
Dedicated connector upload/scan and remote attachment transport are not covered by the
successful browser upload/scan. The complete I2 client transport exit remains open. A later actual
connected upload attempt was refused with CLIENT_FILE_UNAPPROVED_HOST; no new source,
Scope revision or package was created. That earlier response did not expose the rejected
host. The approved PR #259 diagnostic
now identifies it privately; the refusal still stands and no allowlist change was made.
Obtain approval for an exact necessary configuration change before retrying.

Prior local Word feature evidence: 81 distinct selected client/retrieval/auth/PDF tests,
one Edge client-confirmation journey, Ruff, Mypy (229 source files) and Bandit passed.
Word review/package evidence additionally includes 105 integrated tests, 50 history/output
checks, 73 client/PDF checks and an Edge upload/review/package journey. These are bounded
synthetic checks, not current hosted validation or customer acceptance.

Health: functional Draft prototype, incomplete production assurance. PR #267 and its
post-merge CI passed all 2,399 tests and remaining checks. Earlier 30/45-minute
cancellations remain preserved and were not restarted. Main protection was absent at the recorded
inspection; CI must be explicitly observed. `worker.py` currently fails queued jobs with
“No registered handler”; it is not a production document-processing queue.

The earlier root inventory recorded recovery evidence at de0cc5a on
`gpt/phase8-linked-original-images`: 46 unstaged modifications, 14 staged additions,
four DU conflicts and CHERRY_PICK_HEAD c3e4c810. Untracked code, migrations, docs,
operator state and generated/private data coexist. No root changes are included here.
See [local change classification](./LOCAL_CHANGE_CLASSIFICATION.md).

## Recommended Next Actions

1. **C1 - Complete successful post-merge CI and revalidate advisory chat.** The
   diagnostic fix is merged, but its post-merge run cancelled. Diagnose the broader
   slowdown without counting cancellation as a pass. Prepare one exact synthetic follow-up test and
   conditional activation with fresh recovery proofs for explicit approval.
   All earlier provider-call allowances are consumed. Preserve the failed browser
   attempt and successful rollback; do not infer its cause or retry silently.
2. **C2 - Complete report analysis and Scope review.** Native DOCX attachment,
   status, explicit scan, evidence inspection and consented selected text/PNG advice are
   implemented, including typed additions and separate Word/package review in the
   synthetic journey. The same PDF page text/image and typed-addition journey now
   passes synthetic browser checks with separate PDF and package confirmations.
   Native XLSX now also has explicit header/row/picture context, proposed mappings,
   typed additions, separate workbook review and original-bearing package confirmation.
   Its synthetic journey passes. Explicit native proposal retention/reopening is now
   implemented locally, including explicit decision/revision links and selected portable
   history. Targeted regressions, actual-app HTTP/server restart and exact synthetic
   backup/restore passed. Complete rendered-browser and operational acceptance; full
   history coverage remains incomplete. Resolve
   the operational gate separately; do not repeat the proven Word increment. Reuse the existing
   intake/scan/review/client-request/package services. Preserve the demonstrated
   Word/PDF interaction when extending the attachment-to-confirmed-Scope-to-ZIP
   journey from the [assistant contract](./EMBEDDED_WORKSPACE_CHAT.md#approved-target-experience).
   Validate the actual browser, exact originals and distinct confirmations.
   Implementation with synthetic fixtures does not require live activation or
   customer evidence; selected Word pictures use verified PNG previews. Original-file
   and wider-format transfer remain excluded.
3. **C3 - Extend reviewed selected-record coverage.** The local Scope replacement
   action now provides selected-row context, a field diff and separate manual save.
   Complete operational acceptance and durable AI proposal lineage before claiming
   full C3; Match, Estimate and library/pricing edits still need their own typed
   contracts and validation. Other capabilities remain independently requested.
4. **Retained I2/N1 integration acceptance.** Dedicated external connector upload/
   scan and Excel transport evidence remain unproven; reuse the existing tools and
   clearly selected synthetic destinations without repeating completed Word
   confirmations or OAuth setup.
5. **Retained I3/N2 decisions.** Merge-protection changes require owner approval.
   Representative technical recipe/quantity/commercial meaning must be reviewed
   before wider derived-rate methods; no invented yield, productivity or recovery.
6. **L1/L2 broader work.** Preserve wider report/corpus coverage, full physical
   entities/history, T11-T14 validation, Phase8/8C accuracy and Phase8-16 production
   gates, tenant isolation, operational recovery and protected OpenClaw retirement.

The latest local increment changes selected package history, read-only import inspection,
synthetic tests and related documentation. It adds a forward package format, without a
database migration or provider-contract change. Private preparation/operational artifacts
remain outside Git. Preserve the conflicted root, pinned runtime checkouts and old
receipts. Verify current Git/PR/CI before claiming publication or activation.
See [SESSION_HANDOFF.md](./SESSION_HANDOFF.md) for branch context and the next task.
