# CLASSIFIRE Session Handoff

Reconciled 2026-09-13. Current code, Git, CI and runtime evidence override this
checkpoint. Read [PROJECT_STATE.md](./PROJECT_STATE.md),
[architecture](./CLASSIFIRE_ARCHITECTURE.md), [roadmap](./CLASSIFIRE_ROADMAP.md) and
root GOAL.md. The four independent capabilities and full production objective remain
unchanged and incomplete.

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

Workspace chat/PDF suggestions remain disabled. No provider, OAuth/tunnel, host
allowlist, role or grant change occurred. No saved Match, Estimate, report or imported
project existed in this demo, so those operational histories were not exercised.
This is retained synthetic-state acceptance, not customer accuracy, production
certification, storage relocation or full-cluster disaster recovery. Historical
activation plans stay preserved; recovery retains the approved compatibility and
no-lost-work conditions for the older `e2e8292` rollback source.

## Current authorised increment

Current work is isolated in `.tmp/embedded-workspace-chat-20260913`, branch
`feat/embedded-workspace-chat-20260913`, based on merged `6012d15`. The requested
interaction is a native collapsible, resizable, docked chat panel accessible from
the main workspace without an external-page dependency. It reuses the existing
chat API/transport and domain context services; the external connector is not rebuilt.

Acceptance must cover exact current project, screen, Scope/Estimate revisions,
selected Defect/Opening/Service or multiple records, selected technical systems,
library and pricing context. Register selection must supply context without copying.
Advice must support analysis, substrate, systems, prices, wording, missing information,
inconsistencies and summaries while preserving unknowns and current permissions.
An explicit context preview/hash and consent precede any provider transfer.
Conversation continuity is opt-in and limited to the same freshly verified context,
user and a 30-minute expiry; broader history sharing is not approved by convenience.

The native panel and typed context extension are implemented. Local backend validation
passed 55 cases, including all seven library kinds, exact three-review/Estimate history,
permission changes, stale context, request bounds and the retained Scope-only API.
Affected navigation/register/Word/package/0047 checks passed 52 cases initially; five
PostgreSQL-dependent cases then passed on disposable 15433, alongside the repeated
0047 migration case (six passes, no skips). Live 15432 was not used. Full Ruff,
Mypy (233 source files), Bandit and the unchanged single 0047 migration head passed.

Actual Edge acceptance used a new private SQLite database, loopback 8851 and two
scripted replies. It verified global panel presence, selected shared services and blank
openings, exact saved reviews/Estimate, opt-in sensitive details, full qualified reply
history, fresh preview before restoration, inline-result refresh invalidation, logout,
permissions, literal hostile HTML text and desktop/mobile layout. All 66 checked domain
tables and retained synthetic source files matched; only login timestamps changed.
No provider request or project write occurred. The private fixture needed seeding-order
and missing-router corrections; application guards were preserved. The passing run
emitted a Windows connection-reset callback during teardown and its 15-second thread
join expired; the process subsequently exited and 8851 had no listener. This is a
recorded harness limitation, not a clean server-shutdown claim.

Initial PR #268 CI run 34735571580 stopped with 639 passes and one failure: an old
PDF review-page test expected Logout to be the only form. The shared advisory form
is now explicitly accounted for, with exact field/required-consent assertions; all
existing no-resave, session, provenance and database checks are retained. This is a
test-contract update for the authorised UI change, not a weakened application guard.
The related imported-evidence parser now recognises the single actionless advisory
form while preserving POST-only requirements for saved actions and the no-scan/no-write
checks. Its first focused run exposed the matching method-attribute assumption; after
correction, all eight imported-evidence cases passed. The 27 PDF HTTP/template cases
also passed, bringing distinct affected local passes to 147. PostgreSQL cases used
only disposable 15433. The failed run is preserved and was not restarted because of
an observation timeout. Application source remains identical to the browser-tested
candidate; this follow-up changes only two test files and this documentation.

[Embedded assistant boundaries](./EMBEDDED_WORKSPACE_CHAT.md) describe the supported
context and conversation limits. Publication/CI and operational activation are separate
checks. This slice enables no provider, model, tools, domain writes or migration.
No provider credentials/model were verified configured; a concrete configuration and
activation decision is still required. It does not embed an external ChatGPT session
or reuse that service's private conversation history. Synthetic replies prove the
interaction and safeguards, not real model quality or the complete production phase.

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

Live 8820 was accepted on source `6c1e2a4` under its separately approved plan, as
recorded above. Earlier Word/Scope/package confirmations remain complete. The
connected upload host-policy refusal is a separate unresolved transport limit;
no OAuth/tunnel, grant, allowlist or provider change accompanies this increment.

The historical `9cdc4a4` and `7c9b570` bundles remain blocked by their failed/cancelled
post-merge runs. Do not reuse them as successful activation evidence or repeat the
completed fresh backup/restore and activation merely because an old handoff says pending.
Older readers cannot transparently read new Complete-v3 snapshots; retain all later
records and originals before any recovery decision. Existing absolute StoredFile
bindings must not be rewritten to bypass containment.

Other preserved synthetic demos: 8840 integrated workspace,8841 row authoring,
8842 packages,8843 Scope reports. Only 8844 was restarted for this Complete acceptance.
PostgreSQL tests use disposable 15433/classifire_containment_test, never live 15432.

## Classification and next action

PR #265 published 40 reviewed files; PR #266 contained the separate test/workflow
repair; PR #267 contained two documentation files. The current working branch adds
embedded-chat application/UI/tests through their assigned owners. This reconciliation
owns only PROJECT_STATE, SESSION_HANDOFF and PHYSICAL_REFERENCE_READINESS plus private
preparation records. Private customer originals, labels, file hashes and operator
receipts stay outside Git. Preserve the conflicted root and unrelated changes.

1. Finish the embedded-chat slice against its full acceptance list above. Record actual
   backend/UI/browser evidence before claiming completion; keep provider activation separate.
2. Reuse the merged comparator fix. The private accuracy-preparation folder under the
   existing operational private directory retains the controlled run plan, source/rights
   manifest and 24-case synthetic receipt. Do not execute customer analysis from that plan:
   unresolved topology/abstention contracts, rights and Phase 8/8C gates remain.
3. Preserve activated `6c1e2a4`, exact originals/history and its recovery evidence. Normal
   publication of this new slice does not authorize a replacement operational runtime.

Full production work remains: general multimodal accuracy, full physical entities
and applicability, calibrated automatic pricing, full project/audit history,
representative scale/accessibility, operational assurance and protected phase exits.
Do not turn synthetic Draft confirmations into canonical admission, locks or release.
