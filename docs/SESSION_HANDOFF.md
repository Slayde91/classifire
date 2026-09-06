# CLASSIFIRE Session Handoff

## Verified context

2026-09-06 AEST. Current worktree:
`C:\CLASSIFIRE\.tmp\draft-package-import-20260906`; branch
`docs/prototype-state-logo-verification-20260906`, based on shared main
`541c107b9b3552e572d9933b86140b4d6f750120` (merged PR #200).
PR #200 exact-head CI 33998891633 and main CI 33999342298 succeeded, rechecked
2026-09-06. This branch reconciles documentation and the logo regression test;
inspect its live publication state before continuing. The retained import branch
`feat/draft-package-import-20260906` has no import implementation yet.
Do not rebuild already merged package download.

ADRs 0001/0002 remain accepted: independent capabilities, shared deterministic core,
optional AI and UI-first delivery. No OpenClaw retirement or production release.
The full objective remains incomplete despite usable Draft reports and packages.

Merged PR #200: selected package service, UI/template, router/Scope link,
DraftProjectPackage model and migration 0034, readiness/head expectations,
package/HTTP/migration tests, pricing-source permission coverage and aligned docs.
No existing migration was rewritten. No dependency or canonical authority added.
AGENTS.md already aligns and is unchanged.

Preserve the legacy `C:\CLASSIFIRE` root on `gpt/phase8-linked-original-images`:
four DU conflicts, staged/unstaged recovery changes and unrelated untracked files.
Never reset, clean, resolve, stage or publish that root implicitly. Also preserve
three untracked files in `.tmp/project-package-draft-20260905`:
`docs/PROJECT_PACKAGE_V1_CONTRACT.md`, `src/classifire/services/project_package.py`,
`tests/test_project_package.py`. They remain an older generic archive experiment;
current Draft package code implements a different, explicit selected-artifact contract.

## Verification and open work

43 focused tests passed in 65.43 seconds; broader affected migration/report/package
regression passed 98 tests with three warnings in 389.05 seconds.
Mypy (179 files), Ruff, Bandit and one migration head (0034) passed. Extended
PostgreSQL pricing/source permissions passed hosted CI. Initial wiring
failures are fixed; no current known blocker. Final results belong in the PR.

Real Chrome configured and saved Scope-only, combined and reconfigured package
revisions. All three ZIPs stayed exact after actual restart. Independent archive
inspection checked membership/hashes, embedded dependency equality, saved 440.00
subtotal and original report PDF/XLSX. Exact supplied logo remains visible and
byte-identical. Canonical Estimate/line, Opening, Service and Lock counts remain zero.

Demo: `http://127.0.0.1:8809/scopes`, separate marked synthetic directory
`.tmp/draft-package-demo-20260906`, copied from the prior synthetic report fixture;
original demo untouched. Login `scope-demo@example.test` / `synthetic-scope-demo-only`.
Launcher: `scripts/run_draft_scope_demo.py --port 8809 --data-dir <that-directory>`.
Inspect current process IDs/command lines before stopping only this demo.
Receipts/downloads/screenshots: `.tmp/package-artifacts`; browser harnesses:
`.tmp/scope-browser-test-tools/package-check.cjs` and `package-restart.cjs`.
Never stage local-only demo data or receipts.

Current reconciliation checks: all four human-session/branding tests passed (one
existing Starlette deprecation warning), Ruff and diff checks passed. The synthetic
UI login and image endpoint returned HTTP 200; its image hash equals the exact
user-supplied PNG. The header and login both reference this asset.

## Start Here / Next Session

Inspect AGENTS.md, GOAL.md, PROJECT_STATE.md, roadmap/architecture, ADRs, current Git
status/diff/worktrees and origin/main/PR/CI. Package download is merged in PR #200.
Use a clean current-main worktree, preserving unrelated changes.

**Single next task: safe new-project Draft ProjectPackage import.** Why: users can
now collect and download selected capabilities, but cannot reopen that ZIP as a new
local project and continue their work. This advances portability before extra polish.

Files: `services/draft_project_packages.py`, Scope import and envelope validators,
`draft_system_matches.py`/match contracts, `draft_estimates.py`/Estimate contracts,
report snapshot readers, models/migrations, package UI/templates and focused tests.
Read `docs/DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md` before treating the structural ZIP
inspector as a semantic importer: it is explicitly not one.

Prerequisites: package-download merge and current dependency schemas; bounded
archive validation; explicit ownership/identity/lineage mapping and import policy for
Scope, review, Estimate and reports. Retain original bytes, versioned history and
uncertainty, preserve cross-artifact references and keep unavailable external sources
unresolved. Never grant local library eligibility, approval, lock or release from
foreign claims. Imported records need safe local read/edit semantics before being
passed to other capabilities. Do not silently discard unsupported package members.

Done: real UI upload, no-write preview of complete declared membership and findings,
explicit transactional import into a new owned Draft project, reopen after restart,
and re-export with traceable foreign-to-local identities and preserved saved values.
Scope-only and populated packages both work; invalid/mixed/oversized/unsafe input and
foreign authority are refused or explicitly retained unresolved under the approved
contract. No provider, recalculation, canonical write or customer data. Original local
work and imported files remain unchanged. Update documentation and classify gaps.

Validation: focused package/import service and HTTP tests; identity/dependency,
permission/CSRF, malformed ZIP, uncertainty and rollback tests; real synthetic
browser round trip/restart and independent ZIP/content inspection. Run affected
Scope/review/Estimate/report regressions and migration compatibility where changed:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_project_packages.py tests/test_draft_project_package_ui.py tests/test_migrations_draft_project_packages.py tests/test_draft_complete_reports.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Check actual files/dependencies first. Continue through explicit staging, commit,
normal push, PR and safe merge after required exact-head CI/reviews; verify merge.
Access denial, failed CI, unresolved material authority/domain rules or required
review are blockers to report, not bypass. ChatGPT and full source/project coverage,
broader capabilities and production readiness remain separate unfinished work.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing read AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md,
> docs/CLASSIFIRE_ARCHITECTURE.md, docs/SESSION_HANDOFF.md and accepted ADRs 0001/0002;
> inspect Git status/diff/worktrees, origin/main, PRs and CI. Preserve the conflicted
> C:\CLASSIFIRE root, unrelated changes and old package experiments; use an isolated
> worktree. Package download is merged in PR #200; do not repeat it.
> The single next task is safe new-project Draft ProjectPackage import: users
> can download selected work but cannot reopen its ZIP and continue in a new project.
> Inspect draft_project_packages, Scope import, review/Estimate contracts, reports,
> models/migrations and package UI/tests. The ZIP inspector is structural only.
> Establish complete selected-member validation and explicit local identity/lineage
> mapping. Preserve all included capability artifacts, original bytes, uncertainty,
> history and dependency links; external sources remain unresolved. Never silently
> drop unsupported members or grant authority from foreign approvals/library claims.
> Done means actual UI upload, no-write preview, explicit transactional new-project
> import, correct reopening after restart and traceable re-export for Scope-only and
> populated packages. Add service/HTTP/permission/CSRF/rollback and unsafe-archive tests;
> run affected capability/report/migration regressions with worktree PYTHONPATH and
> unique no-cache temp storage, Ruff, Mypy, Bandit, one migration head and real
> synthetic browser/archive inspection. No customer data, providers, recalculation,
> canonical writes or release. Keep docs aligned. Continue autonomously through
> implementation, validation, classification, explicit commit, normal push, PR and
> safe merge after required exact-head CI/reviews; verify merge. Report genuine
> authority/domain/access/CI/review blockers without bypassing them. Avoid speculative
> work; ChatGPT, broader capabilities and full production readiness remain unfinished.
