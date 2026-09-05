# CLASSIFIRE Session Handoff

## Start Here / Next Session

Inspect before editing: AGENTS.md, GOAL.md, PROJECT_STATE.md, roadmap, architecture,
accepted ADRs 0001/0002, relevant contracts, branch/status/diff/worktrees and remote
main/PR/CI. Repository evidence outranks this prepublication checkpoint. Use an
isolated worktree; never adopt or repair the conflicted legacy root implicitly.

**Current work:** first P2b measured-limit review UI in
`C:\CLASSIFIRE\.tmp\draft-applicability-review-20260906`, branch
`feat/draft-applicability-review-20260906`, starting at main
`25510565aac69ce7d0b6402423caac251a266236` (merged PR #194).
That baseline includes PDF intake and the supplied logo; main CI 33982467430 succeeded
with 1,354 tests/141 warnings. Do not redo it. Current measured-limit publication
must be checked from its live PR before assuming it is finished or outstanding.

**First task:** finish this branch's exact-head verification/publication if still
outstanding, then deliver one P3b interaction: **pricing XLSX preview -> explicit
Draft-rate selection with source cell provenance**. This is next because all four
capabilities have bounded UI paths, but Estimate rates are still manual values plus
free-text notes; the existing pricing importer reads CSV and can activate library
state. A safe, source-bound rate-selection interaction adds more user value than
polishing text retrieval or treating two numeric checks as complete applicability.

Relevant files/components:

- `src/classifire/importers/pricing.py`, `models.py` (PricingLibraryRecord), current
  pricing UI and workbook-reading utilities: inspect/reuse useful parsing concepts,
  not the CSV importer's automatic library writes from an upload handler.
- `services/draft_estimates.py`, `draft_estimate_contract.py`, `draft_estimate_ui.py`,
  templates and Estimate report snapshot/renderers: preserve v1 history, original
  rates, reasoned overrides, missing work, units and downstream stale semantics.
- Existing `services/storage.py`, `malware_scan.py`, `draft_pdf_intake.py` and worker
  isolation patterns: reuse exact-byte/scanning/ownership controls, with explicit XLSX
  archive/parser limits. Do not treat PDFs and ZIP-based spreadsheets as identical.
- `DRAFT_CONSTRAINT_REVIEW.md` and match contracts: technical review stays independent;
  selected pricing must not claim compatibility or run technical approval.

Prerequisites/dependencies: supported workbook schema/mapping with explicit sheet/cell
locations, exact retained bytes, safe XLSX parsing and draft-only permission boundary.
Use a synthetic workbook and disposable storage/database. No customer pricing file
or permission to process Package 14/customer evidence is supplied. A real provider,
operational DB, canonical library activation, lock, deployment or release is outside
this task. Ambiguous supplier units/recovery/technical semantics must remain unresolved;
ask only if an actual required product rule cannot be established from repository evidence.

Definition of done: the real UI uploads a supported synthetic workbook, previews
explicit mapped rows/cells and unknowns, applies one selected compatible-unit rate to
one supported Draft line without activating a canonical library, preserves original
and override history, saves/reopens after restart and downloads exact provenance.
Old Draft/Estimate/report bytes remain unchanged. Do not implement all supplier formats
or inferred pricing methods before this usable slice; record those remaining gaps.

Validation: inspect actual test paths and dependency state first. Add targeted
workbook/limit/formula/archive-safety, provenance, unit/override, stale-save and
ownership/CSRF cases. Run relevant Draft Estimate/report, intake/storage and match
regressions, inspect the browser and downloaded JSON/PDF/XLSX where affected, then
Ruff/Mypy/Bandit, one Alembic head, and all required exact-head GitHub checks.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider `
  --basetemp <new-unique-temp-directory> <verified-relevant-test-paths>
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

PDF/quarantine tests use guarded `classifire_containment_test` on loopback 15432 with
explicit destructive-test opt-in, never `classifire_draft_pdf_demo` or an operational
DB. Do not run concurrent reset suites on that DB. Local Mypy used installed lifecycle
stubs on PYTHONPATH; CI installs dev/postgres dependencies. The measured-limit demo
uses its own SQLite file and does not require a scanner or AI.

## Current increment and measured evidence

Shared field snapshot + technical publication v3; match v2 partial measurement review;
existing revision append/CAS reused; UI/strict form validation; versioned synthetic
P2B fixture and tests. No migration, new framework, agent or dependency. AGENTS.md
already matches approved architecture/prototype priority and required no rewrite.

New service/HTTP/dependency tests: 24 passed, one existing Starlette warning (14.06s).
Earlier existing candidate/publication/UI regression: 76 passed, one warning (139.62s).
Chrome demonstrated within/outside/unknown results, exact old downloads and actual
restart. Broader/static and publication results belong in the final checkpoint below
and live PR; do not infer success from this list.

Synthetic demo: `http://127.0.0.1:8804/scopes`; data `.tmp/constraint-demo-20260906`;
receipts/JSON/screenshots `.tmp/constraint-review-artifacts`. Correct logo verified
by exact served-byte hash and rendered inspection. Existing P2A/PDF demos remain intact.
Measurement outcomes are partial unapproved claims; full applicability is unfinished.

## Local change classification and open issues

Current branch: measured-limit source/UI, publication snapshot, demo/tests and relevant
docs only. Before staging, inspect the complete diff and stage explicit paths.
Protected root remains `de0cc5a` / `gpt/phase8-linked-original-images`, CHERRY_PICK_HEAD
`c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`: 46 unstaged modifications, 14 staged
additions, four DU conflicts. Preserve all as unrelated recovery evidence.
`.tmp/project-package-draft-20260905` retains three untracked contract/service/test
candidate files; historical tests do not qualify them as shipped. Preserve the original
logo and prior worktrees/demos. Synthetic data, cookies, logs and browser tools stay
outside Git. No current technical/access blocker to this branch's publication is known.

Remaining product work includes full physical/technical coverage, pricing workbook
and inference methods, report profiles, complete ProjectPackage import/export and
ChatGPT integration. Production gates/retention/privacy/operational assurance remain
unproven; no full product goal completion or OpenClaw retirement is claimed.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE from repository evidence. Before editing, inspect AGENTS.md, GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md, docs/CLASSIFIRE_ARCHITECTURE.md, docs/SESSION_HANDOFF.md, ADRs 0001/0002, branch/HEAD/upstream/status/diff/worktrees, remote main and current PR/CI. Preserve the conflicted C:\CLASSIFIRE root, unrelated changes, original logo, prior demos and ProjectPackage candidate. Finish feat/draft-applicability-review-20260906 publication only if outstanding; then use isolated current main. Do not redo merged manual Scope/import, PDF review, candidate review, manual estimates/reports or measured-limit review.

Deliver one task: P3b pricing-XLSX preview and explicit Draft-rate selection with retained source/sheet/cell provenance. Current importers/pricing.py consumes CSV and can write active library state; Draft Estimate rates have manual values/free-text source_note. Inspect models/PricingLibraryRecord, existing workbook/storage/malware/parser controls, draft_estimates.py, draft_estimate_contract.py, draft_estimate_ui.py, templates, reports and tests. Reuse them; do not expose automatic canonical import as a web upload. Define only the supported synthetic workbook mapping, archive/parser limits, source lineage, units and draft-only permissions needed for the UI. No customer pricing, real provider, operational DB, canonical activation/lock, deployment or release. Unknown technical or recovery rules stay unresolved; selecting a rate never proves compatibility.

Done: upload/preview explicit mapped rows and cells, select one rate for a supported Draft line, preserve original/override history and missing values, save/reopen after actual restart, download exact provenance, and preserve older artifacts. Test file safety, formulas, units, provenance, authority, stale saves and downstream history; run relevant intake/Estimate/report/match regressions, inspect affected outputs and browser, run Ruff/Mypy/Bandit/one Alembic head and full required CI. Verify test paths/environment first; isolate destructive test DBs from demos. Reconcile docs, classify/stage only relevant changes, and continue autonomously through implementation, validation, commit, normal push, PR and merge when exact-head checks/reviews pass; verify merge/main CI. Avoid speculative supplier formats or inference before this usable slice. Stop only for a concrete blocker. The full platform goal remains active after this increment.
```


## Final local verification checkpoint

Broader measurement/candidate/publication/Estimate/report regression: **241 passed,
1 existing Starlette/httpx warning** (364.94 seconds). Counts overlap earlier runs;
do not sum them. Final Ruff, Mypy (169 source files), Bandit and one Alembic head
(0032) passed. No migration or new dependency. Browser/restart and exact historical
JSON/served-logo checks passed. Final documentation-link/whitespace/diff classification
precedes publication. Exact-head hosted CI and merge/main CI remain to be verified
from the branch PR; this checkpoint does not preclaim their result.
