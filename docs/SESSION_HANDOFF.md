# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06 AEST. Worktree `C:\CLASSIFIRE\.tmp\chatgpt-draft-client-20260906`, branch
`feat/chatgpt-draft-client-20260906`, based on main `2f79e490049d23a9dc8e34e3aa54fb8d232a960d`
(PR #203). PR #203 exact-head CI 34007195747 passed 1,470 tests and main CI 34007644149
succeeded. Recheck current upstream/head/PR/CI before editing or publishing this branch.
The full platform goal remains active and incomplete. ADRs 0001/0002 are accepted.

## Work and evidence

Current changes implement the first optional authenticated MCP client with shared
Scope/create/edit/package commands. Durable proposals require the same human's UI
confirmation; SQL compare-and-set prevents double execution. Migration 0036 is
additive and retains review history. JWT policy explicitly maps external subjects
and clients to local users/scopes; current role, owner, expiry and revocation checks
remain mandatory. No provider or canonical approval/lock/release is exposed.

The official SDK and Chrome completed create/edit/package/download with exact
client/browser bytes and the supplied logo. Actual process restart preserved bytes;
sign-in returned to the requested review and rejection persisted. The final screen
reuses the readable Scope component instead of presenting raw JSON as the main review.
Final presentation/static/CI status must be verified live. Measured suites: 38
client/migration/readiness checks, 11 PostgreSQL/preflight checks, 74 affected checks
(one separately passed PostgreSQL test skipped in that run). Mypy passed 190 files;
Ruff/Bandit passed before final presentation changes. Do not sum overlapping runs.

Local evidence in `C:\CLASSIFIRE\.tmp`:
`draft-client-browser-receipt.json`, `draft-client-restart-receipt.json`,
`draft-client-db-receipt.json`, `draft-client-export.zip`, screenshots named
`draft-client-*.png`, `draft-client-probe.py`, and browser scripts under
`scope-browser-test-tools`. No receipt contains a real customer/provider token.
The synthetic token stays inside the marked demo directory and expires in 15 minutes.

Demo: `http://127.0.0.1:8812/scopes`; login `scope-demo@example.test` /
`synthetic-scope-demo-only`. Launch from this worktree using:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py --port 8812 --data-dir C:\CLASSIFIRE\.tmp\draft-client-demo-20260906 --client-demo
```

Use hidden background launches. Inspect command lines before stopping only this
specific demo. The launcher binds only loopback and a marked synthetic SQLite
store; it is not a production OAuth server. Earlier import demo at 8811 remains.
The exact user logo remains `src/classifire/static/brand/classifire-logo.png`.

Legacy root and old worktrees were preserved. The last root inventory recorded four
DU conflicts, 46 unstaged modifications, 14 staged additions and unrelated untracked
work; enumeration of some old pytest directories was incomplete. Never broadly stage,
reset/clean, resolve or publish that root. Recheck any state needed for recovery.

## Start Here / Next Session

**First task:** reconcile current branch/PR/CI and finish publication if needed.
Then extend the existing MCP adapter to the three remaining independently callable
Draft capabilities: System Match, Estimate and reporting. This is the next product
increment because their standalone commands exist and the second interface currently
covers only Scope and selected package operations. Avoid a new orchestration layer.

**Files:** `draft_client.py`, `draft_client_auth.py`,
`services/draft_client_requests.py`, `services/draft_system_matches.py`,
`services/draft_estimates.py`, `services/draft_scope_reports.py`,
`services/draft_estimate_reports.py`, related UI modules/contracts/tests and
`docs/DRAFT_CLIENT_V1_CONTRACT.md`. Inspect actual callable signatures and permissions.

**Prerequisites/dependencies:** current shared baseline, optional `chatgpt` extra,
synthetic authorized library/pricing inputs and explicit saved revisions. Preserve
request confirmation and ownership boundaries, including foreign imported sources.
Real OAuth provider credentials, HTTPS deployment and ChatGPT account connection
require separate operational authority; they do not block safe local parity work.

**Definition of done:** each added capability can be called independently with
valid explicit inputs, reviewed/confirmed by its human owner, reopened and downloaded
with the same saved results as the UI. Deny foreign/revoked/stale/replayed requests.
No automatic analysis/matching/pricing/report chain, no core duplication or canonical
promotion. Inspect client/browser outcomes and outputs, not only schemas.

**Validation:** focused client/auth/service/HTTP and relevant capability/report
regressions; official SDK + browser saved-artifact/restart parity; Ruff, Mypy,
Bandit and one Alembic head. For the current client branch:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_client.py tests/test_migrations_draft_client_requests.py tests/test_human_session_security.py tests/test_deployment_lineage.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

PostgreSQL tests use the guarded disposable `classifire_containment_test` fixture.
Verify its isolation before opting in; never target demo/customer/operational stores.
Use a unique temporary directory and inspect the source import path in worktrees.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Read AGENTS.md, GOAL.md,
> docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/SESSION_HANDOFF.md and docs/DRAFT_CLIENT_V1_CONTRACT.md. Inspect Git status,
> worktrees, origin/main and current PR/head/CI before editing. Preserve the conflicted
> C:\CLASSIFIRE root, unrelated local changes, old worktrees and synthetic receipts.
> First finish any outstanding publication of feat/chatgpt-draft-client-20260906.
> The next single product task is to expose the existing independent Draft System
> Match, Estimate and report workflows through that same authenticated MCP adapter,
> because their UI/shared services exist but the client currently covers only Scope
> and packages. Inspect draft_client.py, draft_client_auth.py, the retained request
> service and existing matching/estimate/report services, contracts and tests. Reuse
> shared domain logic and same-user browser confirmation; require current identity,
> permissions, ownership and explicit saved inputs. Keep AI optional and never chain
> capabilities or grant canonical approval implicitly. Use synthetic fixtures only.
> Done means each capability works independently through client and UI with identical
> saved artifacts/downloads after restart, with denied foreign, revoked, stale and
> replayed requests. Run focused client/auth/HTTP/service and affected report tests,
> official SDK/browser/output checks, Ruff, Mypy, Bandit and migration-head validation.
> Real OAuth/HTTPS/ChatGPT account setup needs separate authority; complete safe local
> work and identify exact external blockers. Avoid speculative infrastructure.
> Continue autonomously through implementation, validation, change classification,
> explicit commit, normal push, PR and merge after exact-head checks/reviews permit.
> Never bypass protections; update aligned docs from evidence and explain plainly.


## Final local validation checkpoint

Final client/auth/readable-Scope regression: 64 passed, one PostgreSQL test skipped
in that run (the separate PostgreSQL confirmation test passed). Full Ruff, Mypy
(190 files), Bandit and the single 0036 migration head passed. Final Chrome inspection
confirmed readable proposed physical content, the exact supplied logo, login return,
persisted rejection and byte-identical downloads after process restart. Documentation
links and diff whitespace checks passed. Git publication/full exact-head CI still
must be checked live; these local results do not establish external ChatGPT linking.
