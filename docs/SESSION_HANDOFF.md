# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06 AEST. Worktree:
`C:\CLASSIFIRE\.tmp\client-measured-review-20260906`; branch
`feat/client-measured-review-20260906`; base/shared main
`fd60bb82538c248b73a14e09dd71bec7493ba7da` (merged PR #205). Main CI
34014555539 succeeded; PR #205 feature `d565621730eb69d197ccf499775ad2bce48a6c92`
passed exact-head CI 34013051763 attempt 2 (1,502 tests). The unchanged retry followed
a worker timeout; no test/assertion/CI timeout was weakened.

ADRs 0001/0002 remain accepted. The full production goal is active and incomplete.
This document is the measured-review increment's pre-publication checkpoint; inspect
its current head/upstream/PR/CI and any local publication receipt before editing.
Do not infer merge or deploy status from the existence of this file.

## Current work and verification

Two client actions reuse shared `validate_inputs` / `save_constraint_review` for
v2 thickness/gap and v3 service-size reviews. Preparation binds explicit saved inputs;
only the same human's separate browser session confirms. Current technical/owner/
source guards and immutable history remain. The confirmation UI shows prior saved
measurements separately from proposed values, with no embedded measurement writer.
No new migration, dependency, domain rule, canonical authority or automatic chaining.

Changed files: `services/draft_client_capabilities.py`,
`services/draft_client_requests.py`, `templates/draft_client_request.html`,
`templates/draft_constraint_review.html`, `tests/test_draft_client_measurements.py`,
GOAL and aligned project/client documents. Paths above are under `src/classifire`
unless prefixed `tests`. AGENTS.md was inspected and remains accurate without changes.

Initial regression: 54 passed; focused new suite: 9 passed. Mypy passed 193 files;
Ruff/Bandit passed and the unchanged single migration head is
`0037_draft_client_capabilities`. Official SDK + Chrome demonstrated both reviews,
rejection, unresolved semantics, exact client/UI saved findings and four PDF/XLSX
outputs. Actual restart preserved current/historical Match revisions, rejected
requests and all four exact outputs; later input changes make reports stale.
PDF text and XLSX contents were inspected; the saved report summary was visually
inspected. Read-only synthetic database counts showed zero canonical physical,
Estimate or lock rows. No real scanner/provider, operational lock or release ran.

Local receipts/artifacts under `C:\CLASSIFIRE\.tmp`:
`client-measured-browser-receipt.json`, `client-measured-output-inspection.json`,
`client-measured-restart-receipt.json`, generated `client-measured-*.pdf/.xlsx`,
screenshots, `client-measured-probe.py` and browser scripts in `scope-browser-test-tools`.
The logo served at `/brand/classifire-logo.png` exactly matches the supplied root PNG;
keep `src/classifire/static/brand/classifire-logo.png` unchanged.

Demo: `http://127.0.0.1:8814/scopes`, login `scope-demo@example.test` /
`synthetic-scope-demo-only`. From this worktree:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py --port 8814 --data-dir C:\CLASSIFIRE\.tmp\client-measured-demo-20260906 --client-demo --seed-service-size-library
```

This is a marked loopback SQLite demo with explicit seeded technical/clean fixture
metadata. Its synthetic token stays in the marked directory and expires in 15 minutes;
restart refreshes it. Never log, paste or commit tokens. Verify exact command lines
before stopping only the owned demo; background launches must be hidden. Earlier
demos (including 8813), worktrees and receipts remain unrelated local artifacts.
The root is still conflicted recovery work on `gpt/phase8-linked-original-images`
(four DU paths plus pre-existing staged/unstaged changes, inspected read-only).
Do not reset, clean, resolve, broad-stage or publish that checkout.

## Start Here / Next Session

**First task:** after verifying/finalizing current publication, expose preview and
human-confirmed application of one already retained/scanned XLSX pricing row to an
existing Draft Estimate line. This closes a proven UI/client gap using existing
commercial rules. Keep upload/scan in the current UI for this bounded increment.

**Files/components:** `services/draft_pricing_intake.py` (`preview`, `apply_rate`),
`services/draft_pricing_contract.py`, `services/draft_source_intake.py`,
`draft_pricing_ui.py`, client capability/tool/request modules and review template,
`tests/test_draft_pricing.py`, `tests/test_draft_pricing_ui.py`, client and
Estimate/report tests, and `docs/DRAFT_CLIENT_V1_CONTRACT.md`.

**Prerequisites/dependencies:** current shared main, `.[dev,postgres,chatgpt]`, an
owned saved Estimate/line and a retained synthetic workbook. Reuse `workbook_bytes`
and `MAPPING` fixtures. Source containment tests need the guarded disposable loopback
PostgreSQL database and marked storage; verify it is isolated/empty/idle before any
fixture cleanup opt-in. A demo/customer/operational database is never that test target.
No known implementation blocker; unavailable disposable PostgreSQL blocks its required
containment proof, not investigation. Real OAuth/account/HTTPS deployment needs separate
authority and is not a prerequisite for the local synthetic interaction.

**Definition of done:** a client can inspect readable mapped row/cell provenance,
propose its use and let the same human confirm/reject. Bind the current Estimate
revision, target line, source/document/row hashes, mapping and recovery note; require
current estimating client scope, owner and domain/project/estimate/library rights.
Only confirmation calls `apply_rate`; no partial revision survives failure. Preserve
original/override history and unchanged retained report bytes after restart. Refuse
stale/replayed/revoked/foreign requests, changed/quarantined sources, unsupported
units and formula-derived rates. No pricing inference, new parser or canonical writes.
Inspect the UI/output, align docs, classify and complete safe publication.

**Validation:** pricing/client/estimate-report suites, official SDK + Chrome,
actual process-restart parity, Ruff/Mypy/Bandit, applicable migration checks and
required exact-head CI. Inspect repository test configuration before commands:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_pricing.py tests/test_draft_pricing_ui.py tests/test_draft_client.py tests/test_draft_client_capabilities.py tests/test_draft_estimates.py tests/test_draft_estimate_reports.py tests/test_draft_complete_reports.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Local Mypy has used stubs at
`C:\Users\tanas\AppData\Local\Temp\lifecycle-stubs-9f7cfd6c36c84af0b5b19c5f3dcf36c7`
appended to PYTHONPATH; verify availability rather than copying a stale command.
Run PostgreSQL suites serially and record skips honestly. Do not weaken containment
or tests to complete a demo.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Read AGENTS.md, GOAL.md and
> docs/PROJECT_STATE.md, CLASSIFIRE_ROADMAP.md, CLASSIFIRE_ARCHITECTURE.md,
> SESSION_HANDOFF.md and DRAFT_CLIENT_V1_CONTRACT.md. Inspect Git status/worktrees,
> origin/main and live branch/PR/CI before editing; first finish any outstanding
> publication of feat/client-measured-review-20260906. Preserve the conflicted root,
> unrelated work, receipts and supplied logo; use an isolated main-based worktree.
> The single next task is client preview and human-confirmed application of one
> already retained/scanned XLSX row to an existing Estimate line. The standalone
> service already supports it, while the client only supports manual pricing.
> Reuse draft_pricing_intake.preview/apply_rate, draft_pricing_contract,
> draft_source_intake, existing pricing UI and client capability/request tools.
> Keep upload/scan in the UI. Bind saved revision, target line, source/document/row
> hashes, mapping and recovery note; require current estimating scope, owner and
> project/estimate/library permissions. Only separate same-human confirmation applies
> the rate. Use synthetic workbook_bytes/MAPPING fixtures and verified disposable
> PostgreSQL/storage; unavailable isolation is a containment-test blocker, never a
> reason to use customer data. Done means readable provenance, confirm/reject/replay
> proof, denied stale/revoked/foreign/changed/quarantined or unsupported unit/formula
> inputs, preserved original/override history and exact report bytes after restart.
> Run focused pricing/client/estimate/report tests, official SDK + browser/restart,
> Ruff, Mypy, Bandit and migration/CI checks. Update aligned docs, classify changes
> and continue autonomously through implementation, validation, explicit-path commit,
> normal push, PR and merge after required exact-head checks/reviews pass. Verify the
> merge. Do not deploy, use real providers, bypass controls or add speculative work.
> After this bounded parity slice, prioritize user feedback and the missing
> evidence-to-structured-Draft interaction instead of indefinite adapter polish.


Final local checkpoint: affected client/measurement/report regression **147 passed,
one PostgreSQL test skipped** in 299.47 seconds. The PostgreSQL confirmation race
remains for required CI; no local PostgreSQL execution is claimed for this increment.
The final browser confirmation, saved-measurement comparison and supplied logo were
visually inspected. Documentation links and diff whitespace checks passed. Exact-head
CI, PR and merge remain the publication steps at this checkpoint; verify them live.
