# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-07 in
`C:\CLASSIFIRE\.tmp\pricing-source-profiles-20260907` on branch
`feat/pricing-source-profiles-20260907`, based on `origin/main`
`ae6ca72a95cd623f5088c9adfb6729d6fa276770` (merged PR #211). The branch contains
the bounded A/B pricing-source profile implementation and aligned documentation.
Treat it as candidate work until its own commit, push, PR, required CI and merge are
verified live.

ADRs 0001/0002 remain accepted. The deterministic modular core, independent
capabilities and optional bounded AI remain unchanged. This increment uses no AI or
OpenClaw and grants no canonical, technical, commercial, deployment or release
authority.

## Relevant local changes and verified evidence

The implementation extends existing pricing/source abstractions:

- `DraftPricingSource` gains nullable stable dataset ID, explicit A/B kind and source
  version fields; historical rows remain unclassified and compatible.
- `DraftPricingSourceProfile` and migration 0040 retain append-only, source-bound,
  hash-chained unapproved profile revisions.
- pricing contracts/services validate explicit dataset kind and price meaning, expose
  mapping/anomaly gaps, recheck exact clean bytes and reject stale/replayed/corrupt or
  foreign inputs.
- pricing UI supports A/B declaration, profile preview, explicit save, history, reopen
  and exact JSON download while keeping existing row application separate.
- the guarded demo launcher accepts the separately named synthetic profile database.

Changed paths are limited to the pricing UI/template/services/contracts, models,
migration/lineage, guarded demo launcher, targeted/new tests and continuity documents.
Use `git status`, `git diff --stat` and explicit-path staging to reclassify before
publication. Temporary demo scripts, logs, workbooks, downloads and database state are
under `C:\CLASSIFIRE\.tmp` and must not be committed.

Local evidence: 85 targeted pricing/profile/UI/client and migration/lineage tests
passed; full Ruff, full Mypy on 205 source files, Bandit, diff check and single-head
Alembic passed. Real loopback HTTP and ClamAV proof created the Draft through UI, seeded
one Estimate through shared domain services, then saved A/B profiles through HTTP,
retained A source v2 and preserved the Estimate revision; restart/fresh login preserved
both exact download hashes. Native visual inspection was blocked by the browser helper's
Windows sandbox setup failure, so repeat a visual layout check when available. Exact-head
PR CI remains mandatory.

The recovery root `C:\CLASSIFIRE` remains at `de0cc5a` on
`gpt/phase8-linked-original-images`, with 46 unstaged tracked changes, 14 staged
additions and four DU conflicts. Do not reset, clean, resolve, stage or publish from it.
Preserve unrelated worktrees and earlier demos.

## Start Here / Next Session

**First task:** after verifying that the A/B profile increment is merged and green,
implement the smallest T12 pricing-source profile review interaction.

**Why this is next:** users can now retain and interpret source A/B, but every profile
is permanently unapproved. A human review decision is the minimum governance step
before any reviewed row import, component/activity mapping, Firefly-system mapping,
coverage or estimation work. It also keeps the next slice visible and testable.

**Prerequisites and dependencies:** inspect current Git/GitHub/CI and repository docs
before editing. Confirm migration head 0040 and the profile services actually exist.
Read roadmap T1/T5/T7/T12/T13 and the technical-corpus/dual-pricing design. Use a clean
isolated current-main worktree. Reuse current proposal/review, permission, audit,
revision and exact-download patterns where compatible; do not create a second generic
review framework. Define who may review and what states/reasons are allowed from
existing authority rules. If the profile increment is not merged, finish its reviewed
publication first rather than rebuilding it.

**Relevant files/components:** `src/classifire/models.py`, migration 0040,
`services/draft_pricing_contract.py`, `services/draft_pricing_intake.py`,
`draft_pricing_ui.py`, `templates/draft_pricing.html`, existing proposal-review
contracts/services/models/UI, pricing/profile tests, PROJECT_STATE, architecture,
roadmap and this handoff.

**Definition of done:** an authorized user can open an exact saved profile, record one
immutable approve/reject/request-revision decision with a bounded reason, inspect its
actor/time/profile hash and history, download the exact decision, and see stale/current
status after a newer profile revision. Unauthorized, foreign, corrupt, stale and replayed
decisions fail closed. Original profile bytes/history remain unchanged. Approval does
not import rows, activate a pricing library, approve technical suitability, match a
system, infer a price, modify an Estimate or release anything.

**Validation:** add contract/service/database/permission/stale/replay/integrity tests;
run existing pricing/profile/UI/client and migration/lineage regressions serially on
the verified idle disposable PostgreSQL database. Exercise the real synthetic UI,
restart, reopen and exact decision download; perform visual inspection when the browser
helper works. Run full Ruff, Mypy, Bandit, `git diff --check`, one Alembic head and the
required PR workflow. Preserve unrelated changes and do not use customer data, live
providers, deployment, canonical locks/writes or OpenClaw retirement work.

Useful validation setup after verifying local paths and the disposable database:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
$taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-review-tests-' + [guid]::NewGuid())
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTemp tests/test_draft_pricing.py tests/test_draft_pricing_profiles.py tests/test_draft_pricing_ui.py tests/test_draft_client_pricing.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

**Blockers/decisions needing validation:** actual A/B source layouts, rights and
commercial semantics remain unknown; use synthetic inputs. The exact reviewer role and
whether request-revision is terminal or supersedable must be derived from existing
review authority contracts before schema work. T13 lineage-aware holdout policy must be
sealed before any price-prediction feature selection or evaluation, but does not block
this review-only interaction.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/CLASSIFIRE_ROADMAP.md, docs/SESSION_HANDOFF.md, current Git/worktrees and GitHub
> PR/CI. Preserve the conflicted C:\CLASSIFIRE root, unrelated changes and demos; use a
> clean isolated current-main worktree. Verify the A/B pricing-source profile increment
> and migration 0040 are merged; if publication is genuinely unfinished, complete that
> prerequisite first. Then implement the single highest-value next task: a bounded T12
> human review interaction for an exact saved pricing-source profile. An authorized user
> must approve, reject or request revision with a reason; retain immutable actor/time/
> profile-hash history, stale status, reopen and exact download. Reuse existing pricing,
> proposal-review, permission, audit and revision services. Do not import rows, activate
> a library, match systems, infer prices, alter Estimates, use real sources/providers,
> deploy or weaken authority gates. Add meaningful permission/stale/replay/integrity and
> compatibility tests; prove the synthetic UI through restart and exact output, run
> Ruff/Mypy/Bandit/diff/Alembic and guarded serial PostgreSQL regressions. Reconcile docs
> from evidence, classify the full diff, stage explicit paths, commit, push, open/update
> a PR and merge only after required CI/review passes; verify the resulting merge. Avoid
> speculative bulk, recipe, calibration or OpenClaw work.
