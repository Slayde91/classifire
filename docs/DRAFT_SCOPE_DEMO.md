# Manual Draft Scope prototype

CLASSIFIRE now has a working manual Draft Scope workspace in its existing UI.
You can create a project, describe its scope, validate, save, reopen and download
an exact saved revision. This guide runs it with isolated synthetic data.

## Start the local demo

Run these PowerShell commands from a **clean worktree containing this feature**,
using the existing CLASSIFIRE virtual environment with its dependencies installed:

```powershell
$taskDemoData = Join-Path $env:TEMP ('classifire-scope-demo-' + [guid]::NewGuid().ToString('N'))
C:\CLASSIFIRE\.venv\Scripts\python.exe .\scripts\run_draft_scope_demo.py --data-dir $taskDemoData --port 8796
```

Open [the local workspace](http://127.0.0.1:8796/scopes) while that command is
running. Sign in with this **synthetic demo account**:

- Email: `scope-demo@example.test`
- Password: `synthetic-scope-demo-only`

The launcher binds to `127.0.0.1`, creates a separate SQLite database and storage,
and prints its data directory. It does not load the root checkout's `.env` or
adopt an existing customer database. Enter only synthetic manual information.
An omitted `--data-dir` creates and prints a new temporary directory. A supplied
directory must be empty or already marked by this launcher; other existing data
is rejected. The URL is available only while you run the demo.

## Try the workflow

1. Create a Draft Scope with a project reference and name. This saves revision 1.
2. Add one defect, then several openings linked to it. Set each opening's plane,
   substrate and dimensions when known. Leave unknown dimensions blank.
3. Add services and select their linked openings. Try two services sharing one
   opening and one service passing through two openings. A blank opening must
   have no linked services. Leave an unknown quantity blank; it stays unknown.
4. Add an **Unresolved** observation, assumptions and exclusions. Selecting an
   evidence state records your draft statement; it does not establish approval.
5. Choose **Validate draft**. Review the findings. Validation does not save a new
   revision, run AI, choose a system or calculate an estimate.
6. Choose **Save new revision**. Unresolved information remains visible in the
   saved Draft. Invalid relationships or malformed values must be corrected.
7. Return to **All drafts**, reopen the project and check the values. Choose
   **Download saved Draft Scope JSON** to download that exact saved revision.
   After further edits, save again before downloading the changed content.

To verify persistence, stop the server with `Ctrl+C` and run the same command
again using the same `--data-dir`. In a new terminal, use the directory path
printed on the first run. Reopen the draft and download the same saved revision;
the downloaded bytes should match the earlier file.

## What this prototype proves

The synthetic Chrome demonstration on 2026-09-05 exercised create, edit, validate,
save, reopen and download, then restarted the actual server and downloaded again.
Its saved revision contained one defect, three openings, two services and one
unresolved observation, including a blank opening, shared relationships and an
unknown quantity. The browser receipts recorded no page errors; the saved view
and service controls were visually inspected.

The original and post-restart JSON files had identical bytes and file SHA-256
`551221821649d33a78b0a2e8a8fa427a0b7e60819b8c0199605351c2edc04f4e`.
The artifact's embedded envelope hash was
`4f49cae3c03733a29df87342ac3fd409c9ab3f839aca3d93e5cd3e96c42e7fc5`;
these hashes cover different representations. Screenshots, receipts and synthetic
files were retained locally under `C:\CLASSIFIRE\.tmp\draft-scope-demo-artifacts`,
not committed as customer or repository data.

## Boundaries and remaining work

- This is `CLASSIFIRE-DRAFT-SCOPE-v1` JSON, not a complete ProjectPackage ZIP.
  Package import, source-file intake, AI analysis, matching, pricing and PDF/XLSX
  reporting are not part of this manual workflow.
- Saved revisions remain Draft and unreviewed. They do not create canonical
  physical-model records, approvals, locks or human releases.
- Draft content is restricted to its owner and administrators. Surrounding
  project metadata retains the application's existing shared project visibility;
  this prototype does not establish tenant isolation.
- This isolated SQLite demonstration proves a usable prototype, not production
  deployment, production database migration readiness or completion of all four
  independent capabilities. Continue with the next visible increment in the
  [roadmap](CLASSIFIRE_ROADMAP.md).
