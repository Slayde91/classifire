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

- The owner-approved commits `6d4793b`, `51e3666`, `1de68b9` and `9cdc4a4` merged
  in [PR #265](https://github.com/Slayde91/classifire/pull/265) as
  `0e9bf984b2fe074b1bb51c6017bd59516759bd00`. Its full tree equals tested `9cdc4a4`;
  all 40 reviewed files were included. Explicit owner approval resolved the earlier
  public-destination block for all four commits.
- PR run [34725079252](https://github.com/Slayde91/classifire/actions/runs/34725079252)
  passed 2,399 tests and every remaining check before merge. No required reviews
  were configured; no human GitHub review is claimed.
- Post-merge run [34726463470](https://github.com/Slayde91/classifire/actions/runs/34726463470)
  ended cancelled at the 30-minute job limit. Its log also records a real test
  failure: 1 failed, 2,295 passed. The import-governance test computed tomorrow at
  collection but ran after midnight, when that date was correctly eligible.
  This run did not pass and was not restarted.
- Separate [PR #266](https://github.com/Slayde91/classifire/pull/266), source `7c9b570`,
  freezes that test's clock and raises the CI ceiling to 45 minutes. Application
  rules, assertions and all validation steps are unchanged; PR #255 is preserved.
  Local reproduction failed before the fix; both rollover cases passed afterwards.
  All 51 import/activation governance tests, targeted Ruff, diff and workflow
  invariant checks passed. Hosted run `34728245700` then passed 2,399 tests and all
  remaining checks. PR #266 merged as `96fdf7a932e61107af7c39262706337fcacc092b`;
  its full tree equals tested `7c9b570`. Post-merge run `34729555434` is the separate
  activation gate; verify its actual result before any deployment.
- No workspace activation follows from publication. The old `9cdc4a4` activation
  bundle is blocked by failed post-merge CI. A successful exact candidate needs a
  reconciled plan, separate owner approval, fresh matched backup and disposable
  restore verification. The new `7c9b570` plan is prepared and unapproved; its 47
  isolated launcher guard cases passed, including a corrected helper-hash pin.
  This does not prove an approved startup or fresh live recovery. The separately
  approved diagnostic runtime remains unchanged.

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
in merged PR #265. Keep activation separately approved and reconcile the exact
successful candidate after PR #266's CI repair.

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

Live 8820 remains the separately approved diagnostic source `e2e8292`. Earlier
accepted Word/Scope/package confirmations are complete and must not be repeated.
Connected upload still has the separately recorded host-policy refusal. No new
OAuth/tunnel, grant, allowlist, provider or live 15432 operation is included.

The historical ccaff7a plan excludes Complete v3. The later prepared `9cdc4a4`
plan is unapproved and blocked by PR #265's failed post-merge CI. Reconcile the
exact repaired candidate and successful PR/post-merge runs before requesting
activation approval. Fresh matched database/storage backup and disposable 15433
restore verification remain required.
Older readers cannot transparently read new Complete-v3 snapshots; retain all later
records and originals before any recovery decision. Existing absolute StoredFile
bindings must not be rewritten to bypass containment.

Other preserved synthetic demos: 8840 integrated workspace,8841 row authoring,
8842 packages,8843 Scope reports. Only 8844 was restarted for this Complete acceptance.
PostgreSQL tests use disposable 15433/classifire_containment_test, never live 15432.

## Classification and next action

PR #265 published 40 reviewed files: 19 application, 11 synthetic tests and 10 docs.
PR #266 contains two files: one test and the CI workflow. This checkpoint correction
changes documentation only. Private logs, originals, generated outputs and operator
state remain outside Git. Preserve the conflicted root and all unrelated work.

1. PR #266's exact-head CI and merge are verified. Observe existing post-merge run
   `34729555434` and retain its actual result; observation expiry is not a retry.
2. Complete the successful candidate's exact activation/recovery plan before requesting
   separate approval. Existing historical approvals do not authorize this activation.
3. Preserve the confirmed private ten-defect Draft reference and unknowns. Follow
   [reference readiness](./PHYSICAL_REFERENCE_READINESS.md) before real evaluation.
   It is not blind independent accuracy evidence or technical approval.

Full production work remains: general multimodal accuracy, full physical entities
and applicability, calibrated automatic pricing, full project/audit history,
representative scale/accessibility, operational assurance and protected phase exits.
Do not turn synthetic Draft confirmations into canonical admission, locks or release.
