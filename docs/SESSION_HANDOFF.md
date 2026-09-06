# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06. Worktree `C:\CLASSIFIRE\.tmp\defect-report-review-20260906`, branch
`feat/defect-report-review-20260906`, baseline main
`080845e2681e292cabb6f201f373a696d1fc40c1` (PR #208). Baseline feature CI passed
1,522 tests and required static checks. Inspect live head/upstream, PR/CI and merge
state before continuing; a document cannot include its own final commit hash.
ADRs 0001/0002 remain accepted. The full production goal remains incomplete.

## Current increment and verification

This increment makes PDF defect-report upload visible and reuses the existing Scope
graph editor beside the retained page. A person edits defects/openings/services,
explicitly links selected items, previews, edits back if needed and confirms one
atomic Draft revision. It adds v4 entity references to the same `evidence_refs` union;
old observation refs and historical downloads remain readable. Changed/deleted items
retain warnings. Imports retain unverified claims. Four report profiles support the
new references and preserve old render versions. Package inventory already consumes
the same array; exporting a selected Scope does not bundle original PDF bytes.

No AI/OCR interpretation, Excel defect ingestion, new canonical writer, dependency,
migration, provider call, deployment or release is added. SQLite still supports manual
Drafts; retained evidence requires the existing guarded PostgreSQL/storage/scanner setup.

Changed components: draft_pdf_intake, draft_scope/evidence services, PDF/Scope routers,
shared editor/preview templates and JS/CSS, report renderers/services/template globals,
demo database allowlist and three focused test modules. Documentation aligns GOAL,
AGENTS, architecture 5.22, roadmap, PDF contract/demo and retained corpus/pricing design.
Final relevant PDF/Scope/report/package/client regression: **264 passed**, no skips,
one expected malformed-ZIP warning, in 1,308.86 seconds. Full PR CI/review and merge
remain publication checks; verify their live result before moving to the next task.

Browser proof passed 11 checkpoints with no page errors, including shared opening/two
services, a separate blank opening and explicit unknown dimensions/quantities. Three
real PDF/XLSX profiles and package export worked; no technical release was seeded,
so Scope+System is covered by synthetic output tests rather than this browser run.
After real restart/fresh login, current/historical Scope JSON, both page images,
three report pairs and ZIP hashes matched. Changed/deleted item warnings remained.
Actual report images and workbook cells were inspected. Ruff/Bandit and Mypy (193
files, existing isolated reportlab/yaml stubs) passed. Alembic still has head 0037.
Two earlier tests failed in PDF fixture setup; both passed unchanged on rerun.

## Preserved local changes and runtime context

Never work from or repair the conflicted recovery root `C:\CLASSIFIRE`. It remains on
`gpt/phase8-linked-original-images`, with 46 unstaged tracked modifications, 14 staged
additions and four DU conflicts at task start. Untracked/ignored recovery material
was not exhaustively enumerated. Preserve all unrelated changes, worktrees, earlier
demos/receipts/scanners and the supplied logo; no broad staging/reset/cleanup.

New synthetic demo: `http://127.0.0.1:8816/scopes`, marked data directory
`C:\CLASSIFIRE\.tmp\defect-report-demo-20260906`, separate PostgreSQL database
`classifire_draft_defect_report_demo` on loopback 15432, current ClamD port 13311.
Owned launcher was restarted during proof. Verify exact live process command line
before stopping/restarting only this demo; start helpers hidden. Do not assume ports,
process IDs or scanner freshness remain current. Read launcher login setup locally;
do not copy credentials, session markers or bearer tokens into handoffs/PRs/logs.
See DRAFT_PDF_DEMO.md. Existing 8815 and older demos remain separate and preserved.

Receipts in `C:\CLASSIFIRE\.tmp\defect-report-review-artifacts-20260906` include
`browser-receipt.json`, `restart-receipt.json`, saved v4/r6 JSON, PDF/XLSX/ZIP files and
screenshots. They are synthetic local artifacts, not Git content or production proof.
The separate destructive-test database is `classifire_containment_test`; verify it is
owned, idle and isolated before using its cleanup opt-in. Never use a demo/customer
DB for these tests. No operational canonical records or locks were created.

## Start Here / Next Session

**First task:** implement one bounded **Excel defect-report mapping** interaction
feeding the existing Draft Scope graph. This is the next missing upload format after
the PDF review slice. The existing Excel UI applies prices inside an Estimate and
cannot serve as a defect-register importer. A/B pricing remains a separate track.

**Prerequisites:** verify this PDF change has merged with passing required CI/review;
otherwise finish its validation/publication first. Inspect current source/Git/docs
before edits and use an isolated current-main worktree. Reuse source retention,
scanner containment, bounded workbook parsing and the existing graph editor/save
boundary. Synthetic fixtures suffice; real-layout acceptance needs authorized sample
files. Genuine current scanning and disposable PostgreSQL/marked storage are required
for browser proof. Do not weaken guards if infrastructure is unavailable.

**Files/components:** docs/DRAFT_PDF_EVIDENCE_V1_CONTRACT.md, DRAFT_PRICING_XLSX.md,
services/draft_source_intake.py, draft_pdf_intake.py, draft_scope.py,
draft_scope_evidence.py, draft_pricing_intake.py, draft_pricing_worker.py,
draft_pricing_contract.py, PDF/Scope routers and shared editor. Inspect existing
models/migrations/tests before deciding the smallest compatible XLSX source/cell
reference contract. PDF page references must not be relabelled as spreadsheet cells;
preserve old schema/readers and append versioned semantics only where necessary.

**Definition of done:** a user uploads/scans a synthetic XLSX defect register, inspects
supported sheets/headers/rows, maps selected columns into editable Draft items, reviews
source cells and unknowns, explicitly resolves any shared-opening relationship and
confirms one saved revision. Reopen after restart and verify provenance/history and
selected export/import. Mapping is human-selected; no AI, product/rate application,
technical approval or canonical writes. Preserve blank/unknown versus zero, reject
ambiguous/malformed values visibly, and show unsupported/over-limit content without
silent truncation. Do not assume one row/defect equals one service/opening/quantity.
Handle duplicate confirmation, stale source/scan/revision, permissions and cross-user
access. Avoid speculative bulk infrastructure or full corpus/AI work.

**Validation commands:** inspect current fixture names/configuration first. Force
imports to the isolated worktree; use a unique temporary output directory. Run guarded
PostgreSQL suites serially only against the verified disposable test database and its
existing explicit cleanup opt-in. Add focused mapping/cell provenance/refusal tests,
then run relevant retained-source/PDF/Scope/package/report/client regressions:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$mappingTestTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('defect-mapping-tests-' + [guid]::NewGuid())
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $mappingTestTemp tests/test_draft_pdf_scope_review.py tests/test_draft_pdf_intake.py tests/test_draft_pricing.py tests/test_draft_scope.py tests/test_draft_package_import.py tests/test_draft_entity_evidence_outputs.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Add meaningful UI/worker/migration regression where the chosen implementation changes
those boundaries. Inspect rendered UI/outputs and demonstrate actual restart; report
skips honestly. Required PR CI is `.github/workflows/pull-request-validation.yml`.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, read AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/CLASSIFIRE_ROADMAP.md and docs/SESSION_HANDOFF.md; reconcile Git/worktrees,
> current main and PR/CI. Preserve the conflicted C:\CLASSIFIRE root, unrelated changes,
> demos/receipts and approved logo; use an isolated current-main worktree. Finish any
> pending PDF graph-review publication first. Then implement only the next bounded
> Excel defect-report mapping UI: PDF now has human page-linked graph review, while
> existing Excel intake handles prices and cannot build a defect register. Reuse
> draft_source_intake, the bounded workbook worker, Draft Scope services and shared
> editor; inspect the PDF evidence and pricing XLSX contracts, models and tests before
> extending source/cell provenance compatibly. Upload/scan a synthetic XLSX, show its
> sheets/headers/rows, let the person map columns and review editable defects/openings/
> services plus exact source cells/unknowns, then explicitly confirm one atomic revision.
> Preserve blanks versus zero, shared-opening decisions, historical bytes and unverified
> import claims; never infer quantity from defect count. Reopen after actual restart
> and verify export/import. No AI, pricing/system approval or canonical writes. Real
> layouts require authorized samples; synthetic implementation is unblocked. Use marked
> storage, current scanner definitions and verified disposable PostgreSQL; never weaken
> guards. Add focused mapping, provenance, stale-input, permission and replay tests;
> run relevant PDF/Scope/pricing/package/report/client regressions, browser/restart,
> Ruff/Mypy/Bandit/migration checks and required CI. Align documentation, classify local
> changes and continue autonomously through explicit-path commit, normal push, PR and
> merge once required checks/reviews pass; verify the merge. Avoid speculative bulk
> infrastructure/model work and preserve human-only release; do not deploy or release.
