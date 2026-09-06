# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06 AEST. Worktree `C:\CLASSIFIRE\.tmp\client-workbook-pricing-20260906`;
branch `feat/client-workbook-pricing-20260906`. Verified base/shared main:
`58c7d4aefad87d714a8922d060fbfa2e68b446bb`, merged PR #206. Feature
`bce35c5e981317bf2e2e9ea5063e55780b2754c7` passed PR CI 34015890493 attempt 2
(1,511 tests); main CI 34017405923 succeeded. The unchanged retry followed a worker
timeout; no test/assertion/timeout was weakened.

ADRs 0001/0002 remain accepted; the production goal is active and incomplete.
This is the workbook-pricing implementation checkpoint. Inspect current head/upstream,
PR/checks and local publication receipt before editing; this file is not merge or
deployment evidence.

## Current change and validation

Two read tools discover/preview owned retained XLSX sources. A strict
`apply_workbook_rate` proposal binds the saved Estimate/line, source/document/scan/row,
explicit mapping and recovery note. Only separate same-human browser confirmation
calls the shared writer. Current owner/client/domain/library rights and source checks
remain. Old manual request hashes survive; original rates, exact source cells,
unapproved selection and later overrides are retained.

Changed components under `src/classifire`: `draft_client_capability_tools.py`,
`services/draft_client_capabilities.py`, `services/draft_client_requests.py`,
`templates/draft_client_request.html`, `templates/draft_pricing.html` and shared
`templates/draft_pricing_row_content.html`. Also: `tests/test_draft_client.py`,
new `tests/test_draft_client_pricing.py`, one demo database choice in
`scripts/run_draft_scope_demo.py`, GOAL and aligned documentation. No migration,
dependency, OAuth scope, pricing rule or canonical authority changed. AGENTS.md
was inspected and needs no instruction change.

Pricing regression: 26 passed. Additional permission plus client/Estimate/report
regression: 161 passed. Total **187 passed**, including PostgreSQL concurrency;
no skips. Ruff/Bandit passed; Mypy passed 193 files. Single unchanged migration head:
`0037_draft_client_capabilities`. The initial discovery assertion omitted the two
new tools; its updated exact set passes. No safety assertion was weakened.

Official SDK + Chrome passed source discovery/mapping, actual clean scan, visible
same-human reject/confirm, original/override history, four exact PDF/XLSX downloads
and supplied-logo parity. Actual process restart retained Estimate revisions 3/4,
rejection and all four files. The initial restart harness expected a source cell in
collapsed details; opening the actual disclosure made the unchanged D2 assertion
pass. No application change was needed. PDF text (seven pages), workbook cell/types
and the PDF source/history page were inspected. The actual pending source-review
panel and current Estimate/logo viewport were visually inspected. Synthetic canonical counts remained
zero for estimates, lines, openings, services and Physical Model Locks.

Retained receipts under `C:\CLASSIFIRE\.tmp`: `client-pricing-browser-receipt.json`,
`client-pricing-restart-receipt.json`, `client-pricing-output-inspection.json`, generated
`client-pricing-*.pdf/.xlsx` and screenshots. The browser receipt records the reused
original Draft `0ddd4d8e-e06d-4ec3-98f9-cae15ab8f0e6`, Estimate
`c030c7fa-a594-4fc0-b5fd-039bd15c3a81` and workbook source
`ae0f8584-c05c-4895-a65c-8b49d69b02a1`. The recovery helper is
`scope-browser-test-tools/client-pricing-resume.cjs`; do not blindly replay its
revision-2 setup over the now revision-4 Estimate. Restart verification is separate.

## Local environment and preserved work

Demo: `http://127.0.0.1:8815/scopes`, marked directory
`C:\CLASSIFIRE\.tmp\client-pricing-demo-20260906`, separate database
`classifire_draft_client_pricing_demo` on loopback 15432. Read synthetic login setup
from the local demo launcher; do not copy its login values or bearer token into docs.
The token expires after 15 minutes; restart refreshes it. Never print/paste/commit it.

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py --port 8815 --data-dir C:\CLASSIFIRE\.tmp\client-pricing-demo-20260906 --client-demo --postgres-demo-port 15432 --postgres-demo-database classifire_draft_client_pricing_demo --clamav-port 13311
```

The separate test database `classifire_containment_test` was verified empty/idle
before guarded serial fixture execution; it is never the demo database. The new
`classifire-client-pricing-20260906-av` scanner uses native Alpine on loopback 13311.
Its genuine daily 28115 was published 2026-09-06T06:26:06Z. Alpine's engine 1.4.4
warns that 1.4.6 is recommended; this disposable setup is not a production deployment.
Earlier scanner 13310 and all earlier demo data remain untouched. See local scanner
configuration/process evidence before restarting its independently launched ClamD.

Local helpers: `.tmp/client-pricing-probe.py` and
`.tmp/scope-browser-test-tools/client-pricing-check.cjs`. Receipts/screenshots/reports
stay under `.tmp` outside this commit, including the failed scan attempt. Verify exact
process command lines before stopping only owned demos; launch background processes
hidden. Preserve prior demos, worktrees and receipts.

The root remains unrelated recovery work on `gpt/phase8-linked-original-images`,
with four DU conflicts plus pre-existing staged/unstaged changes verified read-only.
Never reset, clean, resolve, broad-stage or publish that checkout. The supplied
`src/classifire/static/brand/classifire-logo.png` matches the root PNG and stays unchanged.

## Start Here / Next Session

**First task:** verify/finalize this increment's publication, then build one
source-linked structured Draft interaction from a retained PDF page. Current PDF
review saves observations but cannot bind reviewed Defect/Opening/Service facts to
that page. The existing graph/editor works; do not rebuild it or require AI first.

**Files/components:** `draft_pdf_ui.py`, `services/draft_pdf_intake.py` (`_document`,
`review_page`, staleness), `services/draft_scope_evidence.py`, `services/draft_scope.py`
(`validate_payload`, `_append_revision`), `draft_scope_ui.py`, `static/draft_scope.js`,
Scope/report templates, Scope import and ProjectPackage validation/materialization.
Read current contracts in `docs` before choosing the versioned provenance extension.

**Prerequisites/blockers:** current main, `.[dev,postgres,chatgpt]`, an owned retained
synthetic PDF, marked storage, genuinely current scanner definitions and guarded
isolated PostgreSQL. Verify the test database is empty/idle before its cleanup opt-in.
Never use demo/customer data for destructive fixtures. Missing isolation/scanning
blocks runtime proof, not source inspection. No provider, real OAuth or deployment
is required. The entity/page contract is a bounded decision inside approved ADRs.

**Definition of done:** inspect one page, edit a bounded linked graph with separate
entities and explicit uncertainty, preview without writes, then confirm one atomic
Draft revision. Add the smallest compatible entity/page binding and meaningful
staleness after changed/deleted facts; preserve v1-v3 history and imported-unverified
claims. Recheck source/scan/document/page identity, rights/ownership and expected
revision on save. Reopen after actual restart; inspect JSON, Scope PDF/XLSX and
package round trip with intact graph/provenance and prior revisions. No invented
quantity, canonical writes or automatic matching/pricing. Align docs and safely publish.

**Validation:** focused new provenance tests and current Scope/editor/import,
PDF intake/UI, Scope reports and package/materialization regression. Recheck test
configuration before using:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_scope.py tests/test_draft_scope_ui.py tests/test_draft_scope_import.py tests/test_draft_pdf_intake.py tests/test_draft_pdf_ui.py tests/test_draft_scope_reports.py tests/test_draft_project_packages.py tests/test_draft_package_import.py tests/test_draft_package_materialization.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Run PostgreSQL suites serially with the documented test URL/cleanup opt-in and record
skips. Local Mypy stubs have been at
`C:\Users\tanas\AppData\Local\Temp\lifecycle-stubs-9f7cfd6c36c84af0b5b19c5f3dcf36c7`
appended to PYTHONPATH; verify availability. Demonstrate Chrome/save/restart/download
and inspect outputs. Required CI/reviews must pass on the PR head.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from repository evidence. Before editing, read AGENTS.md,
> GOAL.md and docs/PROJECT_STATE.md, CLASSIFIRE_ROADMAP.md, CLASSIFIRE_ARCHITECTURE.md
> and SESSION_HANDOFF.md; inspect Git/worktrees, main, current PR/CI and local changes.
> Finalize any outstanding client-workbook-pricing publication, then use an isolated
> current-main worktree. Preserve the conflicted root, unrelated work, receipts and logo.
> The single next task is a source-linked structured Draft workflow from one retained
> PDF page: inspect, edit separate linked Defects/Openings/Services, preview, confirm,
> reopen and export. It is next because PDF provenance currently binds only observations,
> while the graph/editor already works. Reuse draft_pdf_ui, draft_pdf_intake,
> draft_scope_evidence, draft_scope, draft_scope_ui, draft_scope.js and existing
> report/import/package services. Define the smallest compatible versioned entity/page
> binding; preserve v1-v3 history, imported-unverified claims and staleness after edits.
> Recheck source/scan/page integrity, rights/ownership and expected revision; unknown
> facts stay unknown. Use synthetic evidence, marked storage, verified disposable
> PostgreSQL and genuinely current scanner definitions. Missing isolation/scanning
> blocks runtime proof; never weaken guards or substitute customer data. Done means
> one atomic save, denied stale/foreign/changed-source requests, intact graph/provenance
> after restart, readable JSON/Scope PDF/XLSX and package round trip, with no canonical
> writes or automatic matching/pricing. Run focused Scope/editor/import/PDF/report/
> package tests, actual browser/restart/output checks, Ruff/Mypy/Bandit/migrations and
> required CI. Align docs, classify changes and continue autonomously through explicit-
> path commit, normal push, PR and merge after required checks/reviews pass; verify
> the merge. Keep AI optional, avoid speculative work, and do not deploy or release.
