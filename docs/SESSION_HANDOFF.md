# CLASSIFIRE Session Handoff

## Verified context

2026-09-06 AEST. Worktree `C:\CLASSIFIRE\.tmp\draft-package-import-v1-20260906`;
branch `feat/draft-package-import-v1-20260906`, based on shared main
`d2709d84c70d7295624cb090ce1d6f6190dab5f1` (PR #201).
PR #201 exact-head CI 33999996200 rerun and main CI succeeded. PR #200 already merged
selected package download. Inspect live current-branch PR/CI before publication or
continuation; this file is a checkpoint, not evidence of a later merge.

ADRs 0001/0002 are accepted: independent capabilities, shared deterministic core,
optional AI and UI-first delivery. No OpenClaw retirement or production release.
The full objective remains incomplete. Import preview is not completed import.

## Current changes and checks

Shared `services/draft_package_import.py` validates selected ZIP manifest, all JSON
artifact/report schemas, exact dependencies and source inventory. Package UI adds
`/package-import` and `/package-import/preview`; the Scope list links to it.
`ui_uploads.single_file` reuses PDF intake's bounded multipart pattern. Existing PDF
and pricing routes now share that helper. No new dependency, database migration or
imported local record. Original report bytes are not opened/scanned/downloaded.

Three service and two HTTP tests passed. Affected package/PDF/pricing HTTP regression:
14 passed, 5 PostgreSQL-dependent skipped locally. Mypy (181 files), Ruff and Bandit
passed. Pricing import-preview permission coverage requires hosted PostgreSQL CI.
Chrome inspected Scope-only/populated ZIPs, refused invalid bytes and showed the exact
supplied logo. A fresh marked demo retains zero project/Draft/canonical records.

Demo: `http://127.0.0.1:8810/package-import`; login `scope-demo@example.test` /
`synthetic-scope-demo-only`. Data: `.tmp/draft-import-preview-demo-20260906`.
Launcher: `scripts/run_draft_scope_demo.py --port 8810 --data-dir <that-directory>`.
Inspect process IDs/command lines before stopping only this demo. Earlier 8809 demo
and `.tmp/package-artifacts` ZIPs are unchanged.
Receipts: `.tmp/import-preview-browser-receipt.json`, `import-preview-db-counts.json`;
screenshots `import-preview-*.png`; browser script
`.tmp/scope-browser-test-tools/import-preview-check.cjs`. These remain local-only.

Preserve the legacy root on `gpt/phase8-linked-original-images`: four DU conflicts,
46 unstaged modifications and 14 staged additions, plus unrelated untracked files.
Preserve `.tmp/project-package-draft-20260905` and its three untracked generic archive
files. The older `feat/draft-package-import-20260906` branch had no import code.
Do not reset, clean, resolve, broadly stage or publish recovery work.

## Start Here / Next Session

Inspect AGENTS.md, GOAL.md, project state, roadmap, architecture/ADRs, Git status,
worktrees, origin/main, PRs and exact-head CI. Preserve unrelated work and continue
from an isolated current-main worktree once current publication is resolved.

**Single next task: complete safe new-project Draft ProjectPackage import.** Users
can now download and inspect selected work; they still cannot reopen the ZIP as a new
editable local project. Do not replace this task with more preview polish.

Files: `services/draft_package_import.py`, `draft_project_packages.py`, Scope import,
`draft_system_match_contract.py`/`draft_system_matches.py`, Estimate contracts/services,
report snapshot readers, models/migrations, package UI/templates and tests.
Read `docs/DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md` and architecture's import section.

Prerequisites/dependencies: full selected semantic validation now exists. Establish
explicit local identities and foreign provenance, immutable original-byte retention,
scanner/quarantine handling for PDF/XLSX, and atomic ownership-bound import. Existing
`DraftSystemMatch.release_id` requires a local release: do not create fake library
eligibility to satisfy that FK. Imported approvals/source claims remain unresolved.
Use existing persistence and shared use cases, not another parallel application.
No external blocker is currently established; these are remaining implementation work.

Definition of done: actual UI upload/preview, explicit transaction creating one new
owned Draft project, retained original artifacts/history/outputs, explicit identity
mapping, local read/edit semantics for Scope/review/Estimate, restart and traceable
re-export for both Scope-only and populated packages. No dropped unsupported members,
implicit recalculation/provider/canonical write/lock/release or foreign authority.
Scanner failure, revoked rights, malformed input and rollback must fail safely.

Validation: import service/HTTP/permission/CSRF/unsafe archive/identity/rollback tests;
affected Scope/review/Estimate/report/upload and migration tests; real synthetic
browser round trip/restart and independent ZIP/content inspection. Current commands:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_package_import.py tests/test_draft_package_import_ui.py tests/test_draft_project_packages.py tests/test_draft_project_package_ui.py tests/test_draft_pdf_ui.py tests/test_draft_pricing_ui.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Read AGENTS.md, GOAL.md,
> docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/SESSION_HANDOFF.md and accepted ADRs 0001/0002; inspect Git status/diff/worktrees,
> origin/main and current PR/CI before editing. Preserve the conflicted C:\CLASSIFIRE
> root, unrelated local work and older package experiments; use an isolated worktree.
> The single next task is complete safe new-project Draft ProjectPackage import:
> download and no-write semantic inspection exist, but users cannot reopen the ZIP
> as an editable local project. Inspect draft_package_import, package/Scope services,
> Match/Estimate contracts, report readers, models/migrations, UI and tests. Reuse
> current validation; do not rebuild preview or substitute Scope-only import. Retain
> all selected original artifacts/history/output bytes, map identities explicitly,
> scan/quarantine binaries and create new owned Draft records transactionally.
> Existing Match release_id needs an explicit imported-origin solution, never a fake
> eligible library release. Foreign sources/approvals remain unresolved. Done means
> actual UI confirmation, full local Scope/review/Estimate read/edit, restart and
> traceable re-export for Scope-only and populated packages, with no silent omissions
> or recalculation/canonical authority. Run focused service/HTTP/CSRF/permission/
> unsafe-archive/identity/rollback tests, affected capability/upload/report/migration
> regressions, Ruff/Mypy/Bandit/one migration head, plus real synthetic browser and
> ZIP inspection. Use worktree PYTHONPATH and unique no-cache test storage. Preserve
> the supplied logo. No customer data or real providers. Keep docs aligned; continue
> autonomously through implementation, validation, classification, explicit commit,
> normal push, PR and safe merge after required exact-head CI/reviews. Verify merge;
> report concrete blockers without bypassing them. Keep the full platform goal active.
