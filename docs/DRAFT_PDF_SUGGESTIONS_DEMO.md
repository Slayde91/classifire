# Optional PDF suggestion prototype demonstration

This is a synthetic workflow demonstration, not a live AI accuracy result.
The configured OpenAI transport remains disabled. The scripted demo only accepts
its exact generated PDF page text and image and is clearly labelled in the UI.

## Existing verified demonstration

URL: `http://127.0.0.1:8818/scopes`.
Data: `C:\CLASSIFIRE\.tmp\draft-pdf-suggestions-demo-20260906`.
Database: `classifire_draft_suggestions_demo`, loopback PostgreSQL15432.
Scanner: the existing local ClamAV service on13311. Verify current availability.

The guarded launcher is `scripts/run_draft_scope_demo.py`; it creates the fixture
`synthetic-suggestion-report.pdf` in the marked data directory. Use its synthetic
login constants locally; never paste operational credentials into documentation.
The launch arguments for this separately owned demonstration are:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe -B scripts/run_draft_scope_demo.py --data-dir C:\CLASSIFIRE\.tmp\draft-pdf-suggestions-demo-20260906 --port 8818 --postgres-demo-port 15432 --postgres-demo-database classifire_draft_suggestions_demo --clamav-port 13311 --scripted-pdf-suggestions
```

Do not launch a second process on an occupied port. Verify exact command lines and
markers before restarting only this demonstration; keep earlier demos untouched.
The database must already be the explicitly owned empty/marked synthetic database.
The launcher refuses an unmarked nonempty database or unrelated data directory.

## Interaction and measured result

Create a Draft, choose PDF defect report, upload the exact synthetic fixture and
scan it. Open the retained page, confirm the labelled scripted request and load
suggestions. Review the source alongside one defect, one shared opening, pipe and
cable groups, and an unresolved question. Dimensions and quantities remain unknown.
Edit a service label, select each kept item for page review, preview, return to edit
and separately confirm. The saved v6 artifact keeps the original proposal as well
as human-reviewed values. A second batch can be explicitly rejected without saving
Scope. Reopen either retained batch from the PDF source page.

Chrome completed this interaction, three PDF/XLSX report profiles and selected ZIP
download. A real process restart and fresh login preserved Scope JSON, page PNG,
all six report files, ZIP and applied/rejected history. Read-only database checks
found no canonical Estimate/Defect/Opening/Service/evidence/link/lock records.
Representative UI/PDF views and one native read-only Excel provenance range were
inspected. A separate artifact-tool native module failed to load; no dependency
was changed and native Excel provided the representative range inspection.

Receipts and exact local downloads are under
`C:\CLASSIFIRE\.tmp\draft-pdf-suggestions-review-artifacts-20260906`:
`browser-receipt.json`, `restart-receipt.json`, `process-restart.json`,
`output-inspection.json`, `visual-inspection.json` and `database-counts.json`.
They are synthetic local proof, not files to commit. Scope+System v6 is covered by
pure report tests; this PostgreSQL demo has no technical release.

See [PROJECT_STATE.md](./PROJECT_STATE.md) for current tests/publication and the
[contract](./DRAFT_PDF_SUGGESTIONS_V1_CONTRACT.md) for exact limits. Live model quality,
latency/cost, customer evidence and production deployment remain unverified.
