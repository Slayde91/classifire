# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-07 on shared main
`af822249b02cf197be62a6e03af32d409a3524fc`, merge commit for PR #216.
Feature head `c70a3add36b35792dd17c8de2ed8ebe80caf7776` passed required run
34054381404 in 17m58s: 1,859 tests, full Ruff, Mypy on 207 source files,
Bandit and one Alembic head. PR #216 is merged. Its post-merge main run
34055366570 had started at the last check; verify the final result rather than
assuming it.

ADRs 0001/0002 remain accepted. CLASSIFIRE is still one modular deterministic
application with independently callable Scope, System Match, Estimate and
Reporting capabilities and optional bounded AI. OpenClaw is transitional.
PR #216 adds no AI, orchestration, persistence, migration, route, UI, prediction
or authority.

## Relevant local changes and open issues

The merged early-T13 module
`src/classifire/services/draft_pricing_evaluation_contract.py`:

- binds synthetic/normalized Firefly B members to exact dataset, source,
  profile, row and target hashes plus availability;
- computes transitive lineage groups from system identity, alias,
  configuration cluster, source derivation and version lineage;
- requires each complete group to stay in training, validation or holdout and
  requires all three splits;
- freezes feature availability and accepts only declared technical,
  independently sourced A/labour or training-observation inputs;
- rejects held-out/validation inputs, target descendants, policy tampering,
  changed hashes, foreign Drafts, duplicate JSON keys, noncanonical bytes,
  stale parents and caller-supplied replay history;
- records actor/time, canonical manifest hash and explicit zero downstream
  effects.

Twelve focused contract tests passed. The existing
pricing/profile/review/UI/client/migration regression selection completed at
100%. Repository-wide Ruff and Bandit passed locally; the changed module passed
Mypy. Local full Mypy lacked installed ReportLab/PyYAML stubs, while exact PR CI
installed them and passed all 207 source files.

The contract is not a saved holdout product feature. Reviewed normalized B
observations and resolved system/configuration identities do not exist yet, so
there is no honest roster to persist. No evaluation, target reveal, calibration,
threshold or accuracy claim was produced.

The clean implementation worktree
`C:\CLASSIFIRE\.tmp\pricing-evaluation-lineage-20260907` remains on
`feat/pricing-evaluation-lineage-20260907` at the merged feature commit. This
documentation reconciliation was prepared in
`C:\CLASSIFIRE\.tmp\pricing-lineage-docs-20260907`. Verify its current
publication state at the start of the next session.

The recovery root `C:\CLASSIFIRE` remains on
`gpt/phase8-linked-original-images` at `de0cc5a`, with 46 unstaged tracked
changes, 14 staged additions and four DU conflicts at last inspection. Do not
reset, clean, resolve, broadly stage or publish from it. Preserve all unrelated
worktrees. The synthetic prototype listener on port 8819 was still running at
the last check under process 37032; it is not production.

## Start Here / Next Session

**First task:** implement one reviewed Dataset A row observation and
product/material/labour/service mapping through the existing pricing UI.

**Why this is next:** users can upload, profile and review a general price
workbook, but the approved profile still cannot create a governed normalized
row. This is the shortest user-visible step toward component and labour costing.
It also creates the real row identity/provenance pattern that B mapping and a
persisted T13 roster will later reuse.

**Prerequisites and dependencies:** inspect current Git, worktrees, GitHub
main/PR/CI and these documents before editing. Confirm PR #216 and its
post-merge run. Use a new clean current-main worktree. Reuse the existing
Draft pricing source/profile/decision, canonical JSON/hash, ownership,
PostgreSQL locking, exact-byte read, audit and download patterns. Require a
current `approve` decision on an exact `general_pricelist` profile. Use
synthetic workbooks only because actual A layout, rights and commercial
semantics remain unverified.

**Relevant files/components:**

- `src/classifire/models.py` around `DraftPricingSource*`, `Product` and
  `LabourComponent`;
- `src/classifire/services/draft_pricing_contract.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `src/classifire/draft_pricing_ui.py` and
  `src/classifire/templates/draft_pricing.html`;
- migrations 0040/0041 and their deployment-lineage registry;
- current pricing profile/review/UI/client/migration tests;
- the new T13 contract, roadmap T5/T6/T12/T13, architecture and project state.

**Definition of done:** an authorized user can open a current approved A
profile, inspect exact normalized row values and source cells, choose one row,
classify it as product, material, labour or service, supply the minimum stable
mapping identity and review reason, preview without writing, explicitly save an
append-only Draft observation/mapping, reopen it after restart and download the
exact canonical JSON. The record must bind Draft, dataset/version, source/hash,
profile/revision/hash, approval-decision hash, worksheet/header/row, exact cells
and row hash, price meaning, unit, currency, tax basis, date,
inclusions/exclusions, reviewer/time and explicit unresolved fields.

Stale source/profile/decision, changed row/cells, duplicate/replayed save,
foreign access, invalid classification/unit/basis, unsupported formula/error
cells and corrupted stored JSON must fail closed. A newer source/profile must
leave old history intact and visibly stale. The save must not create or activate
`Product`, `LabourComponent`, `LibraryRelease`,
`PricingLibraryRecord`, `TechnicalVariant`, an Estimate change, a system
match, a prediction or a release.

Demonstrate the real browser interaction with a synthetic A workbook, inspect
the rendered page and exact download, restart the application and reopen the
same record. Add meaningful contract/service/UI/migration and compatibility
tests. Update state/architecture/roadmap/handoff only from measured evidence.

**Validation commands:** resolve paths and environment first, then use the
explicit disposable PostgreSQL database.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
$taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-row-review-tests-' + [guid]::NewGuid())
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTemp <targeted tests>
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

**Blockers/decisions needing validation:** actual A workbook fields, ownership,
redistribution rights, price meanings, pack/unit/date/tax/inclusion semantics
and supported counts are unknown. Do not guess them or use customer data.
Current profile review is effectively administrator-only because
`pricing_manager` lacks owned Draft project/Estimate reads; do not broaden
global visibility in this slice. Decide only the minimum synthetic mapping
vocabulary needed for the demonstrated row, keeping unknowns unresolved.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. First inspect AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, architecture, roadmap, handoff, current
> Git/worktrees and GitHub main/PR/CI; confirm PR #216 and its post-merge run.
> Preserve the conflicted C:\CLASSIFIRE root and unrelated local changes; use a
> clean current-main worktree. Implement the single highest-value next task: a
> working UI to review one Dataset A workbook row and save/reopen/download an
> immutable Draft product/material/labour/service observation/mapping bound to
> the exact approved profile, decision, source cells and row hash. Preview must
> not write; stale/changed/replayed/foreign/corrupt inputs must fail closed; old
> history must remain. Do not activate Product/Labour/pricing libraries, change
> an Estimate, infer a price, match a system, use customer data, add AI/OpenClaw
> work, deploy or release. Use synthetic XLSX, PostgreSQL locking, existing
> pricing/audit/hash/download patterns, focused service/UI/migration/no-side-
> effect tests, real browser/restart/exact-download proof, Ruff, Mypy, Bandit,
> one Alembic head and required CI. Inspect and classify the full diff, preserve
> unrelated work, then autonomously commit, push, open/update a PR and merge
> only when checks and repository rules allow. Update project documents from
> verified results; avoid speculative breadth.
