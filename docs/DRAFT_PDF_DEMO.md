# Synthetic PDF defect-report review demo

The standalone UI supports retained PDF page review and editable Defect/Opening/
Service graphs. Interpretation is manual; extracted text remains unreviewed. Use
synthetic evidence for this demo. Operational uploads, canonical physical writes,
provider execution, deployment, locks and release require their own authorization.

## Prerequisites and current isolated setup

Use the verified isolated worktree and existing `.[dev,postgres]` dependencies,
PostgreSQL 16 and a trusted ClamD daemon with genuine current definitions. Inspect
existing names/ports and marked directories; do not overwrite earlier environments.

The 2026-09-06 graph-review proof uses:

- Source worktree: `C:\CLASSIFIRE\.tmp\defect-report-review-20260906`.
- UI: `http://127.0.0.1:8816/scopes`.
- Data: `C:\CLASSIFIRE\.tmp\defect-report-demo-20260906`.
- PostgreSQL: `classifire-pdf-intake-20260906-pg` on loopback 15432, separate
  `classifire_draft_defect_report_demo` database, user `classifire_test`.
- Scanner: separate native `classifire-client-pricing-20260906-av` daemon on loopback
  13311. VERSION during proof: ClamAV 1.4.4, database 28115, published 2026-09-06 UTC.
  Recheck freshness; a historical successful scan is not current viewing authority.
- `classifire_containment_test` is the separate destructive-test-only database.
  Never swap it with the browser database or run overlapping destructive fixtures.

This loopback trust-authenticated database is a synthetic development convenience,
not production authentication. On a fresh machine create a separately named empty
allowed demo database and configure genuine scanning; never adopt project data.
The launcher checks both directory and database markers, refuses unmarked nonempty
state and uses create_all only for the disposable demo. It does not prove migration
readiness. Without PostgreSQL flags the existing manual-only SQLite demo remains.

From the verified source worktree, reuse these exact storage/database flags for restart:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py `
  --data-dir C:\CLASSIFIRE\.tmp\defect-report-demo-20260906 `
  --port 8816 --postgres-demo-port 15432 `
  --postgres-demo-database classifire_draft_defect_report_demo --clamav-port 13311
```

Read the existing synthetic login constants locally in the launcher; do not copy
credentials, session markers/cookies or databases into handoffs, logs or Git. Start
background helpers hidden. Before stopping a process verify its exact command line
belongs to this demo. Preserve 8815 and all older demos/scanners.

## User interaction

1. On Draft Scopes, enter the project name and choose **Upload PDF defect report**, or
   open a saved Draft and use its upload button. PostgreSQL mode is required; SQLite
   displays an explicit evidence-setup message.
2. Retain one synthetic PDF (maximum 10 MiB/50 pages), then choose **Scan and prepare
   PDF pages**. Pending/failed/stale/unavailable/infected scanning cannot authorize
   viewing. Correct infrastructure, never force a clean verdict.
3. Open a page. Inspect the raster beside the existing graph editor. Add/edit a
   defect, openings and services; explicitly connect shared-opening services. A
   blank opening may have no service. Leave unknown dimensions and quantities blank.
4. Tick **Link this item to page N** only for the items reviewed against this page.
   Nothing is preselected. Whole-item references record that review; they do not
   confirm every field, technical suitability or canonical physical truth.
5. Preview the entire edited graph and selected links. Return to editing if needed,
   or explicitly confirm and save one Draft revision. Confirmation expires after
   15 minutes and rechecks source/scan/revision/session and exact submitted content.
   If a source becomes unavailable, submitted work is shown as escaped recovery data
   without an enabled save action. Reopen/review current source before retrying.
6. Existing page observations are available separately. Save or abandon pending graph
   edits before using that form; the UI prevents silently stranding unsaved graph work.
7. Reopen the Draft, inspect page references and download the Scope v4 JSON. Generate
   the desired saved report profile and/or a selected Scope package. The package
   contains selected artifacts and a manifest, not the original PDF or complete history.
8. A later graph change or item deletion retains the old reference and shows a warning.
   Re-review explicitly to update a new revision. Earlier revision/report/package bytes
   remain unchanged. Import into a new Draft retains unverified claims and grants no
   source access or approval.
9. Restart only this demo with the same flags, log in again, reopen the source and
   compare historical/current downloads. Scanner freshness still applies after restart.

## Verified graph-review evidence: 2026-09-06

Real Chrome and the real fresh scanner passed 11 checkpoints with zero browser page
errors. A two-page synthetic report produced one defect, two openings (one blank),
two services sharing the first opening, one existing observation and six retained
references at Scope r4. Dimensions/quantities remained unknown. Later r5/r6 edits
changed a label and removed a service; both warnings remained visible.

Scope-only, Estimate-only and Complete reports generated six actual PDF/XLSX files.
Their rendered pages and workbook cells were inspected. Scope+System was deliberately
not exercised in this browser run because no technical release was available; focused
synthetic output tests cover that fourth profile. No technical authority was invented.
A selected Scope package exported correctly. Actual process restart/fresh login
preserved r4/r6 JSON, both page PNGs, three report pairs and ZIP hashes exactly.
Read-only database counts after the journey: canonical Estimate, EstimateLine, Opening,
Service and PhysicalModelLock were all zero.

Local artifacts: `C:\CLASSIFIRE\.tmp\defect-report-review-artifacts-20260906`, including
`browser-receipt.json`, `restart-receipt.json`, screenshots, exact downloads and the
synthetic source. These are local verification evidence, not customer evidence or
production proof. Final automated checks/publication are recorded in PROJECT_STATE
and the live PR; no deployment or Phase 8 exit is implied.

## Historical observation-only proof

The earlier v3 demo used port 8803, `classifire_draft_pdf_demo`,
`.tmp/draft-pdf-demo-20260906` and scanner 13310. Its artifacts remain under
`.tmp/draft-pdf-artifacts`; preserve them. That run proved observation save/restart
and later-edit warnings. Its scanner database date was 2026-08-30 and is historical;
do not assume it remains fresh. Existing v1-v3 Scope and report readers stay compatible.

See [the evidence contract](./DRAFT_PDF_EVIDENCE_V1_CONTRACT.md) for exact bounds and
remaining gaps. The Excel defect-mapping companion is documented in [DRAFT_SCOPE_XLSX_DEMO.md](./DRAFT_SCOPE_XLSX_DEMO.md). Optional image/text proposals remain planned; production technical applicability, pricing and Human Release remain separate.
