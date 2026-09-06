# CLASSIFIRE Session Handoff

## Verified context

2026-09-06 AEST. Worktree `C:\CLASSIFIRE\.tmp\draft-package-materialization-20260906`;
branch `feat/draft-package-materialization-20260906`, based on shared main
`13a5b34ebb08eb287aebf02ed218c78ff539f1d5` (merged PR #202). PR #202 exact-head CI
34002073595 and main CI 34002483886 succeeded. This is a checkpoint; recheck live
publication and current origin/main before continuing. The full product goal remains
active and incomplete. ADRs 0001/0002 remain accepted; no OpenClaw retirement.

## Current changes and verified issues

New-project import now uses shared semantic inspection, signed confirmation, one
Draft transaction, explicit local identities, immutable original archive/mapping,
editable imported Match/Estimate wrappers and origin-preserving v2 re-export.
Migration 0035 retains native records and separates imported origins from eligible
library releases. Report attachments reuse PostgreSQL shared scan/quarantine and a
bounded format worker. Missing or unsafe binaries cannot download/re-export.

The browser exposed a PostgreSQL Match/Estimate insert-order error; the referenced
Match revision is now flushed before its Estimate and a full PostgreSQL case was
added. Historical migration fixtures were updated to insert through actual reflected
old columns, preserving SQL NULL, original JSON/bytes, FK assertions and downgrade
refusals. Do not run today's ORM against an old schema or weaken constraints.

Measured so far: 23 core/HTTP/readiness checks, six migration checks and PostgreSQL
retention/re-import/quarantine/rollback checks passed. Chrome completed both package
profiles through local edits and new ZIP downloads; independent inspection confirmed
original bytes/history and the edited price. Mypy passed for 186 files. Restart/re-import verification passed with exact downloads and preserved edited
Estimate/history. Affected regression passed: 506 tests, three warnings. The final focused run passed 10 tests, including populated PostgreSQL import and
local workbook pricing edits. Ruff, Mypy, Bandit and one 0035 migration head passed.
Publication remains to be verified against live exact-head CI/PR. Consult current
command output/CI rather than assuming later completion from this text.

Synthetic demo: `http://127.0.0.1:8811/scopes`, login `scope-demo@example.test` /
`synthetic-scope-demo-only`. Data directory `.tmp/draft-import-demo-20260906`, separately
marked PostgreSQL database `classifire_draft_import_demo` on loopback port 15432;
ClamD is loopback port 13310. Launch from this worktree:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py --port 8811 --data-dir C:\CLASSIFIRE\.tmp\draft-import-demo-20260906 --postgres-demo-port 15432 --postgres-demo-database classifire_draft_import_demo
```

Use hidden background launches and inspect process command lines before stopping
only this demo. Never reset/adopt another database. Earlier demos and worktrees remain.
Local-only evidence: `.tmp/import-materialization-browser-receipt.json`,
`import-materialization-content-receipt.json`, edited JSON/ZIP files and screenshots;
`import-materialization-restart-receipt.json` and `import-materialization-db-receipt.json`
record successful restart/re-import and zero canonical Estimate/physical/lock counts. Browser scripts live in
`.tmp/scope-browser-test-tools`. The exact supplied logo is served and visually checked.

Preserve the legacy root `gpt/phase8-linked-original-images`: four DU conflicts,
46 unstaged modifications, 14 staged additions and unrelated untracked files. Old
pytest directories have enumeration warnings; do not claim a complete untracked
inventory. Preserve `.tmp/project-package-draft-20260905` and its three generic archive
experiments. No broad staging, reset, clean, conflict resolution or root publication.

## Start Here / Next Session

First inspect AGENTS.md, GOAL.md, project state, roadmap, architecture/ADRs, Git status,
diffs, worktrees, origin/main and exact-head PR/CI. Resolve outstanding verification/
publication for this import branch before starting a new implementation. All branch
changes are intended import work; preserve unrelated work and retained demo evidence.

**Single next product task after import publication: first thin authenticated
ChatGPT-facing Draft create/read/edit/download workflow over the existing services.**
The standalone UI and selected-package lifecycle now provide the reusable core; the
second interface is the remaining user-facing integration requirement. It need not
wait for every technical/pricing edge case. Do not rebuild the core or fork domain logic.

Files/components: application route registration, `security.py`, Draft Scope/package
services, `draft_project_package_ui.py`, existing owner/permission/CSRF patterns,
capability contracts and `docs/DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md`. Inspect actual
paths/contracts before editing; no ChatGPT adapter or authentication decision is
claimed implemented here.

Prerequisites: verify merged import behavior and current integration documentation;
choose explicit human/client identity, ownership, mutation confirmation and bounded
file transfer over the existing backend. Existing tenant/project privacy is not fully
proven. External credentials, HTTPS deployment and app connection are separate
boundaries; do not expose local writes or substitute agent credentials implicitly.
No local implementation blocker is established. Local parity can use synthetic clients.

Definition of done for the next slice: one authenticated client can create an owned
Draft, read/edit explicit revisions, validate and retrieve the exact package; denied
ownership/permissions, stale writes and missing confirmation fail safely. No matching,
pricing/provider or canonical workflow runs implicitly. Demonstrate UI/client parity
and restart persistence; document exactly what was and was not connected externally.

Validation for current import changes:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_package_materialization.py tests/test_draft_package_import_ui.py tests/test_draft_import_reports.py tests/test_migrations_draft_package_imports.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

PostgreSQL tests require the repository's explicitly opted-in disposable
`classifire_containment_test` fixture; never point destructive tests at a demo,
customer or operational database. Run relevant new adapter/auth/permission/conflict
and existing Draft regressions for the next slice, plus actual client/browser parity.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Inspect AGENTS.md, GOAL.md,
> docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/SESSION_HANDOFF.md, accepted ADRs 0001/0002, Git status/diff/worktrees,
> origin/main and current exact-head PR/CI before editing. Preserve the conflicted
> C:\CLASSIFIRE root, unrelated changes, old worktrees and synthetic evidence. First
> finish any outstanding verification/publication of feat/draft-package-materialization-20260906;
> do not rebuild its editable package import. Then the single next product task is
> the first thin authenticated ChatGPT-facing Draft create/read/edit/download slice,
> because the standalone UI and shared package services now provide reusable core
> behavior and the second interface is missing. Inspect actual route registration,
> security.py, Draft Scope/package/import services, UI tests and package contracts.
> Check current official integration guidance; establish human/client identity,
> ownership and explicit mutation confirmation before exposing writes. Reuse existing
> services, keep AI optional and avoid speculative infrastructure or automatic
> capability chaining. Done means a synthetic authenticated client creates, edits,
> validates and downloads one owned Draft/package with exact bytes, restart/UI parity,
> and refusal of foreign access, revoked rights, stale writes and unconfirmed changes.
> Run focused client/auth/service/HTTP/permission/conflict tests, affected Draft/package
> regressions, Ruff, Mypy, Bandit and migration-head checks. External credentials,
> deployment and real-provider/customer/canonical operations require separate authority;
> complete safe local work and report any concrete external blocker. Continue
> autonomously through implementation, validation, change classification, explicit
> commit, normal push, PR and merge when current-head checks/reviews permit. Preserve
> unrelated work and never bypass CI, approval or release protections. Update the
> aligned goal/state/architecture/roadmap/handoff from evidence and explain plainly.


## Publication checkpoint

PR #203 is open. Initial implementation commit `f02a693cd79efe3ebb994b33866e21b38fa1b249`
was pushed normally. Initial hosted run 34006909588 correctly refused an old current-
stack test fixture still stamped 0034; no production guard failed or was weakened.
The preflight fixture and two remaining current-head migration assertions now expect
0035. Recheck the latest PR head and full CI before merge; do not bypass that failure.

The follow-up preflight/legacy-lineage checks passed: 10 tests. A fresh committed-
server Chrome check confirmed exact saved archives/logo and ancestor report inventory.
