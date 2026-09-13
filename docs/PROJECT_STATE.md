# CLASSIFIRE Project State

Reconciled 2026-09-13 after merged PR #269, failed chat acceptance and verified
rollback, and the bounded offline chat diagnostic fix.
[Workspace acceptance](./INTEGRATED_WORKSPACE_ACCEPTANCE.md) records implemented
behaviour and unmet redesign criteria. [The earlier Word record](./WORD_ACCEPTANCE_ACTIVATION.md)
retains its original acceptance evidence. Private operator receipts and customer
material remain outside Git. This is not a production-readiness certificate.

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
context/message, with no attachment input or write action. Existing PDF/Word/XLSX
intake, scan, review, typed client requests and package services are foundations.

The [architecture](./CLASSIFIRE_ARCHITECTURE.md#native-chat-as-a-working-interface),
[C1-C3 roadmap](./CLASSIFIRE_ROADMAP.md#embedded-chat-delivery-sequence) and
[assistant contract](./EMBEDDED_WORKSPACE_CHAT.md#approved-target-experience) now
describe the same target: attach and inspect a retained report, explicitly request
analysis, review a source-bound typed Draft proposal, confirm separately, refresh
the page and reopen/download exact saved artifacts. Later selected-record actions
reuse that review path. Uploaded content never becomes instructions or authority;
original/image provider transfer is still a planned bounded extension.

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
| Migration | Source head remains 0047. Disposable PostgreSQL history/restore checks passed. Actual trial had verified metadata-created lineage; approved startup added only the Word source table, with no fabricated Alembic stamp or downgrade |
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

1. **C1 - Diagnose and revalidate advisory chat.** Publish the bounded diagnostic
   fix after exact CI/reviews. Prepare one exact synthetic follow-up test and
   conditional activation with fresh recovery proofs for explicit approval.
   All earlier provider-call allowances are consumed. Preserve the failed browser
   attempt and successful rollback; do not infer its cause or retry silently.
2. **C2 - Build native chat report intake and Scope review.** Reuse the existing
   intake/scan/Word review/client-request/package services, beginning with one
   supported synthetic DOCX. Finish the visible attachment-to-confirmed-Scope-to-ZIP
   journey from the [assistant contract](./EMBEDDED_WORKSPACE_CHAT.md#approved-target-experience).
   Validate the actual browser, exact originals and distinct confirmations.
   Implementation with synthetic fixtures does not require live activation or
   customer evidence; current text-only transport needs an explicit bounded
   extension before any picture/original transfer to a provider.
3. **C3 - Add reviewed selected-record actions.** Keep selected-page advice available;
   a requested edit yields a typed proposal/diff, then an explicit same-user
   confirmation. Recheck exact revisions, current permissions and stale context.
   Other capabilities remain independently requested and gated.
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

This increment changes chat diagnostics, synthetic regression tests and affected
status documentation. There is no schema change; only a random diagnostic request
header is added to the provider contract. Private preparation/operational artifacts
remain outside Git. Preserve the conflicted root, pinned runtime checkouts and old
receipts. Verify current Git/PR/CI before claiming publication or activation.
See [SESSION_HANDOFF.md](./SESSION_HANDOFF.md) for branch context and the next task.
