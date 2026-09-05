# Synthetic PDF evidence review demo

This first P1b path uses the existing standalone UI and deterministic backend.
Use synthetic evidence only. It does not authorize customer uploads, operational
migrations, provider calls, deployment, canonical physical writes, locks or release.
For manual Scope/Estimate/report workflows, use [DRAFT_SCOPE_DEMO.md](./DRAFT_SCOPE_DEMO.md).

## Prerequisites and isolated setup

Use the current isolated worktree and its dependencies (`.[dev,postgres]`), Docker,
PostgreSQL 16 and a trusted local ClamD daemon. Inspect existing container names,
ports and marked demo directories before starting anything; do not overwrite them.
The already verified development setup is:

- `classifire-pdf-intake-20260906-pg`: PostgreSQL on 127.0.0.1:15432; dedicated
  `classifire_draft_pdf_demo` database for the browser. Separate
  `classifire_containment_test` is destructive-test-only; never swap those names.
- `classifire-pdf-intake-20260906-av`: ClamD on 127.0.0.1:13310, no host evidence
  mounts. Official image digest
  `clamav/clamav@sha256:f0954d679017eb6d48221e2b2be3ac5457bf278a844f39b672376f55a085f591`.
  ARM Docker needed `--platform linux/amd64`. Scanner configuration uses UTC.
- These isolated containers contain no customer data. PostgreSQL's loopback trust
  setup is a synthetic development convenience, never production authentication.

On a fresh machine use distinct available names/ports and create an empty
`classifire_draft_pdf_demo` in an isolated PostgreSQL instance, user classifire_test.
Configure the trusted daemon's UTC timezone and fresh signature database. Do not
point the demo at an existing project database. General deployed settings are
CLASSIFIRE_CLAMAV_HOST/PORT and CLASSIFIRE_STORAGE_ROOT; no new provider key is needed.

From the verified worktree, reuse the exact marked directory after restart:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py `
  --data-dir C:\CLASSIFIRE\.tmp\draft-pdf-demo-20260906 `
  --port 8803 --postgres-demo-port 15432 --clamav-port 13310
```

Open http://127.0.0.1:8803/scopes. Login:
`scope-demo@example.test` / `synthetic-scope-demo-only`.
The launcher uses a fixed loopback demo database name and a matching directory/DB
marker; it refuses an existing unmarked nonempty database or a mismatched marker.
It uses create_all for the disposable demo; it does not prove real migration readiness.
Normal manual-only SQLite mode remains the default without --postgres-demo-port.
Do not copy session markers/cookies or databases into Git.

## User interaction

1. Create or open a Draft Scope and choose **PDF evidence**.
2. Retain one synthetic .pdf (<=10 MiB, <=50 pages). Observe pending/not configured;
   there is no clean verdict yet and no page view.
3. Choose **Scan and prepare PDF pages**. Only a genuine clean verdict from a fresh,
   recognized scanner allows extraction/viewing. Failed/unavailable/infected/stale
   scanning remains blocked. Correct infrastructure rather than forcing clean.
4. Inspect the raster page. Extracted text is explicitly unreviewed; no OCR or
   inferred physical facts are claimed. Pick the page, enter an observation, leave
   uncertainty explicit and confirm you reviewed it. Save the observation.
5. Open saved page-review references and download the new Draft Scope JSON. It uses
   v3 exact source/page/observation/scan/reviewer bindings, without local approval.
6. Restart only this demo process, reuse the directory/flags, log in and reopen the
   same source/Draft. Download the earlier revision and compare exact bytes.
7. Edit the observation manually and save. Its old page-review claim now says to
   review again; previous revisions stay unchanged. Importing its JSON into another
   Draft preserves unverified claims but grants no source viewing or approval rights.

## Verified evidence: 2026-09-06 AEST

Real Chrome and real ClamAV 1.5.4/database 28108 completed upload, page review,
explicit save and v3 download. The actual server restart preserved source/page
access and revision-2 bytes. A later edit created revision 3 and a visible review
warning. Scan database publication was 2026-08-30; the seven-day freshness rule
will block later access unless refreshed. This is truthful expiry, not a demo bypass.

Local evidence under `.tmp/draft-pdf-artifacts` includes synthetic-inspection.pdf,
browser-receipt.json, restart-receipt.json, exact before/after JSON and screenshots.
The served PNG is byte-identical to the owner's attached logo:
`fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.
One PDF/three Scope revisions persisted; canonical Estimate, Opening, Service and
PhysicalModelLock counts were zero. Additional generated-report QA may add only
Draft report rows; check receipts rather than assuming old counts remain current.

Final focused service/HTTP/scanner/parser/storage/migration tests: 67 passed,
2 Windows symlink-permission skips, 2 existing warnings. Migration tests separately
verify 0031 -> 0032 preserves saved Estimate/outputs and exact source binding.
Full current-head CI/review and publication status belong in PROJECT_STATE.md/PR.

No full Scope analysis, technical applicability, governed pricing, ProjectPackage,
ChatGPT or production-readiness completion is claimed. See the
[contract and operational gaps](./DRAFT_PDF_EVIDENCE_V1_CONTRACT.md).
