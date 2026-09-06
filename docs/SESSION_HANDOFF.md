# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06. Worktree `C:\CLASSIFIRE\.tmp\defect-xlsx-mapping-20260906`, branch
`feat/defect-xlsx-mapping-20260906`, shared baseline
`96680f4ce1b26da5da599bd5cb7894af8d3b28de` (merged PDF graph review PR #209).
Baseline required CI passed 1,564 tests; main run 34027941914 succeeded. Verify current
head/upstream, diff, PR and checks before assuming this new Excel source checkpoint
has been published. ADRs 0001/0002 remain accepted; the full production goal is active.

## Current increment

The Excel defect-report path retains/scans a bounded XLSX, shows typed cells and
supported PNG/JPEG occurrences, accepts explicit sheet/header/column/row choices,
and drafts only the selected item kinds. The existing graph editor handles shared
or blank openings and multiple services without automatic relationships or quantity
inference. A human explicitly selects row/image claims, previews and separately
confirms one atomic Scope v5 revision. Formula/ambiguous/missing inputs stay unresolved.

v5 extends the same evidence_refs union with typed row/cell/image provenance; earlier
PDF claims remain readable. Changed/deleted items retain historical review warnings,
re-review updates only a new revision, imports force unverified claims, and selected
packages inventory the same references with original source bodies external. Four
report profiles have conditional v5 renderer versions; old outputs remain exact.
Migration 0038 adds only DraftScopeXlsxSource and reuses the shared retained-file
boundary. A pure shared envelope builder checks the existing 288 KiB budget during
preview and final save. No AI provider, canonical physical write, lock, deployment
or release is added; the existing pricing parser's default behavior stays unchanged.

Changed components: workbook worker/static-picture parser and pure contracts, new
source model/migration/lineage, shared Scope/evidence/source services, workbook router,
shared graph/review templates and JavaScript, four-profile renderers, isolated demo
allowlist and focused source/UI/report/migration tests. See
[DRAFT_SCOPE_XLSX_V1_CONTRACT.md](./DRAFT_SCOPE_XLSX_V1_CONTRACT.md).

## Validation checkpoint

Parser 49, migration/lineage 30, UI/template 19 and mixed workbook/PDF output 20 tests
have passed. The new router's static checks and both JavaScript syntax checks passed.
The first real Chrome journey passed 11 checkpoints: later worksheet rows, shared
opening/two services, separate blank opening, unknown/zero/formula distinctions,
explicit repeated-image links, preview/edit-back/confirm, v5 JSON, three report pairs,
selected ZIP and changed/deleted-item history. Earlier downloads stayed byte-identical;
no browser page errors were recorded. Scope+System is covered by pure output tests;
the guarded PostgreSQL demo cannot seed a technical release and that guard was preserved.

Final-code fresh review saved r5; a second actual restart/fresh login preserved r2/r5
JSON, both PNGs, all six report files and ZIP hashes. Pure size tests passed 3 cases;
full Ruff/Bandit and Mypy on 199 source files passed; Alembic has one head 0038. The rendered Scope/
Complete reference pages and worksheet ranges were inspected and readable. A separate
worksheet visualization utility exited nonzero without a diagnostic after producing
both inspectable PNGs; source workbook hashes stayed exact. See PROJECT_STATE for this
inspection-tool limitation and read-only canonical counts (all eight models zero).

All 30 new PostgreSQL workflow cases passed across focused runs. Two new test-only
audit expectations were corrected: the injected failure is confined to save, and the
HTTP journey asserts one save plus two download events. No runtime guard or assertion
was weakened. The final remaining-workflow and legacy Scope/import/PDF UI group
passed **110 tests** in 310.35 seconds. Combined focused groups total **254 passed**,
no skips, one existing Alembic warning. Independent code/document reviews found no
blockers. Required PR CI and verified merge remain publication gates at this source
checkpoint; inspect the live branch/PR rather than inferring its future merge here.
Publication target: origin/feat/defect-xlsx-mapping-20260906 into main.

## Preserved local changes and runtime context

Preserve the conflicted `C:\CLASSIFIRE` recovery root. Read-only recheck confirms
HEAD `de0cc5a` on `gpt/phase8-linked-original-images`, 46 unstaged tracked changes,
14 staged additions and four DU conflicts. Untracked/ignored recovery content was
not fully enumerated. Do not clean/reset/resolve/stage or publish from that root.
Preserve earlier worktrees, demos, scanners, receipts and the supplied logo.

New synthetic demo is `http://127.0.0.1:8817/scopes`, marked directory
`C:\CLASSIFIRE\.tmp\defect-xlsx-demo-20260906`, separate database
`classifire_draft_xlsx_report_demo` on loopback port 15432 and scanner port 13311. Verify exact
process command lines and scanner freshness before use/restart. Only this demo's
launcher may be stopped during its proof; start background processes hidden.
Log files belong outside the marked data directory before first launch. Read synthetic
login constants locally in scripts/run_draft_scope_demo.py; never print session keys,
cookies or credentials. Existing 8816 PDF/8815 pricing and older demos remain untouched.

Receipts and exact synthetic downloads/screenshots are under
`C:\CLASSIFIRE\.tmp\defect-xlsx-review-artifacts-20260906`. They are local evidence,
not source files to commit. The separate destructive fixture database is
`classifire_containment_test`; verify its exact loopback endpoint, ownership and lack
of other test activity before using the cleanup opt-in. Run such suites serially.
Never use a demo or customer database for destructive tests.

## Start Here / Next Session

**First task after the Excel increment is verified and merged:** implement one
optional, source-bound PDF text/image suggestion interaction feeding the existing
Draft graph editor. This advances interpretation after both manual upload paths are
usable, while preserving the human review and deterministic save boundary. Do not
rebuild manual Scope, PDF page review, Excel mapping, pricing selection or packages.

**Prerequisites/dependencies:** inspect repository/Git/CI first. If this Excel branch
has a supported-path failure or unfinished publication, finish that prerequisite
before starting the next slice. Read the accepted ADRs, current PDF/XLSX contracts,
existing inference ports/journal and proposal review protections. The existing Phase8
runners require estimate-bound manifests and canonical identities; they are not directly
compatible with Draft inputs. Reuse compatible protections through a small Draft-specific
adapter and shared graph services. Never create canonical records, spoof Phase8 manifests
or weaken validators to reuse a runner. Synthetic evidence and a controlled adapter
suffice for development. Real customer/provider workflows,
credentials, deployment and canonical state changes need separate authorization.
Lack of a real provider must remain explicit, not be disguised as working AI.

**Relevant files/components:** services/draft_pdf_intake.py, draft_scope.py,
draft_scope_evidence.py, draft_scope_xlsx.py, the PDF/Scope routers and shared graph
editor; services/phase8_visual_proposal.py, phase8_report_assessment_controller.py,
phase8_report_assessment_input.py and execution_journal.py for compatible port/protection
patterns, not ready-made Draft runners/storage. Inspect their focused tests and the
retained PDF source/authority tests.
Inspect actual file locations and contracts before editing. Future suggestions must
not become a separate physical model, pricing path or autonomous approval mechanism.

**Definition of done:** a synthetic retained page and its extracted text can produce
clearly labelled, bounded proposed defects/openings/services plus source-linked
observations and unresolved questions in the existing editor. The user can inspect,
change or reject suggestions and explicitly confirm a valid Draft revision. No
unattended canonical writes, inferred scale/quantity-one or technical approval. Preserve
manual operation without AI, exact evidence/revision bindings, stale/revoked-source
refusal, historical reports/packages and visible uncertainty. Demonstrate the supported
browser journey and restart; identify real-provider accuracy/operational proof as
unverified until separately authorized and measured. Do not implement speculative
bulk agents, model tuning, a new scheduler or unrelated T1-T14 pricing work.

**Validation:** force source imports to the isolated worktree; unique temp output;
serial PostgreSQL tests only after exact disposable DB verification. Add targeted
proposal/source/authority tests, then affected Scope/PDF/XLSX/import/package/report/
client regressions, browser/restart and inspected outputs. Use current fixture names:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$taskTestTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('scope-tests-' + [guid]::NewGuid())
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTestTemp tests/test_draft_scope_xlsx.py tests/test_draft_pdf_scope_review.py tests/test_draft_scope.py tests/test_draft_package_import.py tests/test_draft_workbook_evidence_outputs.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Do not copy credential values from this document; configure the existing guarded test
URL/opt-in only after verification. Required workflow is
`.github/workflows/pull-request-validation.yml`. Preserve assertions and authority
checks. Classify the exact diff, commit only reviewed paths, push normally, open/update
the PR and merge only after required checks/reviews pass; verify the resulting merge.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from repository evidence. Before editing, read AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/CLASSIFIRE_ROADMAP.md and docs/SESSION_HANDOFF.md; inspect branch/worktrees,
> current main, diff, PR/CI and relevant source/tests. Preserve the conflicted
> C:\CLASSIFIRE root, unrelated local changes and existing demos; use an isolated
> current-main worktree. Verify the Excel defect-mapping increment is delivered and
> finish any outstanding validation/publication prerequisite first. Then implement
> one optional source-bound PDF text/image suggestion interaction through the existing
> Draft editor: reuse draft_pdf_intake, draft_scope/evidence services, shared UI,
> compatible inference protections through a small Draft-specific adapter and retained evidence.
> Do not create canonical records, spoof Phase8 manifests or weaken their validators. This is next
> because PDF/Excel human review now supplies a usable deterministic foundation for
> interpretation. Use synthetic evidence and a controlled adapter; do not run real
> customer/provider workflows, deploy or create canonical state without authorization.
> Done means reviewable proposed defects/openings/services and unresolved questions,
> exact source/revision bindings, reject/edit/explicit-save behavior, manual operation
> without AI, preserved history and no invented quantities or approval. Test no-write
> proposals, invalid/stale/foreign/revoked inputs, affected Scope/PDF/XLSX/package/report/
> client behavior, actual browser/restart and inspected outputs; run Ruff, Mypy, Bandit
> and single-head migration checks with isolated imports and guarded serial disposable
> PostgreSQL tests. Avoid speculative infrastructure or unrelated pricing work. Continue
> autonomously through implementation, validation, change classification, explicit-path
> commit, normal push, PR and merge when required checks/reviews pass; verify the merge
> and update the four continuity documents with measured facts and any genuine blocker.
