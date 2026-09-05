# Manual Draft Scope prototype

CLASSIFIRE now has a working manual Draft Scope workspace in its existing UI.
You can create a project, describe its scope, validate, save, reopen and download
an exact saved revision. You can also import downloaded Scope JSON, review its
content and explicitly apply it as a new local revision. This guide runs both
workflows with isolated synthetic data.

## Start the local demo

Run these PowerShell commands from a **clean worktree containing this feature**,
using the existing CLASSIFIRE virtual environment with its dependencies installed:

```powershell
$taskDemoData = Join-Path $env:TEMP ('classifire-scope-demo-' + [guid]::NewGuid().ToString('N'))
C:\CLASSIFIRE\.venv\Scripts\python.exe .\scripts\run_draft_scope_demo.py --data-dir $taskDemoData --port 8797
```

Open [the local workspace](http://127.0.0.1:8797/scopes) while that command is
running. Port 8797 leaves room for an earlier P0 demo on 8796; use the port you
selected consistently. Sign in with this **synthetic demo account**:

- Email: `scope-demo@example.test`
- Password: `synthetic-scope-demo-only`

The launcher binds to `127.0.0.1`, creates a separate SQLite database and storage,
and prints its data directory. It does not load the root checkout's `.env` or
adopt an existing customer database. Enter only synthetic manual information.
An omitted `--data-dir` creates and prints a new temporary directory. A supplied
directory must be empty or already marked by this launcher; other existing data
is rejected. The URL is available only while you run the demo.

## Create and edit a manual scope

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

## Import, replace and continue editing

1. Download a saved Scope JSON file using the workflow above. Open the target
   draft and choose **Import Draft Scope JSON**. Save any current edits first.
2. Choose the downloaded file and select **Preview import**. Review the current
   and imported counts, complete scope content, relationships, uncertainties and
   source identity/checksums. Preview does not save a new revision.
3. Check the confirmation that this **replaces the whole Draft content** while
   keeping previous saved revisions, then select **Apply import as new revision**.
   Imported items are not merged with the current items. Cancel leaves them unapplied.
4. Inspect **Saved import history**, reopen the draft and download its new revision.
   The local user, target project and revision remain locally assigned. Names,
   authors and ancestry declared by the source remain unverified claims.
5. Edit an imported item and save again. Download that revision, then try importing
   it again. Manual edits retain source history; a re-import adds the supplied
   artifact to that history. Earlier saved JSON bytes remain unchanged.

Supported files are `CLASSIFIRE-DRAFT-SCOPE-v1` or `CLASSIFIRE-DRAFT-SCOPE-v2`, up to
**288 KiB (294,912 bytes)**. Existing v1 manual revisions retain their original
format. Import creates a v2 revision with `provenance: imported`; editing it creates
a v2 successor with `provenance: manual_edit`. Both remain Draft and unreviewed.

An imported revision supports at most **16 source-history records**. A file already
containing 16 records is refused because another import would exceed that limit;
history is not silently truncated. A preview expires after 15 minutes. If it expires
or the target changes, preview again. Unsupported versions, tampering, invalid
relationships and oversized files are refused without replacing saved content.

## Create a scope-only report

1. Save the Scope, then choose **Scope reports** from its editor.
2. Select a saved revision and choose **Preview revision**. Review the complete
   saved content; unsaved editor changes are excluded.
3. Choose **Create PDF and Excel report**. Open **Download PDF** and **Download Excel**.
   Both files preserve the same project labels and Scope snapshot.
4. Edit and save another Scope revision, then reopen the earlier report. It shows
   **Out of date**, while downloading either format returns the original bytes.
5. Restart the same isolated demo and reopen the saved report link. Verify both
   downloads again. The report list shows the newest 20; older saved links remain valid.

The dedicated PDF is the print layout. Excel has filterable sheets and separate
service/opening links; scroll horizontally on wider sheets. Known quantities are
numeric; missing quantities and technical/pricing facts remain unavailable. Neither
file grants approval or causes matching, pricing, AI or release to run.

## Review technical candidates with synthetic sources

Use a new empty/marked demo directory and opt into its labelled synthetic library:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe .\scripts\run_draft_scope_demo.py --data-dir C:\CLASSIFIRE\.tmp\my-candidate-demo --port 8799 --seed-technical-library
```

The fixture contains a real one-page PDF and two synthetic pipe records. Its seeded
approved/clean metadata is fixture setup, not a malware scan or technical approval.
It never adopts or overwrites an unrelated existing library. Use the same directory
and flag after restart; an altered fixture is refused instead of silently reseeded.

1. Create/save a synthetic Scope with service type `pipe`, a linked wall opening
   and substrate `masonry` or `concrete`. Leave unknown material, FRL and dimensions
   unknown. A cable-only query can correctly return no records from this tiny library.
2. Choose **System candidate review**, a saved Scope revision, release
   `SYNTHETIC-P2A-001` and an opening, service or actual linked pair.
3. Choose **Find and save candidates**. Read the selected target, unassessed items,
   missing criteria, captured source references and text comparisons. Open current
   document/variant metadata if useful; these links are not source-file viewers.
4. Set **Keep for review** or **Reject from this review**, enter reasons and choose
   **Save new review revision**. These are unapproved preferences, never applicability.
5. Reopen and **Download saved candidate review JSON**. Use the historical revision
   selector to confirm earlier decisions/bytes remain unchanged.
6. Edit/save the Scope and return to the review: **Out of date** explains the changed
   dependency. A new retrieval creates a separate review; saving notes does not
   refresh candidates or remove staleness. Restart and compare the same download.

Only one target is assessed for retrieval per review, with at most 20 candidates.
The artifact preserves the full Scope context and remaining unassessed item IDs.
No Estimate, provider, canonical physical write, lock or operational release runs.

## Check persistence after restart

To verify persistence, stop the server with `Ctrl+C` and run the same command
again using the same `--data-dir`. In a new terminal, use the directory path
printed on the first run. Reopen the draft and download the same saved revision;
the downloaded bytes should match the earlier file.

## Verified demonstrations

The P0 synthetic Chrome demonstration on 2026-09-05 exercised create, edit, validate,
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

The P1a Chrome demonstration on the same date exercised preview, explicit import,
manual edits, v2 re-import and tampered-file refusal. It restarted the actual server
and downloaded revision 5 again. Browser/restart receipts both recorded `PASS` with
no page errors. The resulting revision retained two source-history records.

Its final, post-refusal and post-restart JSON files have identical bytes and file
SHA-256 `ef77991ef46955ae917e0a252ff19651ee8a3251f2d018c66fff6f759f437442`.
The embedded envelope hash is
`dd930c4e1ab0861fce9551c556f1ccc4bc076dce598ac1e541eb1359017f840e`.
The isolated database contained one Draft and five revisions, with zero canonical
defects, openings, services, service links, estimates or Physical Model Locks.
P1a screenshots, receipts and synthetic downloads are retained locally under
`C:\CLASSIFIRE\.tmp\draft-scope-import-artifacts`; none belong in Git.

The P4a final Chrome demonstration created a report from imported Scope revision 2,
saved a later revision 3 and showed the retained report as out of date. Both files
remained byte-identical after the later edit and an actual server restart. Browser
and restart receipts reported `PASS` with no page errors.

- PDF SHA-256: `1ed6dbd5f4beda3f720b8095e265bc4899891f2b84c20a0e550fb812c37e6cde`.
- XLSX SHA-256: `c20f1e826854f8fb17424c5376dc5d171ffddc91384c0c21be2b1abb6e480dc8`.
- Report snapshot SHA-256: `4a331ad21e131eeae4802176f893c3890b6f94604de1b28e173d698852c679fc`.
- Final saved report: `http://127.0.0.1:8798/scopes/b4d57d5e-67d1-4507-942f-6f13bb895a67/reports/8db56993-c17a-4155-9f3c-2d7f321da16f` (local synthetic server on port 8798).

The report retains three imported-source history records, all unverified claims.
Its three PDF pages were inspected; independent standard/long-text fixtures added
seven inspected PDF pages with hostile literal text. All nine workbook sheets were
opened read-only in native Excel with macros/events disabled and rendered for visual
review. Workbook cells, numeric types, filters, relationships and absent formulas/
hyperlinks were also checked programmatically. A duplicated workbook title and
oversized PDF logo found during verification were fixed before the final demonstration.

The report demo contains four synthetic Drafts, 11 revisions and three reports from
the verification runs, with zero canonical defects/openings/services/links/estimates
or Physical Model Locks. It lives at `.tmp/draft-scope-report-demo-20260905`; receipts,
screenshots and downloads are in `.tmp/draft-scope-report-artifacts`. Additional
standard/long-text fixtures are in `.tmp/draft-scope-report-output-qa`. These are local
synthetic artifacts, excluded from the PR. The launcher can run this increment with
`--data-dir C:\CLASSIFIRE\.tmp\draft-scope-report-demo-20260905 --port 8798`.

## Boundaries and remaining work

- Scope JSON import/export is implemented for the supported v1/v2 contracts.
  Complete ProjectPackage ZIP generation/import, source-file intake, AI analysis,
  matching, pricing and additional report profiles remain outside this workflow.
  Scope-only Draft PDF/XLSX reporting and bounded P2a candidate review are implemented;
  P3a manual Draft estimating is next after current validation/publication.
- Saved revisions remain Draft and unreviewed. They do not create canonical
  physical-model records, approvals, locks or human releases.
- Draft content is restricted to its owner and administrators. Surrounding
  project metadata retains the application's existing shared project visibility;
  this prototype does not establish tenant isolation.
- This isolated SQLite demonstration proves a usable prototype, not production
  deployment, production database migration readiness or completion of all four
  independent capabilities. Continue with the next visible increment in the
  [roadmap](CLASSIFIRE_ROADMAP.md).
