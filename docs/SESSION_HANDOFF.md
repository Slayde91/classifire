# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09.

- Shared `origin/main` is
  `720de41fc828f933107436d70c00ac410feafef7`, merge commit for PR #233.
- PR #233 head `3103236b8a466ff13dd18d0d3e97a6c7886c11c0` passed required
  GitHub run 34279792008 before merge: 1,921 tests, full Ruff, full Mypy on
  220 source files, Bandit and one Alembic head.
- Post-merge main run 34281851774 attempted twice and executed zero steps. GitHub's
  check annotation says Actions could not start because recent account payments failed
  or the spending limit must be increased. This is an external account/CI blocker, not
  a code-test failure, but the exact merge commit lacks post-merge execution.
- Current isolated documentation worktree:
  `C:\CLASSIFIRE\.tmp\quantity-basis-docs-merged-20260909`.
- Current branch: `docs/reconcile-quantity-basis-merge-20260909`, based exactly on
  the PR #233 merge commit. Its only intended changes reconcile the four durable
  documents from candidate language to the merged state and record the CI blocker.
- PR #234 is open for that documentation reconciliation. Its required Python validation
  also executed zero steps and failed with the same GitHub account billing/spending
  annotation, so it must remain unmerged until Actions availability is restored.
- A separate clean current-main worktree
  `C:\CLASSIFIRE\.tmp\draft-pricing-b-roster-ui-uat-20260909` contains no tracked
  change. It was used only to execute the synthetic Dataset B/T9/T13 browser proof.
- The recovery root `C:\CLASSIFIRE` remains on
  `gpt/phase8-linked-original-images` at `de0cc5a` with extensive staged,
  unstaged, conflicted and untracked recovery material. It was not edited, reset,
  cleaned, resolved, broadly staged or published.
- ADRs 0001/0002 remain accepted: one modular deterministic application, independent
  Scope/System Match/Estimate/Reporting capabilities, portable artifacts, bounded
  optional AI and transitional OpenClaw.

## Current implementation and open issues

PR #233 adds the first purpose-specific, append-only
`DraftPricingQuantityBasis` and migration
`0046_draft_pricing_quantity_bases`.

An authorised pricing reviewer can:

1. open a T9-eligible bottom-up target;
2. select a service with an explicit quantity and matching unit from the current
   immutable Scope revision;
3. preview the exact binding without a database write;
4. explicitly save canonical hash-bound JSON;
5. reopen current/stale history and download the exact record;
6. let the T10 proposal calculate only from the newest current compatible basis.

The record binds Scope revision/hash, service identity/quantity/unit/evidence state,
technical release/target/recipe hashes, exact recipe link and requirement, reviewer,
UTC time and reason. Changed Scope, recipe link, requirement, unit or hashes makes
history stale. Foreign, missing, changed, replayed, corrupt and incompatible inputs
fail closed. The browser rejects typed quantity fields. The earlier manual preview
remains only as explicit `quantity_source="manual_preview"` behavior for tests and
comparison.

This increment adds no Estimate mutation, technical approval, pricing-library
activation, evaluation, canonical physical write, release, AI or OpenClaw authority.
Yield, productivity, waste, pack, recovery, margin, comparables and
multi-observation arithmetic remain absent.

The existing Dataset B mapping, T9 coverage and T13 roster UI has now also passed a
synthetic real-process Chrome 152 journey. The administrator saved three mapped rows and
one unmatched row; coverage showed three direct-B targets; the roster assigned one group
to each required split and excluded the unmatched row. Estimator mutation attempts
returned HTTP 403. A fresh server and browser reopened the records and returned identical
mapping, roster and coverage bytes. This is UI/persistence proof, not representative-data
semantic validation or evaluation execution.

Open issues:

- GitHub Actions cannot currently start new jobs because of the account billing/spending
  state. Do not merge a later PR without its required checks.
- Representative A/B source files, ownership/rights and accepted recipe/quantity
  semantics have not been provided or validated.
- T13 grouping/split policy remains synthetic and unaccepted against representative data.
- Only one reviewed `sell_price` observation per requirement is supported.
- No evaluation execution, calibrated confidence, commercial activation, deployment,
  real ChatGPT OAuth/HTTPS link, OpenClaw retirement or Human Release exists.
- Branch-protection behavior needs review because PR #232 merged immediately when
  auto-merge was requested.

## Files materially changed by PR #233

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

## Validation evidence

Final affected local command:

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('quantity-basis-regression-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp tests/test_draft_pricing_quantities.py tests/test_draft_pricing_bottom_up.py tests/test_migrations_draft_pricing_quantity_bases.py tests/test_deployment_lineage.py tests/test_migration_packaging.py

Result: **47 passed**, one existing warning.

The local full repository result was **1,919 passed, 2 skipped, 140 warnings**.
Full Ruff and Bandit passed. Focused Mypy passed on the five changed modules with
`--ignore-missing-imports`. Alembic reports one head:
`0046_draft_pricing_quantity_bases`. `git diff --check` passed.
Clean PR run 34279792008 then passed **1,921 tests** and strict full Mypy.

Real Chrome 152 UAT used only disposable synthetic database
`classifire_draft_quantity_uat_20260909_03`. It proved missing-basis withholding,
no-write preview, immutable save, history/reopen, correct
`2 each x $300 = $600.00`, visible hashes, exact downloads, HTTP 403 for an
estimator and byte-identical quantity/proposal JSON after server restart.

Receipts and screenshots remain outside Git at
`C:\CLASSIFIRE\.tmp\quantity-basis-browser-artifacts-20260909`.
The quantity JSON is 1,994 bytes with SHA-256
`7ae8c65575233d932e192a4d250b0c4b001c25c90cee2a0fc6edfeb091684a7d`.
The proposal JSON is 3,793 bytes with SHA-256
`ac8b341a2cbbef9cd499e3363d4012c48f26d93f0bc770180a32dd66fc6be153`.
The supplied logo rendered and matches the served asset at SHA-256
`fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.

Dataset B/T9/T13 real-process browser evidence used a dedicated loopback PostgreSQL
UAT database and synthetic four-row workbook. Four mapping JSON files, one roster and one
coverage artifact were byte-identical after a server restart and fresh Chrome profile.
Three focused PostgreSQL UI tests passed in 40.35 seconds. Screenshots were visually
inspected; the supplied logo matched SHA-256
`fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`; fully flushed
server logs contained no traceback, exception, error or HTTP 500. The final database held
four mapping rows, one roster, zero pricing-library records and zero canonical Estimates.
Receipts/screenshots remain outside Git at
`C:\CLASSIFIRE\.tmp\b-roster-browser-uat-20260909-081927-46817af3`.
The local ClamAV service was unavailable, so only synthetic source seeding used an explicit
clean-scan stub; the browser proof does not cover malware-scanner integration.

## Start Here / Next Session

**First task:** validate the governed T6 recipe meanings and T13 grouping/split policy
against authorised representative Dataset B source files.

**Why this is next:** synthetic UI, persistence, permission and restart behavior is now
proven. It cannot tell CLASSIFIRE what real workbook fields mean, whether recipes recover
the correct work, or whether related price observations stay in one split. Those facts
must be accepted before evaluation or broader yield/productivity arithmetic is safe.

**Prerequisites:** inspect `AGENTS.md`, `docs/GOAL.md`, Git/worktrees, `origin/main`, open
PRs/checks and these four documents before editing. Confirm the representative files are
authorised for local use and document their ownership, redistribution limits, price basis,
tax/date/inclusion meaning, versions and known relationships. Verify PR #234 and main run
34281851774 after GitHub Actions billing is restored; never bypass required checks. Use a
fresh current-main worktree, preserve the recovery root and unrelated changes, and never
commit customer files or confidential values.

**Relevant components:** `docs/TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md`,
`src/classifire/services/draft_pricing_contract.py`,
`src/classifire/services/draft_pricing_intake.py`,
`src/classifire/services/draft_pricing_recipes.py`,
`src/classifire/services/draft_pricing_evaluation_contract.py`,
`src/classifire/services/draft_pricing_evaluation_rosters.py`, T6/T7/T13 tests and the
four durable project documents.

**Validation:** inventory and hash the authorised sources outside Git; inspect workbook
structure and meanings; map representative records through current profile/mapping/recipe
contracts; test whether version, alias, source-derivation and near-duplicate relationships
form leakage-safe connected groups; verify that all required splits can be populated
without using target prices. If evidence proves a contract defect, implement the smallest
shared-core correction and add regression tests. Run focused PostgreSQL tests, Ruff,
targeted Mypy, Bandit, Alembic one-head and diff checks; broaden only when changes warrant.
Do not run a holdout evaluation or activate commercial data in this task.

**Blockers:** authorised representative A/B files, usage rights and accepted commercial
semantics are not present in the verified repository. GitHub publication also cannot
complete while Actions jobs cannot start.

**Definition of done:** a traceable representative-data review records each source's
identity, commercial meaning and lineage; confirms or corrects each frozen T6 recipe and
T13 connected-group/split rule; leaves unsupported meanings unresolved; proves no target
price influenced assignment; and passes the affected tests. Update durable documents,
classify local changes and continue through commit, push, PR, required CI and merge only
where safe.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Inspect AGENTS.md, docs/GOAL.md,
> Git/worktrees, origin/main, open PRs/checks and the four durable project documents before
> editing; preserve the conflicted C:\CLASSIFIRE recovery root and unrelated changes.
> Confirm PR #234 and failed zero-step main run 34281851774 after GitHub Actions billing is
> restored; never bypass required checks. The highest-value task is to validate current T6
> recipe meanings and T13 connected-group/split rules against authorised representative
> Dataset B files, because synthetic browser/restart proof is complete but cannot establish
> commercial meaning or leakage-safe real-data grouping. First confirm local-use rights and
> record source identity, versions, price/tax/date/inclusion meaning and lineage outside
> Git; never commit customer files or confidential values. Reuse current pricing contracts,
> ingestion, recipes and roster services. Keep unknowns unresolved, never use target prices
> for assignment, and do not run evaluation or activate data. If evidence proves a defect,
> make the smallest shared-core correction with regression tests. Run focused PostgreSQL
> tests, Ruff, targeted Mypy, Bandit, Alembic one-head and diff checks. Update durable docs
> from evidence and continue autonomously through classification, commit, push, PR,
> required CI and merge where safe. If authorised files or rights are absent, do not invent
> them; report that exact blocker and preserve the verified state.
