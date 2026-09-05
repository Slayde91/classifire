# CLASSIFIRE Session Handoff

**Verified:** 2026-09-05 (AEST).
**Shared-main baseline:** `18f5177f55458a5a1eb36b8117aea112d7a82f33`, merged
[PR #190](https://github.com/Slayde91/classifire/pull/190).
[Main CI 33952553673](https://github.com/Slayde91/classifire/actions/runs/33952553673)
passed on that exact commit: 1,124 tests, 141 warnings.
**Current P2a branch:** `feat/system-match-review-20260905` at
`C:\CLASSIFIRE\.tmp\system-match-review-20260905`, based on that main commit.
**Architecture:** approved ADR 0001 + ADR 0002, prototype-first delivery.
This checkpoint precedes P2a publication. Verify final commit/PR/checks/merge from
current Git and GitHub; local validation alone does not prove a shared-main feature.

## Start Here / Next Session

First finish P2a verification/publication if still outstanding; do not abandon its
implemented candidate-review UI. Then the **single highest-value next task is P3a:
a usable independent manual Draft Estimate workspace** over explicit saved Scope
inputs, with an optional saved candidate-review reference.

Why next: P0 editing, P1a JSON exchange and P4a PDF/XLSX reporting are merged. P2a
adds saved technical-candidate review, making a manual costing screen the missing
fourth interaction. Broad applicability (P2b) needs new physical/source criteria
and validated rules; it does not have to block an explicitly provisional manual
worksheet. This order does not declare full matching, estimating or the goal done.

### Inspect before editing

Read `AGENTS.md`, `GOAL.md`, the four current docs, ADRs 0001/0002 and current Draft
contracts. Inspect branch, HEAD/upstream, diffs/conflicts/worktrees, current remote
main and relevant PR/CI. Reconcile current source/tests before editing. Preserve
all unrelated changes and the conflicted root. Use a clean current-main worktree
after P2a publication; do not rebuild P0/P1a/P4a/P2a or seek architecture reapproval.

### P3a supported slice and decisions

- Select one saved Scope artifact/revision/hash. A candidate-review attachment is
  optional, explicit and hash-bound; keeping a candidate is not technical approval.
  Do not force users to run matching first or create a canonical Estimate/Opening.
- Start with explicitly user-entered **unit sell rates**, classified user-defined
  and provisional. Do not silently interpret them as cost plus markup or an exact
  library rate. Declare currency, unit, precision, rounding and tax treatment.
  Reuse the existing money/quantity helpers where their behavior fits; document
  the supported calculation rule before coding and test it with concrete values.
- Preserve original Scope quantities and original rate values. Any override needs
  local author/time, reason, scope and active value. Missing quantity/rate remains
  unavailable, not zero or one. Do not infer physical work from defect counts.
- Bind lines to explicit Scope service/opening IDs and unit/recovery intent. Do not
  generate duplicate shared work automatically. Refuse duplicate recovery for the
  supported case or keep ambiguous recovery unresolved; state unsupported work.
- Show priced/unpriced/omitted items and a clearly labelled partial subtotal when
  anything is unresolved. A provisional worksheet cannot appear to be a complete
  technically approved quote. Do not run pricing inference, release or reporting.
- Deliver the UI, minimum shared contract, persistence, validation and exact JSON
  download together. Save/reopen after restart, retain old revisions and mark later
  Scope/attached-review changes stale without recalculating earlier artifacts.

### Relevant implementation and prerequisites

- `services/draft_scope.py`, `draft_system_matches.py`,
  `draft_system_match_contract.py`, `draft_scope_reports.py`, `models.py` and current
  UI/templates/tests: ownership, revision/CAS, retained hashes and stale dependencies.
- `services/calculation.py`: pure `money`, `rate`, `quantity`, `calculate_line` and
  `sum_money`. Inspect behavior first: `D(None)` returns zero; `calculate_line`
  rounds unit sell to cents before multiplying. Neither silently defines all
  independent Draft semantics. Keep existing canonical behavior unchanged.
- Existing Estimate creation pins six library releases. Existing estimate-line UI
  requires a Physical Model Lock. `calculate_estimate_line`/`recalculate_estimate`
  mutate canonical Estimate records; `services/snapshot.py:build_estimate_snapshot`
  recalculates. Do not call these as read-only Draft projections or bypass guards.
- `templates/estimate.html`, `PricingLibraryRecord`, pricing import and desk-quote
  services provide presentation/provenance concepts. Desk quotes require release
  bindings and priced allowances, so are not a drop-in Draft contract.
- Current migration head is `0029_draft_system_matches`; use a new forward migration
  if new persistence requires it. Preserve earlier migration tests as historical
  scenarios and reconcile current-head/deployment fixtures explicitly.
- `scripts/run_draft_scope_demo.py` supports marked isolated SQLite storage and
  optional `--seed-technical-library`. The fixture PDF/approval/clean metadata are
  synthetic setup, not a scanner result or operational technical approval.

No customer evidence, provider, operational canonical record/lock, deployment or
release is authorized by this development task. Synthetic isolated test fixtures
may exercise boundaries. No identified external dependency blocks manual P3a.
P1b scan producer/retention/concurrent upload, P2b applicability and P3b pricing
XLSX/default/inferred-rate coverage remain required separate follow-on work.

### Definition of done and validation

1. A real authenticated synthetic browser session selects saved inputs, enters
   supported unit rates/quantities, sees meaningful provisional/unknown totals,
   records a reasoned override and saves/reopens/downloads an exact Draft revision.
2. Shared services enforce active human permissions and owner/admin access; no
   adapter duplicates calculations or creates canonical physical/Estimate state.
3. Tests cover Decimal rounding/units, zero versus unknown, bounds, partial totals,
   original/override lineage, duplicate recovery, optional/stale attachments,
   integrity, CAS, ownership, agent denial, sessions/CSRF and safe export.
4. Restart retains prior downloads. Inspect the browser and downloaded JSON against
   concrete expected arithmetic and Scope IDs. No mock-only success screen.
5. Relevant existing Draft, calculation/snapshot, physical/admission and desk-quote
   regressions plus any migration checks pass. Run Ruff, Mypy and Bandit as required.
6. Reconcile docs, classify the full diff, commit only relevant paths, push normally,
   create/update PR, check exact-head CI/review, merge safely and verify main result.

From the isolated worktree, using installed declared development dependencies:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$taskTestBase = Join-Path $env:TEMP ('classifire-estimate-' + [guid]::NewGuid().ToString('N'))
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTestBase tests/test_draft_scope.py tests/test_draft_scope_ui.py tests/test_draft_system_matches.py tests/test_draft_system_match_ui.py tests/test_snapshot.py tests/test_desk_quote.py tests/test_physical_api_boundary.py tests/test_initial_canonicalisation_boundary.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src --no-incremental
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -r src -ll
```

Add the new feature tests and current migration checks after inspecting their names.
Local PostgreSQL skips require hosted/disposable PostgreSQL evidence; do not label
SQLite checks production concurrency proof. Do not connect to an operational DB.

## Current local changes and evidence

P2a adds shared review services/strict contract, two revision tables and migration
0029, thin UI adapter/templates/navigation, stable retrieval ordering, synthetic
fixture/launcher, tests and documentation. Detailed measured checks are in
PROJECT_STATE.md; Git/PR is authoritative for its final publication status.

Protected `C:\CLASSIFIRE` remains at `de0cc5a` on
`gpt/phase8-linked-original-images`, CHERRY_PICK_HEAD
`c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`: 46 unstaged modified paths, 14 staged
additions and four DU conflicts, plus untracked recovery material. Do not resolve,
reset, clean, broadly stage or publish from it. The four conflicts are linked-visual
service/evidence files and their tests. They are unrelated to this increment.

Prior P0/P1a/P4a worktrees/demos and `.tmp/project-package-draft-20260905` are preserved.
The latter contains three untracked candidate files (contract/service/test), not a
shipped full package implementation. Its historical 22 tests are not qualification
against current main. Demo databases, evidence PDFs, browser session cookies,
screenshots and receipts remain outside the feature diff under `.tmp`.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE from verified repository state. Read AGENTS.md, GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md, docs/CLASSIFIRE_ROADMAP.md, docs/SESSION_HANDOFF.md, ADRs 0001/0002 and current Draft contracts. Inspect branch/HEAD/upstream, status/diffs/conflicts/worktrees, origin/main and relevant PR/CI before editing. Preserve the conflicted C:\CLASSIFIRE root, all unrelated changes, prior demos and package candidate; use an isolated current-main worktree. First finish P2a publication if outstanding; do not redo merged work.

Then deliver one task: P3a, a working independent manual Draft Estimate UI over an explicit saved Scope revision, with optional hash-bound candidate-review attachment. It is next because editing, JSON exchange, reports and candidate review already provide useful interactions; manual provisional costing adds the fourth without waiting for broad applicability rules. Reuse Draft ownership/revision/hash/staleness patterns and inspect services/calculation.py Decimal helpers, models.py, estimate.html and existing Draft/snapshot/desk-quote/physical-boundary tests. D(None) becomes zero, canonical Estimate creation pins six releases, line writes require a Physical Model Lock and build_estimate_snapshot recalculates: do not use these to bypass Draft boundaries.

Define a bounded unit-sell-rate/currency/unit/rounding/tax contract, then implement its shared service and real UI together. Preserve original quantities/rates and attributed reasoned overrides, keep unknowns unpriced, show partial/omitted work, prevent supported-case duplicate recovery, and never turn a kept candidate into technical approval. Save/reopen after restart and download exact JSON revisions; upstream changes flag stale without overwriting. No external blocker is known for synthetic manual inputs; real scanning, full applicability and pricing XLSX/inferred defaults remain separate required work. No speculative framework or real customer/provider/canonical/lock/deployment/release operation.

Done means observed browser entry/calculation/override/save/reopen/restart/download with correct arithmetic/IDs plus focused Decimal, unknown/unit/recovery, lineage, stale/CAS, permission/CSRF/integrity tests. Run relevant existing Draft, snapshot, desk-quote and physical/admission regressions, any forward-migration checks, Ruff, Mypy, Bandit and exact-head CI. Set PYTHONPATH to the isolated src and use unique pytest temp storage with cache disabled. Update the aligned docs, classify/preserve unrelated changes, commit explicit paths, push normally, PR and merge after required checks/review pass; verify merge/main CI. Continue autonomously, stopping only for a concrete blocker. Report limitations honestly; this does not complete the full product goal.
```
