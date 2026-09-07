# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-08 from shared main
`abfbffc54a48f498f6c59764824ad9754b2839d6`, merge commit for PR #222.
Exact implementation head `08bb671369b358707d4eadc6a575db9ee035918f`
passed workflow 34140315496: 1,875 tests, full Ruff, Mypy on 211 source
files, Bandit and one Alembic head. Post-merge main workflow 34141924350
passed the same 1,875-test and repository-gate workflow.

ADRs 0001/0002 remain accepted. CLASSIFIRE is one modular deterministic
application with independently callable Scope, System Match, Estimate and
Reporting capabilities, portable artifacts and optional bounded AI. OpenClaw
remains transitional. The pricing roster uses no agent or provider and grants
no canonical, technical, commercial, deployment or release authority.

This handoff is being reconciled on `docs/pr222-final-state-20260908` in
`C:\CLASSIFIRE\.tmp\pr222-final-state-20260908`. Verify its documentation
PR and current `origin/main` before starting new work.

## Relevant local changes and open issues

PR #222 extends the existing Draft pricing path:

- migration 0044 adds append-only `draft_pricing_evaluation_rosters` and is
  the single migration head;
- an authorised reviewer can preview the full current Dataset B mapping
  inventory without a write;
- only current `mapped` records are eligible; stale, unmatched and ambiguous
  records retain explicit exclusions;
- transitive system, alias, configuration, source-derivation and workbook-
  version groups stay wholly in training, validation or holdout;
- assignment receives observation IDs and lineage only, never target prices;
- fewer than three independent groups produces a visible no-save result;
- explicit save locks the Draft and exact dependencies, rebuilds the preview,
  checks freshness and appends canonical roster/manifest history;
- unchanged replay, stale/changed/foreign/corrupt input fails closed;
- the UI reopens current/stale history and downloads exact canonical JSON;
- target reveal, evaluation, prediction, library activation, Estimate change,
  technical approval, deployment and release effects are all false.

Local verification passed the 16 focused T13 tests, the full Draft Pricing
regression group, every changed migration/current-head consumer, repository-wide
Ruff and Bandit, isolated Mypy on the changed evaluation services,
`git diff --check`, and the one-head check. TestClient covered permission
denial, preview/save, all splits, insufficient evidence, a fresh client session,
history and exact download. A visual browser and separate application-process
restart were not run.

Real A/B layouts, ownership, redistribution rights, price basis, tax/date/unit/
inclusion semantics, representative record counts and the v1 lineage/split
policy remain unverified. The parser cap is 1,000 rows including the header,
so support for 1,000-plus Dataset B data rows is not proven. The roster freezes
membership only; there is no target-opening service, evaluation run, metric,
calibration or accuracy claim.

The recovery root `C:\CLASSIFIRE` remains on
`gpt/phase8-linked-original-images` at `de0cc5a`, with 46 unstaged tracked
changes, 14 staged additions, four DU conflicts and untracked recovery material
at last inspection. Do not reset, clean, resolve, broadly stage or publish from
it. Preserve unrelated worktrees and changes.

## Start Here / Next Session

**First task:** add the first bounded T9 pricing-coverage and missing-data
status interaction.

**Why this is next:** the product can now govern source meaning, review exact A
rows, map B rows to technical identity and freeze an evaluation roster. Before
building price proposals, users need one screen that shows which technical
targets have usable evidence and which remain unsupported. This is the shortest
safe step toward an interactive estimating prototype and exposes missing data
instead of hiding it behind a total.

**Prerequisites and dependencies:**

- inspect `AGENTS.md`, Git/worktrees, current `origin/main`, latest CI and
  the state/architecture/roadmap/handoff documents before editing;
- use a clean current-main worktree and preserve the recovery root;
- reuse current active TechnicalRelease records, current reviewed Dataset A
  observations, current mapped Dataset B records and their integrity checks;
- keep technical eligibility separate from commercial evidence;
- do not treat profile approval, a B mapping or a T13 roster as permission to
  apply or approve a price;
- represent stale, unresolved, missing and unsupported evidence explicitly.

**Relevant files/components:**

- `src/classifire/models.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `src/classifire/services/draft_pricing_evaluation_rosters.py`;
- technical release and Draft Estimate read services;
- `src/classifire/draft_pricing_ui.py` and
  `src/classifire/templates/draft_pricing.html`;
- Draft pricing, mapping, roster, UI and migration tests;
- roadmap T6-T10 and the integrated corpus/dual-pricing design.

**Definition of done:** an authorised user selects the current technical
release and previews every selected technical target with one explicit status:
direct observed B support, bottom-up A support, review needed, stale input or
insufficient evidence. Each result identifies exact dependency records/hashes
and clear reasons. The same deterministic service is reusable by future API/
client interfaces. Preview performs no write and creates no price, library
record, Estimate revision, technical approval, evaluation or release. Foreign,
stale and corrupt inputs fail closed. Tests cover supported and unsupported
targets, permission isolation, deterministic ordering and no side effects.

**Validation commands:** resolve paths first and use the disposable PostgreSQL
database.

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t9-coverage-tests-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp <targeted tests>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads

**Blockers requiring validation:** the complete target inventory and acceptable
commercial-basis tuple are not yet defined from real sources; A rows are not
yet mapped to versioned component/activity recipes; current technical releases
do not freeze complete recipes. The first slice should expose these as missing
coverage, not invent them or wait for the entire corpus.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect
> AGENTS.md, GOAL.md, docs/PROJECT_STATE.md, architecture, roadmap, handoff,
> current Git/worktrees, origin/main and GitHub CI. Preserve the conflicted
> C:\CLASSIFIRE recovery root and unrelated changes; use a clean current-main
> worktree. Implement the single highest-value next task: a bounded T9 pricing-
> coverage status UI using current active technical-release targets and current
> governed Dataset A observations and Dataset B mappings. Show every target as
> direct-B support, bottom-up-A support, review needed, stale input or
> insufficient evidence, with exact dependency hashes and reasons. Reuse
> existing integrity/permission services and keep technical eligibility separate
> from commercial evidence. Preview must be deterministic and no-write; do not
> calculate or approve prices, activate a library, change an Estimate, open
> holdout targets, evaluate a model, approve technical applicability, deploy or
> release. Add focused service/UI/permission/staleness/no-side-effect tests and
> relevant regressions; run Ruff, Mypy, Bandit and the one-head check. Inspect
> and classify the final diff, preserve unrelated work, then autonomously commit,
> push, open/update a PR and merge only after checks pass. Update documentation
> from measured evidence and avoid speculative work.
