# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06 AEST. Worktree:
`C:\CLASSIFIRE\.tmp\client-independent-capabilities-20260906`; branch
`feat/client-independent-capabilities-20260906`; base shared main
`bef06e2264944a34f85f72e7d0fb80c83e406997` (merged PR #204). Its main CI
34010757579 succeeded. Recheck current head/upstream/PR/CI before editing.
ADRs 0001/0002 are accepted; the full production goal remains active and incomplete.
This is a pre-publication checkpoint, not a claim that the current branch is merged.

## Current work and verification

The optional client now proposes independent Match retrieval/review, Estimate
creation/manual lines/overrides/omit/restore, and all four report profiles. It lists
and reads saved capability artifacts/staleness and downloads exact saved PDF/XLSX.
Typed commands bind selected input hashes; the existing same-user browser session
confirms and calls shared services. New technical/estimate scopes also guard nested
content and ZIPs. No automatic capability chaining or canonical approval is exposed.
Migration 0037 extends the request check constraint and preserves retained history.

Files: `src/classifire/draft_client*.py`,
`src/classifire/services/draft_client*.py`, `models.py`,
`migrations/versions/0037_draft_client_capabilities.py`,
`services/deployment_lineage.py`, `templates/draft_client_request.html`,
client/migration/current-head tests, `scripts/run_draft_scope_demo.py` and core docs.
Current diff is only this authorized increment. Legacy root/unrelated work is preserved.

Focused capability/migration/readiness: 26 passed. Affected regression: 192 passed,
one PostgreSQL test skipped and two existing warnings. Mypy passed 193 files;
Ruff/Bandit passed. Official SDK + Chrome passed independent estimate/match/review
and eight exact report downloads. All eight outputs remained exact after actual
process restart; saved revisions and a rejected review persisted. The review screen,
correct logo and rendered complete PDF were visually inspected. PostgreSQL race
coverage is delegated to required CI; this is not a local PostgreSQL run claim.

Local receipts/artifacts under `C:\CLASSIFIRE\.tmp`:
`client-capabilities-browser-receipt.json`, `client-capabilities-output-inspection.json`,
`client-capabilities-restart-receipt.json`, generated
`client-capabilities-{profile}.pdf/.xlsx`, screenshots `client-capabilities-*.png`,
`client-capabilities-probe.py` and browser scripts in `scope-browser-test-tools`.
The logo served at `/brand/classifire-logo.png` exactly matches the user's root PNG;
keep `src/classifire/static/brand/classifire-logo.png` unchanged.

Demo: `http://127.0.0.1:8813/scopes`, login `scope-demo@example.test` /
`synthetic-scope-demo-only`. From this worktree:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py --port 8813 --data-dir C:\CLASSIFIRE\.tmp\client-capabilities-demo-20260906 --client-demo --seed-technical-library
```

This is a marked, loopback synthetic SQLite demo. The token is synthetic, stays in
its marked directory and expires after 15 minutes; restart refreshes it. Never log,
commit or paste tokens. Inspect exact process command lines before stopping only
this demo and use hidden background launches. Earlier demos at 8811/8812 remain.
The root `C:\CLASSIFIRE` is conflicted recovery evidence; do not reset, clean, resolve,
broad-stage or publish it. Old worktrees and unrelated changes remain untouched.

## Start Here / Next Session

**First task:** after verifying/finalizing current publication, expose existing
measured-constraint and service-size review through the same client confirmation
boundary. The current client retrieves/reviews candidates but cannot enter these
measurements; standalone UI/shared services already implement the bounded checks.
This improves useful technical review without duplicating rules or claiming complete applicability.

**Files:** `services/draft_system_matches.py:save_constraint_review`,
`services/draft_constraint_review.py:validate_inputs`, `draft_system_match_ui.py`,
`services/draft_client_capabilities.py`, `draft_client_capability_tools.py`,
`services/draft_client_requests.py`, `templates/draft_client_request.html`,
`tests/test_draft_client_capabilities.py`, `tests/test_draft_constraint_review*.py`,
`tests/test_draft_service_size*.py`, and `docs/DRAFT_CLIENT_V1_CONTRACT.md`.

**Prerequisites/dependencies:** current shared main and `.[dev,postgres,chatgpt]`,
explicit saved Match revision and authorized synthetic source/measurement fixtures.
Keep client technical scope, current domain permissions, owner identity, stale-input
checks, source integrity, human confirmation and review history. Real provider data,
OAuth credentials/account linking and HTTPS deployment need separate authority;
none is a prerequisite for synthetic parity. No known blocker to this bounded task.

**Definition of done:** each supported measured review can be proposed, inspected,
confirmed/rejected and reopened through client and UI with the same saved revision
and findings; reports retain that exact reviewed input after restart. Invalid,
foreign, revoked, stale and replayed requests are denied. Existing source and
constraint guards remain intact; no invented compatibility or automatic next capability.
Inspect the UI and output, update docs, classify the diff and complete safe publication.

**Validation:** focused client/constraint/service-size/HTTP and report regressions;
official SDK + browser review and process-restart artifact parity; Ruff, Mypy,
Bandit, one Alembic head and required exact-head CI. Set the isolated source path:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_client.py tests/test_draft_client_capabilities.py tests/test_draft_constraint_review.py tests/test_draft_constraint_review_ui.py tests/test_draft_service_size_review.py tests/test_draft_service_size_ui.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

PostgreSQL tests require the guarded disposable loopback fixture; verify isolation
before opting in. Never target a demo/customer/operational database for table cleanup.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Read AGENTS.md, GOAL.md,
> docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/SESSION_HANDOFF.md and docs/DRAFT_CLIENT_V1_CONTRACT.md. Inspect Git status,
> worktrees, origin/main and current branch/PR/CI before editing. Preserve the
> conflicted C:\CLASSIFIRE root, unrelated local changes, old worktrees, receipts and
> supplied logo. First finish any outstanding publication of
> feat/client-independent-capabilities-20260906. The single next product task is
> client parity for the existing measured-constraint and service-size review: the
> UI/shared services already support it, while MCP currently only retrieves and
> keeps/rejects candidates. Inspect save_constraint_review in draft_system_matches.py,
> draft_constraint_review.py, draft_system_match_ui.py, draft_client_capabilities.py,
> the retained client request service, review template and constraint/service-size tests.
> Reuse those rules with explicit saved revisions, technical scope, current ownership,
> source integrity and same-human browser confirmation. Use synthetic fixtures only;
> real OAuth/account linking/deployment requires separate authority and does not
> block local work. Done means independently proposed/confirmed/rejected reviews,
> equal client/UI saved findings and exact report inputs after process restart, with
> invalid/foreign/revoked/stale/replayed operations refused and no canonical approval
> or automatic chaining. Run focused client/constraint/service-size/report tests,
> official SDK + Chrome/restart proof, Ruff, Mypy, Bandit and migration-head/CI checks.
> Update aligned docs, classify changes and continue autonomously through implementation,
> validation, explicit-path commit, normal push, PR and merge after required checks
> and reviews pass. Verify the merge; never bypass controls or add speculative work.


Final local presentation checkpoint: the review labels the selected saved Estimate
and explicitly separates its totals from proposed edits. All four client capability
journey/boundary tests passed again after that caption change. Documentation links,
Ruff and diff whitespace checks passed. Required exact-head CI/publication is the
remaining step at this pre-commit checkpoint.
