# CLASSIFIRE Session Handoff

**Verified:** 2026-09-05 (AEST).
**Shared-main baseline before this increment:**
`96d686952021828ef1fb28b53f4d6eea566376aa` (merged PR #188).
**P1a branch/worktree:** `feat/draft-scope-import-20260905` at
`C:\CLASSIFIRE\.tmp\draft-scope-import-20260905`.
**Architecture:** accepted ADR 0001 + approved ADR 0002; prototype-first delivery.
Check current P1a PR/CI/merge state before continuing; a local demonstration and
shared publication are separate facts.

## Start Here / Next Session

**Single first task: P4a, scope-only Draft PDF/XLSX reporting from a selected saved
Scope revision.** Verify P1a publication first. Deliver a real UI action, preview,
frozen report snapshot, both downloads and persistence after restart together.

**Why next:** P0 manual editing and P1a saved JSON exchange are demonstrated. The
roadmap already permits the scope-only P4 profile early. This adds another useful
independent capability using the existing output libraries. Evidence intake is
still required, but actual scanning, PostgreSQL clean-byte reads and source-retention
policy must be established before parsed uploads are exposed. A pending-upload
screen would not complete Scope Analysis.

### Inspect before editing

Read `AGENTS.md`, `GOAL.md`, `docs/PROJECT_STATE.md`, the relevant architecture and
roadmap sections, ADRs 0001/0002 and `docs/DRAFT_SCOPE_V1_CONTRACT.md`. Inspect
branch/HEAD/upstream/status/conflicts/worktrees, current main and relevant PR/CI;
reconcile newer source and tests before selecting edits. Use an isolated current-main
worktree. Preserve the conflicted root, unrelated changes and package candidate.
Do not rebuild the completed P0/P1a interactions or seek architecture approval again.

Relevant components:

- `src/classifire/services/draft_scope.py`: owner/admin access, verified v1/v2
  revisions, import history and exact saved bytes. The report pins a chosen revision.
- `src/classifire/draft_scope_ui.py`, Draft templates and static scripts: existing
  UI, CSRF and permission patterns. Add the report interaction here or a small adapter
  using the same application services, without duplicating domain rules.
- `src/classifire/outputs/common.py`, `outputs/pdf.py`, `outputs/xlsx.py`: existing
  ReportLab/XlsxWriter branding/layout patterns. Their Estimate schemas are not a
  valid Draft Scope input; do not fabricate an Estimate to satisfy them.
- `src/classifire/outputs/desk_quote.py`, `api/router.py`: separately classified
  output/snapshot and cached artifact-integrity patterns worth reusing selectively.
- `src/classifire/services/snapshot.py`: `build_estimate_snapshot` recalculates.
  Do not call it for a read-only Draft report. Existing canonical export locks remain.
- `src/classifire/models.py`, storage services and packaged migrations: determine
  the smallest explicit immutable report snapshot/output mapping in the existing
  persistence stack. Add a forward migration only if needed.
- `tests/test_snapshot.py`, `test_desk_quote.py`, `test_draft_scope.py`,
  `test_draft_scope_ui.py`, import/authority tests and new report/HTTP tests.
- `scripts/run_draft_scope_demo.py`, `docs/DRAFT_SCOPE_DEMO.md`: isolated synthetic
  launcher and actual UI demonstration instructions.

### Prerequisites, dependencies and blockers

P1a source and its required CI must be available on the selected branch. Existing
ReportLab, XlsxWriter, PyMuPDF, pypdf and openpyxl are declared; verify installed
dependencies before using them. Saved manual/imported Scope reporting needs no AI,
scanner or customer file. Use synthetic data and isolated storage only.

P4a needs one explicit snapshot contract capturing Scope envelope/revision/hash,
project labels, profile/render version and output identities. Freeze these together
so later project edits, Scope revisions or rendering changes cannot silently alter
an earlier download. Ownership/permissions and exact stored-output hashes must be
checked by the backend. Do not introduce a second application/database/framework.

The shared numeric helper `d()` converts absent values to zero; do not use it for
unknown Scope quantities. Escape user text in ReportLab Paragraphs and prevent XLSX
formula/URL interpretation of user strings. Existing renderer patterns do not prove
safe handling for newly exposed fields.

No known architecture blocker prevents P4a. Full tenant privacy and production
readiness are unproven. P1b retains separate actual-scan, PostgreSQL verified-read,
source-retention and safe concurrent-upload prerequisites; do not bypass them.

### Definition of done for P4a

1. An authenticated owner/admin explicitly selects a saved Scope revision and
   creates/previews a clearly labeled scope-only Draft report. No upstream step runs.
2. PDF and XLSX consume the same retained snapshot: stable project/Scope/report
   identity, revision/hash/profile version, defects, openings, services and links,
   quantities/units, observations, assumptions, exclusions and manual/import lineage.
   Missing technical/pricing information is unavailable, not invented or zero-priced.
3. Both files are downloadable through checked permissions and stable output
   bindings. Restart/reopen returns the same saved outputs; subsequent Scope or
   project edits do not change the earlier report. Unsupported/stale inputs are clear.
4. Inspect rendered PDF pages and actual workbook cells/types, filters, units and
   links. Demonstrate shared/blank openings, unknown quantities, imported history,
   long text and hostile spreadsheet/PDF markup. No false approval/release claims.
5. Relevant report/service/HTTP/security/migration regressions and static checks
   pass. Prove no AI, matching, recalculation, canonical physical write, lock or
   release occurs. Keep existing v1/v2 bytes and import behavior compatible.
6. Record actual browser/output/restart evidence, update docs, classify changes,
   commit/push normally, create/update the PR and merge only after exact-head CI
   and required review permit it. Verify the merge; do not deploy or use real data.

This completes only P4a, not every report profile, all four capabilities, complete
ProjectPackage export, production tenancy or the full active product goal.

### Validation commands

Run from the isolated feature worktree, with current declared dependencies installed:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$taskTestBase = Join-Path $env:TEMP ('classifire-draft-report-' + [guid]::NewGuid().ToString('N'))
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTestBase tests/test_draft_scope.py tests/test_draft_scope_import.py tests/test_draft_scope_ui.py tests/test_draft_scope_import_ui.py tests/test_snapshot.py tests/test_desk_quote.py tests/test_human_session_security.py tests/test_physical_api_boundary.py tests/test_initial_canonicalisation_boundary.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -r src
node --check src/classifire/static/draft_scope.js
node --check src/classifire/static/draft_scope_import.js
git diff --check
```

Add the new report/output/HTTP tests to the command once implemented. If migration
head changes, reconcile deployment-lineage readiness and current-head fixtures;
run the full migration and affected preflight collection, preserving historical
migration cases. Hosted CI runs PostgreSQL concurrency; local skips are not passes.
Mypy needs declared stubs (the prior local environment needed temporary missing-stub
support). Do not hide dependency failures. Inspect PDF page images and workbook
cells as well as browser downloads. No real-report UAT or configured customer DB
`doctor` run is authorized by this task.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE toward accepted ADR 0001/ADR 0002, with working UI slices first.
Inspect repository state BEFORE editing: AGENTS.md, GOAL.md, project state,
architecture, roadmap, handoff, ADRs and Draft Scope v1/v2 contract. Verify current
main/branches/worktrees/diffs/PR/CI and newer source. P0 merged PR #188 at 96d6869;
P1a was demonstrated on feat/draft-scope-import-20260905. Verify its publication.
Preserve C:\CLASSIFIRE's conflicted recovery checkout, unrelated changes and the
unpublished package candidate; use a clean current-main worktree.

Single task: early P4a scope-only Draft PDF/XLSX reporting from a selected saved
Scope revision. This adds another visible independent capability after working
manual editing/import. The roadmap permits this early profile; evidence intake
still needs actual scanning, PostgreSQL clean reads and retention policy.

Inspect services/draft_scope.py, draft_scope_ui.py/templates, outputs/common.py,
outputs/pdf.py, outputs/xlsx.py, outputs/desk_quote.py, api/router.py, snapshot.py,
models/storage/migrations and related tests. Reuse existing libraries/patterns;
do not fabricate an Estimate, call recalculating build_estimate_snapshot or bypass
canonical export locks. Freeze Scope envelope, project labels and render/profile
version in one retained report snapshot with exact PDF/XLSX output bindings.

Deliver actual create/preview/download/reopen-after-restart UI behavior. Include
scope relationships, quantities/units, uncertainty, notes and imported lineage;
technical/pricing data remains unavailable. Unknown quantities are not zero.
Preserve old v1/v2 artifacts and report bytes after later edits. Enforce ownership,
CSRF, output integrity and safe filenames; escape PDF markup and prevent XLSX
formula/URL interpretation. Synthetic data only; no AI, canonical writes or release.

Done: new report/output/HTTP tests plus relevant Draft/import/authority/migration
regressions pass; Ruff/Mypy/Bandit, JS and diff checks pass; actual PDF page images,
workbook cells/types and browser downloads are inspected; restart retains identical
outputs. Use handoff commands with worktree src in PYTHONPATH and isolated storage.
Update docs, classify changes and continue autonomously through commit, normal push,
PR and merge after exact-head CI/reviews pass; verify merge. Do not expand to other
profiles, evidence ingestion, speculative infrastructure, deployment or real data.
Report evidence, limits, Git/PR status and the next useful visible increment.
```

## Verified P1a evidence and local context

- Actual Chrome upload/preview/confirmed replacement, v1 to v2 import, manual edit,
  v2 reimport, unchanged historical downloads and tampered-file refusal passed.
  Preview/content screenshots were visually inspected. Actual server restart and
  saved v2 download passed with identical bytes; no browser page errors.
- Final/restart/post-refusal file SHA-256:
  `ef77991ef46955ae917e0a252ff19651ee8a3251f2d018c66fff6f759f437442`.
  Envelope hash: `dd930c4e1ab0861fce9551c556f1ccc4bc076dce598ac1e541eb1359017f840e`.
  Synthetic DB: one Draft, five revisions, zero canonical physical/estimate/lock rows.
- Final combined regression: **118 passed, one local PostgreSQL skip, one existing
  Starlette/httpx warning**. Full Mypy passed 146 source files; Ruff/Bandit, JS
  syntax, template/escaping and whitespace checks passed. Verify final PR/CI separately.
- P1a changes only Draft service/UI/tests and docs. No migration or new dependency;
  head remains `0027_draft_scope_revisions`. Exact raw uploads are bounded to 288 KiB,
  source metadata lineage to 16 records; original attachments/foreign revision chains
  are not retained by this narrow JSON import.
- Active demo uses port 8797 and `.tmp/draft-scope-import-demo-20260905`. Browser
  artifacts are in `.tmp/draft-scope-import-artifacts`; tools in
  `.tmp/scope-browser-test-tools`. Keep generated files/cookies out of Git.
- Legacy root remains `gpt/phase8-linked-original-images`, HEAD `de0cc5a`, with
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`, four conflicts and
  staged/unstaged/untracked recovery work. Do not reset, clean or broadly stage it.
- `.tmp/project-package-draft-20260905` retains three unrelated untracked files
  (contract/service/tests); prior 22 synthetic tests are historical evidence only.
  The clean P0 branch/worktree and synthetic port 8796 demo are also preserved.
- Historical issues #42/#43 and draft PRs #9-#13 remain recovery/operations context;
  requery current state when relevant. Real provider/UAT/lock/release/deployment
  operations were not authorized or exercised by this increment.

Use [PROJECT_STATE.md](./PROJECT_STATE.md) for facts and health,
[the roadmap](./CLASSIFIRE_ROADMAP.md) for sequencing and
[the architecture](./CLASSIFIRE_ARCHITECTURE.md) for boundaries.
