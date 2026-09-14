# CLASSIFIRE Session Handoff

Reconciled 2026-09-15. Current code, Git, tests and receipts outrank this checkpoint.
Use [PROJECT_STATE.md](./PROJECT_STATE.md) for current evidence and limitations,
[CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md) for structure and authority,
and [CLASSIFIRE_ROADMAP.md](./CLASSIFIRE_ROADMAP.md) for sequencing and exits.
The requested shorter architecture/roadmap aliases are absent; root SESSION_HANDOFF.md
points here. The full production objective remains active and incomplete.

## Selected checkout and scope

Continue in `C:/CLASSIFIRE/.tmp/distribution-ui-assets-20260915`, branch
`fix/distribution-ui-assets-20260915`. PR #273 merged as `46fc436` after 2,647
passing tests and all CI checks. Its post-merge run `34869099059` is in progress.
The selected branch includes that merge and the packaging fix: installed wheels
retain the existing UI resources and CI verifies their exact source bytes.
Runtime/build code matches combined candidate `25dd47d`, which passed 78 affected
tests, a 326-file wheel check and fresh offline installation checks. No activation
is included. Review the exact diff against current main before publication.

The ancestor range implements native Word/PDF/XLSX evidence selection and typed
additions, selected Scope edits, explicit saved generations/decisions and v7 package
history. It also fixes delayed UI replies, explicit proposal-only packaging,
source/Draft lock ordering, rejection rights after waits and rejection-card cleanup.
Do not rebuild these features or cherry-pick the standalone `8bce0b0` test correction
into this stack: the equivalent expanded assertion is already present.

Startup fix `c47c119` reuses the existing read-only lineage assessment after the
packaged-head check. It refuses missing required tables and retired tables before
production startup/CLI writes. No schema or authority change is introduced. It passed
89 affected tests and seven candidate checks on a separate owned PostgreSQL15433
database, plus an old-code failure control; guard connections were read-only and
dumps unchanged. This remains narrower than complete production schema certification.

The full `5418f51` regression terminated after 928 passes and one fixture failure.
The imported-evidence UI test supplied an obsolete generic object without
`history_members()`. This follow-up uses the real `InspectedPackage` type and
explicitly preserves empty history. All 60 affected navigation tests passed;
permission, exact-identity and no-implicit-action assertions remain. Earlier
chronology and failed attempts remain in Git and private receipts.

## Publication and operational boundaries

- PR272 merged as `370888c54549642c1213eb4e2ebed2c54081aeb2`; its tree matches
  tested `cb82409`. PR CI34846714887 passed 2,630 tests (1,892.04 seconds).
  Post-merge CI34853579643 passed 2,630 tests (1,963.93 seconds), plus all later checks.
  PR271 post-merge CI34841047799 also succeeded. No existing job was restarted.
- The private historical-copy conversion/recovery rehearsal passed on15433. Existing
  data and the two original-file hashes survived. Recovery schema matches an independent
  restored migration reference; raw PostgreSQL check text changes after dump/restore.
  Fresh live drift, original owner/ACL and current file linkage remain unverified.
- Guarded migrated restart is merged as `46fc436`; PR CI `34862079545` passed
  2,647 tests in 3,509.19 seconds and every later check. Observe post-merge
  `34869099059`. Publish the distribution fix and merge only after its own
  successful exact-head CI and required reviews.
- The stack includes the expanded Word/PDF/XLSX form correction. Standalone
  `8bce0b0` remains preserved locally; do not duplicate that earlier patch.
- Diagnostic PR270 merged, but post-merge 34753856708 cancelled without a full summary.
  Do not restart a job because observation expired; poll the same live handle when one exists.
- The last observed 8820 listener was PID 24324. The approved receipt is rollback 6c1e2a4,
  chat disabled after the 7dbc1cc follow-up 502. Its cause is unknown. Old provider
  allowances are consumed; a new exact test and activation need separate approval.
- Shared main migration head is 0049 after 0048; the older 97c0778 baseline is 0047. Both new
  migrations refuse destructive downgrade. v7 history adds no further DB migration.
  Never assume code-only rollback; preserve post-backup writes and newer artifacts.
- Keep OAuth/tunnel/host policy and customer/technical/commercial authority unchanged.
  Original Word project/Scope/package confirmations are complete; do not repeat them.

## Verified evidence and remaining checks

Private evidence is under `C:/CLASSIFIRE/.tmp/`. The `5418f51` ancestor review ledger is in
`native-document-reconciliation-20260914/range-review-progress.json`. It records
scope and hashes for 84 files: 75 non-document files and nine documents. Complete-file
and changed-line reviews are distinguished. This is not public approval or full
confidentiality/production certification.

Earlier full runs: d33f5ec passed 2,574 with two Windows symlink skips; 1aeded3 passed
2,593 with two skips and terminal exit 0. Neither covers all later fixes or v7.
Later targeted tests and artifacts are recorded by version in PROJECT_STATE.md.
Earlier UI source ef790d1 has 35 passing Node cases and 16 nearby pytest cases;
synthetic DOM checks do not prove visible interaction. Thirteen complete test-file
reviews matched 137 prior passes to unchanged content; five independently inspected
ZIPs verified 21 members, exact Word/PDF originals and explicit decision selection.
The later full `5418f51` run ended with exit1 and 928 passes/one failure, zero
skips/errors, before the remaining collected tests ran. Read
`native-stack-full-validation-5418f51-20260914/attempt2/run.json` and its JUnit/log.
The runner and pytest processes exited; do not keep polling their historical PIDs
as though still active. The corrected pinned 5279904 full run also finished:
2,623 passed, two Windows symlink capability skips, exit 0 in 8,868.19 seconds.
PR271 Linux CI subsequently passed all 2,625 tests. Four fresh ZIPs from the completed
local run matched 10 manifest members and the exact Word/PDF originals; proposal-only
history has no decision authority. The import optimization needs its own checks.
The merged workflow retains every check and uses verbose test/duration output with a
90-minute job budget. Do not change test selection or assertions to shorten CI.
Startup evidence is in `startup-lineage-validation-evidence-20260914`, including
`postgresql/receipt.json`; fixture checks are in
`imported-evidence-fixture-validation-20260914/targeted.xml`.

Actual-main HTTP/server restart and exact synthetic recovery at 23f5110 passed:
read `native-history-http-restart-23f5110-20260914/attempt3/receipt.json` and
`native-history-http-restart-23f5110-20260914/recovery/continuation-receipt.json`.
Seventy-one tables, 76 rows, schema and retained bytes matched. Normal transactions
plus a SQL-mutation guard allowed required source locks and recorded no mutations.
Owner/ACL restoration was excluded; test-mode HTTP is not production or browser proof.
Preserve the earlier harness failures; do not repeat completed recovery unnecessarily.

The earlier 0048 browser history journey passed. New 0049 decision/v7 package controls
still need rendered-browser acceptance; the browser helper failed initialization.
Real-provider/live acceptance, full raw provider/prompt-version lineage, retention
policy, representative accuracy and the broader Phase 8-16 exits remain incomplete.

## Next executable task

Finish the distribution fix as one coherent update. Its code and regression tests
are reviewed and passed; the combined `25dd47d` evidence is in
`combined-release-25dd47d-20260915`. Fresh isolated installation preserved all
constrained dependencies; two installed HTTP starts and five installed worker modes
passed. The database checks used disposable 15433 and preserved full dumps.
Publish explicit files from the selected branch, then observe its exact-head CI
and required reviews before merge. Record post-merge results separately and retain
branches. Also observe PR #273 post-merge run `34869099059`; do not restart jobs.
Then finish the operational launcher/dependency and fresh-backup/restore/rollback
plan, including preserved roles/grants and current file linkage. The historical-copy
conversion proof is in `native-activation-readiness-370888c-20260915`; it does not
prove current live state. New0049/v7 rendered-browser acceptance remains blocked
by browser-helper initialization. Live activation/provider testing needs a new exact
approved plan; preserve consumed allowances and original Scope/package confirmations.

Tests use `C:/CLASSIFIRE/.tmp/native-stack-test-env-20260914/Scripts/python.exe`,
the selected checkout's `src` (and `tests` where required) on PYTHONPATH,
`-p no:cacheprovider` and a unique basetemp. Clear inherited live/model configuration
and use explicit synthetic fixtures. PostgreSQL must be owned disposable 15433,
never live 15432; do not overlap tests that drop the same synthetic database.
No real API key or workspace-chat.env content belongs in commands, logs or Git.

Preserve root `C:/CLASSIFIRE`: 46 unstaged modifications, 14 staged additions, 4 DU
conflicts, unrelated untracked/private files and inaccessible old test directories.
Use isolated checkouts and explicit staged paths. Pinned runtime/rollback checkouts
and private evidence must remain intact. Do not reset, clean, resolve or publish root.

## Copy-ready next-session prompt

Continue CLASSIFIRE from repository evidence. Read AGENTS.md, GOAL.md and the canonical
state, architecture, roadmap and handoff. Use the isolated
C:/CLASSIFIRE/.tmp/distribution-ui-assets-20260915 checkout and verify HEAD/status.
PR #273 merged as 46fc436 after 2,647 tests and all checks passed; observe its
post-merge run 34869099059. The current packaging change includes 67 templates and
19 static assets in the wheel and verifies exact source bytes in CI. Combined
runtime/build code at 25dd47d passed 78 affected tests, a 326-file wheel comparison,
fresh offline dependency installation, two installed HTTP starts and five isolated
Word/XLSX worker modes. Inspect the full current diff and private evidence in
combined-release-25dd47d-20260915. Finish explicit-file publication and CI/review-gated
merge where authorized; record post-merge CI separately and retain branches.
Do not restart jobs because observation timed out. The historical 15433 conversion
and independent-reference recovery passed, but do not prove current live state or
owner/ACL restoration. Finish the exact launcher, fresh-backup, roles, storage and
rollback plan before requesting new activation/provider approval. Live 8820's last
receipt remains rollback 6c1e2a4 with chat disabled. Use selected-checkout PYTHONPATH
and fresh basetemp; PostgreSQL tests only on owned 15433 databases, never live 15432.
Preserve unknowns, blank openings, separate human Scope/package confirmations,
original evidence and foreign-history authority. Keep the conflicted root and
private evidence untouched. Rendered-browser acceptance of newer 0049/v7 controls
and full Phase 8-16 production exits remain incomplete.
