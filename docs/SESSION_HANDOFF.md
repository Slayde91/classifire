# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09.

- Shared `origin/main` is
  `3a715d0d27f07a9c072e22db428f8f91d93f1642`, merge commit for PR #232.
- Current isolated worktree:
  `C:\CLASSIFIRE\.tmp\draft-pricing-quantity-basis-20260909`.
- Current branch: `feat/draft-pricing-quantity-basis-20260909`, based exactly on
  that shared-main commit.
- The branch contains the locally verified governed T10 quantity-basis candidate.
  It is not shared implementation until reviewed and merged.
- The recovery root `C:\CLASSIFIRE` remains on
  `gpt/phase8-linked-original-images` at `de0cc5a` with extensive staged,
  unstaged, conflicted and untracked recovery material. It was not edited, reset,
  cleaned, resolved, broadly staged or published.
- ADRs 0001/0002 remain accepted: one modular deterministic application, independent
  Scope/System Match/Estimate/Reporting capabilities, portable artifacts, bounded
  optional AI and transitional OpenClaw.

## Current candidate and open issues

The candidate adds the first purpose-specific, append-only
`DraftPricingQuantityBasis` and migration
`0046_draft_pricing_quantity_bases`.

An authorised pricing reviewer can:

1. open a T9-eligible bottom-up target;
2. select a service with an explicit quantity and matching unit from the current
   immutable Scope revision;
3. preview the exact binding without a database write;
4. explicitly save canonical hash-bound JSON;
5. reopen current/stale history and download the exact record;
6. let the existing T10 proposal calculate only from the newest current compatible
   saved basis.

The record binds Scope revision/hash, service identity/quantity/unit/evidence state,
technical release/target/recipe hashes, exact recipe link and requirement, reviewer,
UTC time and reason. Changed Scope, recipe link, requirement, unit or hashes makes
history stale. Foreign, missing, changed, replayed, corrupt and incompatible inputs
fail closed. The browser rejects the old typed-quantity fields. The earlier manual
preview remains only as explicit `quantity_source="manual_preview"` compatibility
behavior for tests and comparison.

The candidate adds no Estimate mutation, technical approval, pricing-library
activation, evaluation, canonical physical write, release, AI or OpenClaw authority.
It does not add yield, productivity, waste, pack, recovery, margin, comparables or
multi-observation arithmetic.

Files materially changed:

- `src/classifire/models.py`
- `src/classifire/migrations/versions/0046_draft_pricing_quantity_bases.py`
- `src/classifire/services/draft_pricing_quantity_contract.py`
- `src/classifire/services/draft_pricing_quantities.py`
- `src/classifire/services/draft_pricing_bottom_up.py`
- `src/classifire/services/deployment_lineage.py`
- `src/classifire/draft_pricing_ui.py`
- `src/classifire/templates/draft_pricing.html`
- focused quantity/bottom-up/migration/deployment tests and migration-head assertions;
- the four durable project documents.

Open issues:

- representative A/B source files, ownership/rights and accepted recipe/quantity
  semantics have not been provided or validated;
- one reviewed `sell_price` observation per requirement is supported;
- yield, productivity, waste/pack, shared recovery and comparables remain absent;
- T13 grouping/split policy is synthetic and unaccepted against representative data;
- no evaluation execution, calibrated confidence, commercial activation, deployment,
  real ChatGPT OAuth/HTTPS link, OpenClaw retirement or Human Release exists;
- GitHub previously merged PR #232 immediately when auto-merge was requested, so branch
  protection enforcement requires separate repository-setting review.

## Validation evidence

Focused quantity, bottom-up, migration, deployment-lineage and packaging set:

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('quantity-basis-regression-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp tests/test_draft_pricing_quantities.py tests/test_draft_pricing_bottom_up.py tests/test_migrations_draft_pricing_quantity_bases.py tests/test_deployment_lineage.py tests/test_migration_packaging.py

Result: **47 passed**, one existing warning.

Full repository result: **1,919 passed, 2 skipped, 140 warnings** in 3,135.34
seconds. Full Ruff and Bandit passed. Focused Mypy passed on the five changed modules
with `--ignore-missing-imports`. Strict full Mypy was locally blocked only by missing
third-party ReportLab and PyYAML stubs in the environment; clean GitHub CI must run the
strict configured gate. Alembic reports one head:
`0046_draft_pricing_quantity_bases`. `git diff --check` passed.

Real Chrome 152 UAT used only disposable synthetic database
`classifire_draft_quantity_uat_20260909_03` and loopback port 8831. It proved
missing-basis withholding, no-write preview, immutable save, history/reopen, correct
`2 each x $300 = $600.00`, visible hashes, exact downloads, HTTP 403 for an estimator,
and byte-identical quantity/proposal JSON after a real server restart. The supplied
CLASSIFIRE logo rendered and is byte-identical to `C:\CLASSIFIRE\classifire logo.png`
at SHA-256
`fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.

Receipts and screenshots remain outside Git at
`C:\CLASSIFIRE\.tmp\quantity-basis-browser-artifacts-20260909`.
The quantity JSON is 1,994 bytes with SHA-256
`7ae8c65575233d932e192a4d250b0c4b001c25c90cee2a0fc6edfeb091684a7d`.
The proposal JSON is 3,793 bytes with SHA-256
`ac8b341a2cbbef9cd499e3363d4012c48f26d93f0bc770180a32dd66fc6be153`.
Ports 8831 and 9231 were closed and server logs contained no traceback, exception,
application error or HTTP 5xx.

## Start Here / Next Session

**First task:** run a real-process browser/restart/exact-download proof for the existing
Dataset B mapping, T13 roster and T9 coverage workflow.

**Why this is next:** the highest strategic task is representative validation of T6
recipe meanings and the T13 grouping/split policy, but no authorised representative A/B
files or accepted rights/semantics are currently available. The browser proof is the
highest-value unblocked task: it strengthens the interactive prototype and can expose UI
or lifecycle defects without inventing commercial truth.

**Prerequisites:** inspect AGENTS.md, GOAL.md, Git/worktrees, current `origin/main`,
recent PR/CI state and the four project documents before editing. Confirm the
quantity-basis candidate was merged and main CI passed; otherwise finish or accurately
reconcile that work first. Use a fresh current-main worktree. Preserve the recovery root
and unrelated local changes. Use synthetic data and the local PostgreSQL/ClamAV
boundaries only.

**Relevant components:** `src/classifire/draft_pricing_ui.py`,
`src/classifire/templates/draft_pricing.html`,
`src/classifire/services/draft_pricing_intake.py`,
`draft_pricing_coverage.py`, `draft_pricing_evaluation_rosters.py`,
their contracts/models/migrations, and focused B-mapping/roster/coverage UI tests.

**Validation:** exercise actual login, coverage navigation, B mapping preview/save/
history/download, roster preview/save/history/download, permission denial, exact hashes,
server restart and byte-identical downloads. Visually inspect screenshots and the correct
logo. Run affected PostgreSQL tests, Ruff, targeted Mypy, Bandit, Alembic one-head and
diff checks. Run broader tests only if code changes or failures justify them.

**Blockers:** do not use customer files, claim representative validation, run holdout
evaluation, activate commercial data, deploy, retire OpenClaw or create canonical/release
state. If existing UIs cannot produce the journey, implement only the smallest shared
service/UI correction exposed by the test.

**Definition of done:** the real browser proves the existing B mapping, roster and
coverage lifecycle across restart with exact auditable artifacts, or a concrete defect is
fixed and the same proof then passes. Evidence is retained outside Git, durable documents
are reconciled, unrelated changes are classified, and any safe product/document change
continues through focused validation, commit, push, PR, required CI and merge.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. First inspect AGENTS.md, GOAL.md,
> Git/worktrees, current origin/main, recent PR/CI, PROJECT_STATE, architecture, roadmap
> and handoff; preserve the conflicted C:\CLASSIFIRE recovery root and unrelated changes.
> Confirm the governed T10 quantity-basis candidate is merged with green main CI, and
> reconcile it first if not. Then use a fresh current-main worktree for the highest-value
> unblocked task: a synthetic real-process browser/restart/exact-download proof of the
> existing Dataset B mapping, T13 roster and T9 coverage UI. This is next because
> representative recipe/grouping validation is strategically higher but blocked until
> authorised A/B files and accepted rights/semantics exist. Reuse existing services and
> PostgreSQL/ClamAV boundaries; inspect actual controls before editing and make only the
> smallest correction a failed journey proves necessary. Prove login, navigation,
> preview/save/history/download, permission denial, hashes, restart persistence,
> byte-identical JSON, and the supplied CLASSIFIRE logo. Run affected PostgreSQL tests,
> Ruff, targeted Mypy, Bandit, Alembic one-head and diff checks. Do not invent commercial
> rules, use customer evidence, run evaluation, activate/release data, deploy or change
> OpenClaw. Update durable docs from evidence, preserve unrelated work, and continue
> autonomously through classification, commit, push, PR, required CI and merge where safe.
