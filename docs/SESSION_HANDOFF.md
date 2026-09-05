# CLASSIFIRE Session Handoff

**Verified:** 2026-09-06 (AEST). Approved ADR 0001 + ADR 0002; prototype-first delivery.
**Shared-main baseline:** `24ee6e35f181ed544ae82cdc3bc429ce70f49c3b`, merged PR #192,
feature `8c0da21476e66dac0e1e003b086271d6118c78b2`. PR CI 33967557386 and main CI
33968038437 passed 1,286 tests, 141 warnings. P3a and the supplied logo are merged.
**Current branch:** `feat/draft-estimate-reports-20260905` in
`C:\CLASSIFIRE\.tmp\draft-estimate-reports-20260905`, based on that main.
This checkpoint precedes report publication. Verify current Git/PR/CI rather than
mistaking this record for a blocker after merge. Do not redo completed work.

## Start Here / Next Session

Finish the current estimate-only P4b increment's publication if outstanding.
Then the single highest-value task is **P1b: one supported PDF evidence intake UI
path with genuine scan status, retained evidence and reviewed Draft observations**.

Why next: manual Scope/import, candidate review and manual estimates are merged;
estimate-only reports now have browser/restart evidence. The missing source-to-Scope
interaction is more valuable than polishing every report detail. Keep the scope
bounded to one PDF path; do not implement every format or a general agent/job platform.

### Inspect before editing

Read AGENTS.md, GOAL.md, current docs, ADRs and contracts. Inspect actual source,
branch/upstream/status/diff/worktrees, remote main and relevant PR/CI. Preserve the
conflicted root and unrelated changes. Use an isolated current-main worktree after
report publication. Prior summaries and test counts are navigation, not proof.

### Prerequisites, files and blockers

- Reuse `services/storage.py` exact-byte ownership/containment checks,
  `services/report_evidence_adapter.py`, `draft_scope.py`, `draft_scope_contract.py`,
  `draft_scope_ui.py`, existing templates/models/settings and storage/adapter tests.
  Inspect `worker.py` and technical intake callers before choosing execution shape.
- Current `save_upload` assigns pending/not_configured; `worker.py` has no registered
  handler. A configured optional clamd dependency is not a working producer. Deliver
  the minimum actual scan boundary and safe retained-source lifecycle with the UI.
  Record exact file/hash/page provenance and human review; foreign scan/approval
  claims or manually forcing clean must not grant local authority.
- Scope v1/v2 has no complete retained evidence locator contract. Add only the
  minimum backward-compatible revision/attachment binding required by this path;
  preserve old downloads and import authority. Plan an additive migration only
  where necessary (current report branch head: 0031_draft_estimate_reports).
- Missing/unavailable/error/infected scanning blocks extraction/viewing where the
  existing clean-byte boundary requires it. Establish bounded size/type handling,
  quarantine/retention and concurrency behavior before exposing accepted content.
  Scanner setup may be an external prerequisite; do not claim a mocked scanner
  proves production scanning. Use synthetic evidence and isolated storage only.
- Keep extraction as proposals and explicit reviewed Draft edits; no inferred
  compatibility, pricing, canonical physical records, locks, provider calls,
  customer evidence, deployment or release. Manual entry must remain usable.

### Definition of done and validation

A real browser uploads one synthetic supported PDF, sees truthful scan/failure
states, opens authorized retained page evidence, explicitly saves traceable reviewed
observations into a Draft revision, reopens after restart and downloads the saved
Scope with intact provenance. Prior revisions remain unchanged. Unsupported or
unclean files and unauthorized users are refused; no automatic downstream action.

Run focused new service/HTTP/scan/provenance tests and existing storage, evidence
adapter, Draft import/report/Estimate and physical/admission regressions. Include
content/hash/ownership changes, scanner timeout/error/infection, stale saves,
concurrent quarantine and import trust. Use disposable PostgreSQL for locking proof.
Run Ruff, Mypy, Bandit, relevant migration checks and exact-head CI. Inspect the
rendered workflow and downloaded content; do not stop at backend tests.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$taskTestBase = Join-Path $env:TEMP ('classifire-intake-' + [guid]::NewGuid().ToString('N'))
# Inspect actual relevant names before adding new intake/storage test paths.
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTestBase tests/test_draft_estimate_reports.py tests/test_draft_estimate_reports_ui.py tests/test_draft_scope_reports.py tests/test_physical_api_boundary.py tests/test_initial_canonicalisation_boundary.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
```

## Current local changes and verified evidence

Current increment adds the Estimate report service/renderer/model, migration 0031,
UI/report template/navigation, focused tests, current-head fixtures and aligned docs.
No dependency or historical migration changed. AGENTS.md already expresses the
approved decisions and prototype priority, so no instruction rewrite was needed.
The tracked architecture, roadmap and handoff files are under docs/; no root-level
copies exist in this checkout. Avoid creating parallel contradictory copies.

Local evidence: 21 report backend tests; 17 report-HTTP/migration/readiness tests;
233 combined regressions; 15 additional historical migration/preflight checks.
Runs overlap. Existing warnings are documented in PROJECT_STATE.md. Full Ruff,
Mypy (160 files), Bandit and whitespace checks passed. Hosted CI remains a gate.
Chrome report creation, later Estimate edit and actual server restart preserved
both downloads. Five PDF pages and ranges from all six workbook sheets were
visually inspected; exact decimal/string/formula behavior was programmatically checked.

Synthetic demo port 8802; data `.tmp/draft-estimate-report-demo-20260906`, artifacts
`.tmp/draft-estimate-report-artifacts`. Report captures Estimate 8 / Scope 3; latest
Estimate 9 / Scope 4. Partial subtotal AUD 441.23, no tax. One report persisted;
zero canonical Estimate/line/physical/lock or library-release rows. Demo uses
create_all; real forward migration has a separate passing test. See demo guide.

Protected root stays at de0cc5a on gpt/phase8-linked-original-images with
CHERRY_PICK_HEAD c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7. Reverified read-only:
46 unstaged modifications, 14 staged additions, four DU conflicts in linked-visual
services/tests. Recheck without mutation; never reset, clean, resolve or publish it
implicitly. Original supplied logo remains unchanged. Prior worktrees/demos and
three untracked ProjectPackage candidate files are unrelated and preserved.
Synthetic databases, browser tools, cookies and QA files stay outside commits.

Initial PR #193 CI caught lost recognition of schema 0029 after advancing the head
(526 passed, one failed). The service now preserves recognized upgrade lineages;
the original assertion was retained. Fifteen focused lineage/migration checks and
static checks passed after correction; verify the fresh full CI before merging.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE from repository evidence. Read AGENTS.md, GOAL.md, canonical docs under docs/, ADRs 0001/0002 and Draft contracts. Inspect branch/HEAD/upstream/status/diffs/worktrees, origin/main and relevant PR/CI before editing. Preserve the conflicted C:\CLASSIFIRE root, unrelated changes, prior demos and package candidate; use an isolated current-main worktree. Finish estimate-report publication only if still outstanding; do not redo merged P0/P1a/P4a/P2a/P3a or the first P4b report profile.

Deliver one task: P1b, a supported PDF evidence intake UI path. Manual scope/costing/reporting is usable; source-to-Scope intake is the next missing user interaction. Reuse services/storage.py, report_evidence_adapter.py, draft_scope.py/contract, draft_scope_ui.py, models/settings/templates and existing tests. Inspect worker.py: save_upload currently leaves pending/not_configured and no handler produces clean scans. Deliver the minimum genuine scan, retained-byte/hash/page provenance, authorized viewing and explicit reviewed observations into a saved Draft revision with the UI. Preserve old versions/import trust and optional manual operation. Determine bounded retention/quarantine/concurrency policy for this supported path; no speculative framework or every-format expansion. Unavailable/error/infected scanning must fail closed; do not fake clean or claim mocks prove real scanning. Add only necessary compatible schema/migration changes after inspecting current head (report increment adds 0031).

Done: synthetic real-browser upload/status/view/review/save/reopen and actual restart, exact downloaded provenance, unchanged history, ownership/CSRF/hash/source/scan failure and concurrency tests, no automatic matching/pricing/canonical writes/locks. Run focused intake tests plus applicable storage/adapter/Draft/report/physical regressions, migrations, Ruff/Mypy/Bandit and exact-head CI; use isolated src/unique pytest temp/no cache and disposable PostgreSQL for locking proof. Inspect actual UI and output. Update aligned docs, classify/preserve local changes, commit explicit paths, push normally, PR and merge after required checks/review; verify merge/main CI. Continue autonomously unless concretely blocked. No customer evidence, real provider, deployment or release. Full applicability, governed pricing, other reports and portability remain required; do not mark the full goal complete.
```
