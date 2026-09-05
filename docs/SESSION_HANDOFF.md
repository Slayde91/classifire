# CLASSIFIRE Session Handoff

**Verified:** 2026-09-05 (AEST).
**Pre-increment shared main:** `803da1bfee1724a9f1bd86f58b6130782dfdb8c3` (PR #187).
**P0 branch/worktree:** `feat/draft-scope-ui-20260905` at
`C:\CLASSIFIRE\.tmp\draft-scope-ui-20260905`.
**Architecture:** accepted ADR 0001 + approved ADR 0002; prototype-first delivery.
Publication is a separate fact: inspect the current branch/PR/checks/merge before
continuing, rather than assuming this handoff records a completed merge.

## Start Here / Next Session

**Single first task: P1a, safe Draft Scope JSON import/replacement in the working
UI.** Complete any outstanding P0 publication check first. A user should upload
saved Draft Scope JSON, inspect a validation/identity/uncertainty preview and
explicitly apply content as a new local Draft revision. Preserve prior revisions
and foreign source lineage without importing local authority.

**Why next:** P0 now provides a demonstrated create/edit/validate/save/reopen/
download workflow. Import closes the smallest useful portability loop so users
can return with saved work. Rebuilding P0 or completing every archive/schema before
an interaction would repeat work or undo the approved delivery priority.

### Inspect before editing

Read `AGENTS.md`, `GOAL.md`, the maintained docs under `docs/`, ADRs 0001/0002 and
`docs/DRAFT_SCOPE_V1_CONTRACT.md`. Inspect branch, HEAD, upstream, status/conflicts,
worktrees, current main, relevant PR/CI and newer source before selecting edits.
Use an isolated current-main worktree. Preserve unrelated changes and the legacy
root. Architecture approval is complete; a manual import path does not require
OpenClaw production assurance or a real provider/customer report.

Relevant implementation:

- `src/classifire/services/draft_scope.py`: strict manual payload/envelope,
  owner/admin checks, caller-owned transactions, revision compare-and-save,
  integrity checking and exact download. Reuse these shared rules.
- `src/classifire/draft_scope_ui.py`, `templates/draft_scope.html`,
  `templates/draft_scopes.html`, `static/draft_scope.js`, `static/draft_scope.css`:
  actual UI, bounded forms, CSRF, validation findings and safe DOM rendering.
- `src/classifire/models.py`, migration `0027_draft_scope_revisions.py`,
  `services/deployment_lineage.py`, `security.py`, `db.py`: existing persistence,
  migration-readiness and authority boundaries; add a forward migration only if needed.
- `tests/test_draft_scope.py`, `test_draft_scope_ui.py`,
  `test_migrations_draft_scope.py`, `test_deployment_lineage.py` and existing
  human-session/physical-boundary/snapshot regressions.
- `scripts/run_draft_scope_demo.py`, `docs/DRAFT_SCOPE_DEMO.md`: isolated synthetic
  launcher and real browser/restart/download evidence. Use these to demonstrate.

Abbreviated code paths above are relative to `src/classifire/`; test paths are
under `tests/`. Check current filenames and behavior rather than treating this
list as proof. The protected canonical opening/service writers are not Draft APIs.

### Prerequisites, dependencies and blockers

P0 source and its required CI must be available on the selected branch. Use the
existing virtual environment or install declared development dependencies in an
isolated environment. SQLite tests/demo need no customer database. The hosted CI
PostgreSQL service supplies the real concurrent-save test; a local skip is not a pass.

The v1 contract is manual-only and has no imported-source lineage. Determine the
smallest explicit compatible evolution needed for import while retaining v1 reads.
Check declared hashes/schema and every relationship; checksum validity is not trust
in an author or assertion. Give a new local revision its current actor/time/ownership
and retain foreign identity/hash as attributed source history, not approval.

There is no known architecture-approval blocker to this bounded task. Existing
shared project names/references mean production tenant privacy remains unproven.
Use synthetic data only. Do not introduce ZIP, arbitrary files, external fetches,
automatic report extraction or operational canonical writes into this slice.

### Definition of done for P1a

1. An authenticated owner/admin can upload a supported saved Draft JSON and see
   a useful preview with identity, differences/content, uncertainty and blockers.
   Preview does not save or run another capability.
2. Explicit confirmation appends a new local Draft revision using the expected
   current revision. Reopen/restart and download preserve its content and lineage.
   The original local history and original imported artifact identity are retained.
3. Malformed/oversized input, duplicate JSON keys, unsupported versions, hash or
   graph mismatch, stale confirmation and unauthorized access fail without writes.
   Foreign actor/project/approval claims never grant local authority. Uploaded
   text is data and cannot execute code, HTML, formulas or hidden instructions.
4. Existing v1 revisions still validate and download with unchanged bytes. Any new
   schema/version or migration is explicit, tested and documented. No silent v1
   reinterpretation; no blanket trust in caller-supplied lineage.
5. No AI, matching, estimation, canonical admission/lock or release occurs. Relevant
   service/HTTP/security/migration regressions pass. Observe the actual browser
   export/import/confirm/reopen/download flow and inspect the generated JSON.
6. Update contract, demo and continuity docs from evidence, classify all local
   changes, then commit, push normally, create/update the PR and merge after
   exact-head CI/review permit it. Verify the resulting merge; do not deploy.

### Validation commands

Use the isolated feature worktree, never the conflicted root. Confirm dependencies
and the repository CI configuration before running these commands:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$taskTestBase = Join-Path $env:TEMP ('classifire-scope-' + [guid]::NewGuid().ToString('N'))
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTestBase tests/test_draft_scope.py tests/test_draft_scope_ui.py tests/test_migrations_draft_scope.py tests/test_deployment_lineage.py tests/test_human_session_security.py tests/test_physical_api_boundary.py tests/test_initial_canonicalisation_boundary.py tests/test_snapshot.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -r src
node --check src/classifire/static/draft_scope.js
git diff --check
```

Add import-specific tests in the same service/HTTP suites. If models/migrations or
lineage change, run the full migration collection and the affected preflight/lineage
regressions; changing the latest head affects more than the packaging assertion.
Mypy needs the repository's declared stub dependencies. The previous local run used
temporary stubs for missing declared packages; do not hide dependency failures.
Run the demo instructions and inspect outputs; unit tests alone do not prove the UI.
No `doctor` against a configured customer database or real report UAT is authorized.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE toward accepted ADR0001/ADR0002, with working UI slices first.
Inspect repository state BEFORE editing: AGENTS.md, GOAL.md, docs/PROJECT_STATE.md,
architecture, roadmap, handoff, ADRs and docs/DRAFT_SCOPE_V1_CONTRACT.md; verify
branches/worktrees/diffs/current main/PR/CI and newer implementation. P0 was locally
demonstrated on feat/draft-scope-ui-20260905 based on803da1b (PR187); first verify its
publication. Preserve C:\CLASSIFIRE's conflicted recovery checkout and unrelated
local/package-candidate work; use a clean current-main worktree.

Single task: P1a safe Draft Scope JSON import/replacement in the existing UI. This
closes the download/return loop on working P0; do not rebuild it. Inspect shared
services/draft_scope.py, draft_scope_ui.py, DraftScope models/migration0027,
deployment_lineage.py, Draft templates/static files and service/HTTP/migration tests.
The v1 envelope is manual-only: make any import-lineage/schema evolution explicit
and backward compatible. Reuse owner/admin, CSRF, validation and revision guards.

Deliver bounded upload, no-write preview and explicit confirmation as a new local
Draft revision; preserve old revisions and source identity/hash while assigning
local actor/time/ownership. Refuse bad versions/hashes/graphs, oversized/duplicate
JSON, unauthorized access and stale saves without writes. Foreign history grants
no approval. Prove old v1 download bytes remain unchanged. No ZIP/report extraction,
AI, matching, pricing, canonical admission/locks or release; synthetic data only.
Production tenancy is unproven and is not claimed by this task.

Done: service/HTTP and relevant authority/migration tests pass; Ruff/Mypy/Bandit,
JS syntax and diff checks pass; actual isolated browser export/import/preview/
confirm/restart/reopen/download works and JSON is inspected. Use handoff commands
with worktree src in PYTHONPATH and fresh test storage; hosted CI must cover the
PostgreSQL race. Align docs, classify changes and continue autonomously through
commit, normal push, PR and merge when exact-head CI/reviews permit; verify merge.
No speculative expansion, unrelated edits, guard bypass, deployment or real data.
Report evidence, limitations, Git/PR result and the next useful visible slice.
```

## Verified P0 evidence and local context

- Actual Chrome flow and actual server restart passed; screenshots were inspected.
  The same saved revision downloaded byte-for-byte identically after restart.
  File SHA-256: `551221821649d33a78b0a2e8a8fa427a0b7e60819b8c0199605351c2edc04f4e`.
  Embedded envelope hash: `4f49cae3c03733a29df87342ac3fd409c9ab3f839aca3d93e5cd3e96c42e7fc5`.
- Initial combined local regression: 69 passed, one local PostgreSQL skip, two
  existing warnings. Final HTTP suite after duplicate-create and malformed-field
  regressions: 20 passed, one existing Starlette/httpx warning. Full Mypy passed
  146 source files; Ruff/Bandit and JavaScript/template checks passed during review.
  The full migration collection plus deployment/preflight/legacy regression run
  passed 41 tests with one existing Alembic warning. Final source Mypy/Ruff also
  passed after the corrections. Publication checks remain separate evidence.
- Demo data at `.tmp/draft-scope-demo-20260905` is synthetic. Browser tools/receipts/
  screenshots/downloads are under `.tmp/scope-browser-test-tools` and
  `.tmp/draft-scope-demo-artifacts`. No generated data, cookies or tool dependencies
  belong in the PR. The launcher uses loopback and isolated storage only.
- The legacy root remains `gpt/phase8-linked-original-images`, HEAD `de0cc5a`, with
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`, four conflicts and
  staged/unstaged/untracked recovery work. Never reset, clean or broadly stage it.
- `.tmp/project-package-draft-20260905` retains three untracked candidate files
  (contract, service, tests), previously 22 synthetic tests passed. It is unrelated
  preserved work, not a shipped project archive or dependency of P1a.
- Historical open issues #42/#43 concern Phase8 tooling/OpenClaw advisories; legacy
  draft PRs #9-#13 are recovery context. Requery their current state as needed.
  Production provider assurance, real-UAT/locks, release and deployment remain
  separately gated and were not exercised by this prototype.

Use [PROJECT_STATE.md](./PROJECT_STATE.md) for health and current gaps,
[the roadmap](./CLASSIFIRE_ROADMAP.md) for sequencing and
[the architecture](./CLASSIFIRE_ARCHITECTURE.md) for implemented/target boundaries.
