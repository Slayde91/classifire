# Excel defect-report review demo

This bounded synthetic demonstration extends the existing PDF/manual Draft Scope
workspace. It is human-selected mapping and review, not AI interpretation or a
production-approved physical model. Read [the contract](./DRAFT_SCOPE_XLSX_V1_CONTRACT.md)
and [PROJECT_STATE.md](./PROJECT_STATE.md) for current acceptance and limits.

## Isolated setup

Verified source worktree: `C:\CLASSIFIRE\.tmp\defect-xlsx-mapping-20260906`.
The new loopback demo is `http://127.0.0.1:8817/scopes`, using a separately marked
directory and named PostgreSQL database. Existing PDF 8816/pricing 8815 and older
demos are preserved. Verify live process/scanner availability before use.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py `
  --data-dir C:\CLASSIFIRE\.tmp\defect-xlsx-demo-20260906 `
  --port 8817 --postgres-demo-port 15432 `
  --postgres-demo-database classifire_draft_xlsx_report_demo --clamav-port 13311
```

The existing owned container exposes PostgreSQL only on loopback port 15432. The database
`classifire_draft_xlsx_report_demo` was created empty for this demo; directory/database
markers bind subsequent use. Do not point the launcher at project/customer data.
Its create_all setup proves only a disposable demo, not production migration readiness.
The separate destructive-test database is `classifire_containment_test`; never swap
it with the demo database or run overlapping destructive suites.

Genuine current ClamD is required for retained evidence. Preserve scan guards rather
than forcing a clean result. SQLite supports manual Drafts but cannot perform this
retained Excel workflow. The existing synthetic technical-library seed is restricted
to SQLite; do not bypass that restriction to make another report profile available.

Read synthetic login constants locally in the launcher. Keep credentials, cookies,
session markers and data out of logs/PRs/Git. Launch background helpers hidden and
write logs outside the initially empty data directory. Verify exact process command
lines before stopping only this demo. Reuse all flags for restart.

## User interaction

1. On **Draft scopes**, enter project details and choose **Upload Excel defect report**.
   From an existing Draft, choose **Excel defect report**. PDF upload remains a separate
   visible option.
2. Choose a supported synthetic XLSX, upload, then use **Scan Excel workbook**. Pending,
   unavailable, stale, infected or unsupported content cannot authorize mapping.
3. Choose the worksheet and header row. Map desired columns to the displayed fields;
   leave unavailable fields unmapped. Use the row controls to inspect later rows and
   select up to 25 rows. Choose Defect/Opening/Service kinds explicitly for each row.
4. Prepare the Draft batch. Inspect full selected cells beside the shared graph editor.
   Formula values are source text; ambiguous or missing measurements remain unresolved.
   Quantities distinguish blank/unknown from 0. Column mapping does not infer scale.
5. Edit the graph: explicitly connect services to shared openings, keep separate blank
   openings when appropriate, remove unwanted duplicates and add other supported items.
   Matching labels do not join records. Review each item's source-row links and choose
   any supporting picture occurrences. Spreadsheet placement alone is not evidence of
   an opening/service relationship.
6. Preview the entire graph and links. Return to editing if needed; confirm separately
   to save one revision. Permission, revision, source/scan and exact content are checked
   again. Confirmation expires after 15 minutes. Oversized selections are refused during
   preview; choose fewer rows/source links instead of increasing limits.
7. Reopen the saved Draft and inspect workbook references; download exact Scope v5 JSON.
   Generate a selected saved report or ProjectPackage explicitly. The ZIP inventories
   selected artifacts and external source claims; it does not contain the original
   workbook/image bytes or the complete project's history.
8. Later edits/deletion preserve the earlier claims and show review warnings. Re-review
   creates a new revision. Imports mark claims unverified and grant no source access.
9. Restart only the owned demo, sign in again and verify current/historical JSON, image
   previews, report pairs and package bytes. Current source scan rights still apply.

## Retained verification evidence

Real Chrome with genuine scanning passed 11 checkpoints on rows 15, 27 and 28 of a
synthetic register. The resulting graph included two services sharing one opening,
a separate blank opening, unknown and zero quantities, a withheld formula value and
six explicit source references. Two occurrences of identical image bytes retained
different anchors. Preview/edit-back/confirm saved v5; later edits/deletion preserved
historical review claims and downloads. No browser page errors were recorded.

After the final shared size helper was loaded, a fresh review confirmed revision 5.
A second actual process restart/fresh login preserved r2/r5 JSON, both image PNGs,
three report pairs and the selected ZIP byte-for-byte. Scope-only, Estimate-only and
Complete were exercised in the real demo. Scope+System is covered by focused synthetic
output tests because the guarded PostgreSQL demo has no technical release.

Receipts, synthetic fixture, screenshots and exact downloads are under
`C:\CLASSIFIRE\.tmp\defect-xlsx-review-artifacts-20260906`, including
`browser-receipt.json`, `final-code-review-receipt.json` and `restart-receipt.json`.
These are local verification evidence, not repository content or customer acceptance.
See PROJECT_STATE for final test/output inspection and publication results.
