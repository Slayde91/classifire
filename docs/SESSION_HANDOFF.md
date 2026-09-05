# CLASSIFIRE Session Handoff

**Verified:** 2026-09-05 (AEST).
**Shared-main baseline:** `02dc20022b87b532c3d860d4c12527bdfb60dd05`, merged
[PR #191](https://github.com/Slayde91/classifire/pull/191), feature
`21b53363b3e5037b7ad3496c002d0cd84c47fe21`.
[PR CI 33955043986](https://github.com/Slayde91/classifire/actions/runs/33955043986)
and [main CI 33955401203](https://github.com/Slayde91/classifire/actions/runs/33955401203)
both passed 1,191 tests, 141 warnings.
**Current P3a branch:** `feat/draft-estimate-ui-20260905` at
`C:\CLASSIFIRE\.tmp\draft-estimate-ui-20260905`, based on that main.
**Architecture:** approved ADR 0001 + ADR 0002; prototype-first delivery.
This checkpoint precedes P3a publication. Verify final commit/PR/checks/merge from
current Git and GitHub; do not mistake this prepublication record for a blocker if
P3a has since merged. Full product completion and production readiness remain open.

## Start Here / Next Session

Finish P3a validation/publication if still outstanding. Then the **single
highest-value next task is P4b: estimate-only Draft PDF/XLSX reporting** over an
explicit saved Draft Estimate revision.

Why next: P0 editing, P1a JSON exchange, P4a Scope reports and P2a candidate review
are merged. P3a now makes manual costing usable; readable, portable estimate
reports turn that saved work into something a user can review outside the UI.
Broad applicability, pricing inference and every source format need not block
this honest partial report. The full product goal remains larger than this slice.

### Inspect before editing

Read `AGENTS.md`, `GOAL.md`, the four current docs, ADRs 0001/0002 and Draft
contracts. Inspect branch/HEAD/upstream, diffs/conflicts/worktrees, current remote
main and relevant PR/CI. Reconcile source/tests before editing. Preserve the
conflicted root, unrelated changes and prior demos. Use an isolated current-main
worktree after P3a publication. Do not rebuild merged increments or seek approval
again for the already accepted hybrid/independent-capability architecture.

### Next task scope, files and prerequisites

- Select one authorized saved Draft Estimate revision/hash; capture its complete
  validated envelope, project labels and explicit estimate-only profile/version
  into one immutable report snapshot. Preview the chosen basis before creation.
- Generate PDF/XLSX from that same snapshot and retain both atomically with byte
  hashes. Read/download must verify stored bytes, never regenerate them. Later
  Estimate/Scope/attached-review/source or project changes show stale reasons
  without rewriting earlier reports or requiring an upstream rerun.
- Show the retained service/blank-opening identities, units, quantities, rates,
  original values, reasoned override/omit/restore history and source notes. Include
  unpriced, omitted, unrepresented and unassessed work plus the partial AUD subtotal.
  Tax remains uncalculated; technical status remains unapproved. Attached reviews
  are provenance/context, not an applicability verdict or a combined-report claim.
- Reuse `services/draft_estimates.py`, `draft_estimate_contract.py`,
  `draft_scope_reports.py`, `draft_scope_ui.py` report routes,
  `outputs/draft_scope.py`, `draft_estimate_ui.py`, templates and their tests.
  Extend existing report abstractions where coherent; preserve the strict
  Scope-only profile and existing rows. Add only the minimum estimate profile,
  retained binding and forward migration needed. Current head is
  `0030_draft_estimates`; never rewrite historical migration files.
- Define spreadsheet precision before rendering: supported values can produce
  `999999998000000001.00`, which a float loses precision on. Preserve exact decimal
  text for authoritative values; use numeric columns only under an explicit tested
  safe-precision policy. Unknown must not become zero. Disable formula/URL inference
  for user text and inspect long/hostile content and workbook cell types.
- Use the supplied `static/brand/classifire-logo.png` for newly generated report
  branding with a suitable display frame. Never rewrite existing retained report
  outputs or their hashes. The original square PNG is preserved byte-for-byte.
- Apply active human owner/admin and project/estimate permissions, export permission
  for downloads and technical access for attached review content, with fresh checks
  around source/storage work. Test denial and revocation independently of the UI.
- Do not invoke canonical Estimate creation, `recalculate_estimate`, the canonical
  `build_estimate_snapshot`, physical writes, locks, matching, tax or release. Those
  paths retain their existing gates. The Draft renderer displays validated saved
  arithmetic and does not change the estimate.

No new infrastructure, dependency or external evidence is known to be required.
P1b scan/storage/retention, P2b actual applicability and P3b governed pricing
XLSX/default/inferred methods remain required separate work. Their missing breadth
does not block this bounded synthetic report profile. No customer evidence, real
provider, operational canonical record/lock, deployment or release is authorized.

### Definition of done and validation

1. An authenticated real browser selects an explicit saved estimate, previews it,
   creates both files, reopens/downloads them and retains identical bytes after an
   actual server restart and later upstream edits.
2. PDF pages are rendered and visually inspected. Workbook sheets/cells/types are
   inspected, including exact amounts, six-decimal rates, large-value precision,
   unknown/zero distinction, omissions, histories, IDs, long text and hostile text.
   Both outputs agree with the same retained snapshot and declare partial coverage.
3. Service/HTTP/output tests cover ownership/permissions/revocation, CSRF, integrity,
   staleness, historical reads and atomic output failure/rollback. No upstream
   capability or canonical writer runs. Existing reports remain unchanged.
4. Appropriate forward-migration/current-head, existing Draft, snapshot, desk-quote
   and physical/admission regressions pass, alongside Ruff, Mypy and Bandit.
5. Classify all changes, update aligned docs, commit explicit paths, push normally,
   open/update PR, review exact-head CI, merge safely and verify the merge/main CI.

From the isolated worktree with declared development dependencies installed:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$taskTestBase = Join-Path $env:TEMP ('classifire-estimate-report-' + [guid]::NewGuid().ToString('N'))
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTestBase tests/test_draft_estimates.py tests/test_draft_estimate_ui.py tests/test_draft_scope_reports.py tests/test_draft_scope_reports_ui.py tests/test_draft_scope_outputs.py tests/test_snapshot.py tests/test_desk_quote.py tests/test_physical_api_boundary.py tests/test_initial_canonicalisation_boundary.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src --no-incremental
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
```

Add the actual new feature/migration tests after inspecting their names. Use hosted
or disposable PostgreSQL for skipped concurrency cases; SQLite does not prove those
behaviors. Never point tests at the operational database.

## Current increment, local changes and evidence

P3a adds shared manual estimate service/contract, immutable parent/revision tables
and migration 0030, thin routes/templates/Scope navigation, tests and documentation.
Current-head/deployment fixtures advance coherently while historical migrations
remain unchanged. The exact supplied PNG replaces the old sidebar/sign-in/favicon
asset reference; report master/output bytes remain unchanged in this UI increment.
`AGENTS.md` already expresses accepted ADRs, prototype priority and authority rules;
review confirmed no instruction change was needed.

Measured local evidence: 53 backend tests; 40 HTTP tests plus an overlapping
three-case form-bound rerun; 27 migration tests and 20 related readiness/preflight/
legacy tests. One initial missing-table readiness fixture omission was corrected
before its passing rerun. Full Ruff, Mypy (157 source files) and Bandit passed.
The combined relevant regression passed 328 tests with one dedicated PostgreSQL
concurrency skip and one existing Starlette/httpx warning. Hosted CI must cover
the skipped database case; verify final Git/CI publication evidence.

The Chrome demonstration created one Scope/four revisions and one Estimate/eight
revisions, covering unknown pricing, direct six-decimal unit rates, overrides,
omission/restoration, stale dependencies and exact historical downloads. Partial
subtotal: AUD 441.23, tax uncalculated. Login/sidebar and saved lines were visually
inspected. Actual restart preserved revision 2 and 8 download bytes. A first harness
navigation raced startup; after HTTP readiness succeeded the comparison passed.
No library releases or canonical Estimate/line/physical/lock rows were created.
Local demo runs at port 8801; data is `.tmp/draft-estimate-demo-20260905`, artifacts
are `.tmp/draft-estimate-artifacts`. See DRAFT_SCOPE_DEMO.md for URLs and hashes.

Protected `C:\CLASSIFIRE` remains at `de0cc5a` on
`gpt/phase8-linked-original-images`, CHERRY_PICK_HEAD
`c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`: 46 unstaged modified paths, 14 staged
additions and four DU conflicts, plus untracked recovery material. Do not resolve,
reset, clean, broadly stage or publish from it. Conflicts are the linked-visual
service/evidence files and their tests, unrelated to this increment. The original
user-supplied `classifire logo.png` remains untouched in the root.

Prior P0/P1a/P4a/P2a worktrees/demos and `.tmp/project-package-draft-20260905` are
preserved. The package candidate has three untracked contract/service/test files;
its historical 22-test result is not current-main qualification or a shipped
package. Demo databases, source fixtures, cookies, screenshots, harnesses and
receipts stay outside the feature diff under `.tmp`.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE from verified repository state. Read AGENTS.md, GOAL.md, the four canonical docs under docs/, approved ADRs 0001/0002 and current Draft contracts. Inspect branch/HEAD/upstream, status/diffs/conflicts/worktrees, origin/main and relevant PR/CI before editing. Preserve the conflicted C:\CLASSIFIRE root, unrelated changes, prior demos and package candidate; use an isolated current-main worktree. Finish P3a publication if still outstanding and do not redo merged work.

Deliver one task: P4b estimate-only Draft PDF/XLSX reports from an explicit saved Draft Estimate revision. Manual costing is now usable; readable retained reports add immediate user value before broad applicability/pricing refinement. Reuse services/draft_estimates.py, draft_estimate_contract.py, draft_scope_reports.py, draft_scope_ui.py report routes, outputs/draft_scope.py, draft_estimate_ui.py and current templates/tests. Freeze the complete envelope/project labels/profile version, preview, atomically retain both outputs and verify exact downloads. Show retained quantities/rates/originals/reasoned overrides, omissions/unknown work and the partial AUD subtotal with tax uncalculated. Preserve exact decimal text beyond spreadsheet numeric precision; test any numeric presentation policy and formula/URL safety. Use the supplied current logo for new outputs without rewriting historical files.

Preserve owner/admin and project/estimate read/write/export boundaries, optional technical permissions, source/hash checks, stale dependencies and immutable history. Do not rerun matching/calculation or call canonical build_estimate_snapshot, physical writers, locks or release. Current migration head is 0030_draft_estimates; add a forward migration only if needed. No known external blocker exists for this synthetic profile; scan/retention, full applicability and pricing XLSX/default/inferred methods remain separate required work. Avoid speculative frameworks and customer/provider/deployment operations.

Done means real browser preview/create/download, actual restart and historical byte equality, visually inspected PDF pages and inspected XLSX cells/types/totals, including large decimals, six-decimal rates, unknown/zero, long/hostile text and history. Run focused renderer/service/HTTP/authority/atomic-failure tests, applicable migration checks, existing Draft report/estimate, snapshot, desk-quote and physical/admission regressions, Ruff, Mypy, Bandit and exact-head CI. Use isolated src, unique pytest temp storage and disabled cache. Update aligned docs, classify/preserve unrelated changes, commit explicit paths, push normally, PR and merge after required checks/review; verify merge/main CI. Continue autonomously unless concretely blocked. Report limits honestly; this does not complete the full product goal.
```
