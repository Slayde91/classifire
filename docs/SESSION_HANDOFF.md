# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-08 from shared main
`75817f04f4ff5433b7cfc348daf8454a6b243b3d`, merge commit for PR #224.
Exact implementation head `463682f826b789cdfd4843ed22b0f771b6e2a34a`
passed workflow 34148949367: 1,877 tests, full Ruff, Mypy on 212 source
files, Bandit and one Alembic head. Post-merge main workflow 34150861778
passed the same repository-gate workflow on the exact merge commit.

ADRs 0001/0002 remain accepted. CLASSIFIRE is one modular deterministic
application with independently callable Scope, System Match, Estimate and
Reporting capabilities, portable artifacts and optional bounded AI. OpenClaw
remains transitional. T9 coverage uses no agent or provider and grants no
canonical, technical, commercial, deployment or release authority.

The six-file state, architecture, roadmap and handoff reconciliation merged in
PR #225 at `1d1365d8684704857fecbd59bbe45fdd0cc4de6d`. Recheck current
`origin/main`, worktrees and CI before starting new work.

## Relevant local changes and open issues

PR #224 extends the existing Draft pricing path:

- `services/draft_pricing_coverage.py` deterministically inventories every target
  in the current active technical release;
- current exact Dataset B mappings provide direct support, ambiguous candidates
  require review, stale evidence remains stale and absent evidence abstains;
- each target result retains release, target and mapping hashes plus explicit reasons;
- reviewed Dataset A observations are visible as current/stale unlinked evidence;
- bottom-up A support is deliberately zero because no governed versioned recipe links
  an A observation to a frozen technical component or labour requirement;
- the existing pricing page renders the service output and downloads the same exact
  canonical JSON;
- corrupt mapping envelopes and foreign access fail closed;
- all price calculation, proposal, activation, Estimate, technical, evaluation,
  deployment and release effects are false;
- no migration, database write, background job, agent or model was added.

Local verification passed two focused coverage service/UI tests, eight pricing
regressions, repository-wide Ruff and Bandit, targeted Mypy on both changed source
files, `git diff --check` and the one-head check at
`0044_draft_pricing_evaluation_rosters`. TestClient covered rendered statuses and
exact JSON. Full local Mypy was limited by missing ReportLab/PyYAML stubs in unrelated
output/Mission Control modules; complete CI Mypy passed. A visual browser and separate
application-process restart were not run.

The immediate architectural blocker is verified in code and documentation:
`TechnicalVariant.component_requirements` and `labour_requirements` exist, but
`technical_field_snapshot.FIELD_NAMES` and the v3 technical-release record omit
them. Reading current mutable JSON for costing would falsely imply that it was part
of an approved release. Dataset A evidence therefore cannot provide target-specific
bottom-up support until a versioned recipe/claim basis and review link exist.

Real A/B layouts, ownership, redistribution rights, commercial basis, tax/date/unit/
inclusion semantics, representative record counts and the T13 lineage/split policy
remain unverified. The parser cap is 1,000 rows including the header, so support for
1,000-plus Dataset B data rows is not proven. There is no pricing proposal, holdout
execution, metric, calibration or accuracy claim.

The recovery root `C:\CLASSIFIRE` remains on
`gpt/phase8-linked-original-images` at `de0cc5a`, with 46 unstaged tracked
changes, 14 staged additions, four DU conflicts and untracked recovery material
at last inspection. Do not reset, clean, resolve, broadly stage or publish from
it. Preserve unrelated worktrees and changes.

## Start Here / Next Session

**First task:** implement the first bounded T6 versioned component/activity
recipe-review interaction.

**Why this is next:** T9 now gives users an honest view of pricing coverage and
shows that Dataset A cannot support any technical target. A reviewed recipe is the
smallest missing dependency between frozen technical requirements and current A
product/material/labour/service observations. Price calculations built first would
rest on mutable or invented associations.

**Prerequisites and dependencies:**

- inspect `AGENTS.md`, Git/worktrees, current `origin/main`, latest CI and all
  current state/architecture/roadmap/handoff documents before editing;
- use a clean current-main worktree and preserve the recovery root;
- inspect the current v3 technical-release snapshot before defining compatibility;
- reuse `TechnicalVariant`, technical release/source integrity, reviewed Dataset A
  observations, canonical JSON/hash and Draft locking/permission services;
- preserve old technical-release readers and bytes; do not fabricate historical
  component/labour approval;
- keep technical eligibility, commercial evidence, recovery and price authority
  separate;
- use synthetic fixtures unless real-source access and rights are explicitly authorised.

**Relevant files/components:**

- `src/classifire/models.py`;
- `src/classifire/technical_field_snapshot.py`;
- `src/classifire/services/technical_release_publication.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `src/classifire/services/draft_pricing_coverage.py`;
- `src/classifire/draft_pricing_ui.py` and
  `src/classifire/templates/draft_pricing.html`;
- technical release, Dataset A, coverage, UI, permission and migration tests;
- roadmap T4-T6 and architecture sections 8-9.

**Definition of done:** an authorised user can choose one current technical target,
inspect an explicit frozen component or labour/activity requirement, preview candidate
current reviewed Dataset A observations and explicitly save/reopen/download one
immutable recipe-link review. The artifact binds the technical release/target/recipe
basis and A source/profile/decision/row hashes; retains units, quantity/yield or
productivity basis, recovery boundary, evidence state, reviewer reason and unresolved
fields; supports explicit unresolved/no-link outcomes; and preserves prior release
bytes. Foreign, stale, changed, replayed and corrupt inputs fail closed. The slice
does not calculate or approve a price, activate a library, alter an Estimate, approve
technical applicability, run evaluation or release output. T9 can consume the new link
only after its integrity and currentness checks are proven.

**Validation commands:** resolve exact test paths after implementation and use the
disposable PostgreSQL database.

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t6-recipe-tests-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp <targeted tests>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads

**Blockers requiring validation:** decide the smallest additive compatibility contract
for old v3 releases that omit component/labour fields. Do not silently read mutable
`TechnicalVariant` JSON or backfill approval. If a recipe cannot be frozen without a
new release/artifact version, implement that forward version explicitly and retain old
readers. Real recipe meaning, units, yields, productivity and recovery rules still need
authorised representative evidence.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect AGENTS.md,
> GOAL.md, the four current project documents, Git/worktrees, origin/main and GitHub CI.
> Preserve the conflicted C:\CLASSIFIRE recovery root and unrelated changes; use a clean
> current-main worktree. Implement the highest-value next task: one bounded T6 versioned
> component/activity recipe-review interaction. First inspect TechnicalVariant component/
> labour JSON and the v3 technical-release snapshot; never treat mutable omitted fields as
> released or backfill historical approval. Reuse technical source/release integrity,
> reviewed Dataset A observations, canonical hashes, permissions and locks. Let an
> authorised user preview, explicitly save, reopen and download one immutable link or
> unresolved outcome with exact technical/A dependencies, units, quantity/yield or
> productivity basis, recovery boundary, evidence state and reviewer reason. Preserve old
> release bytes. Do not calculate/approve prices, activate a library, change an Estimate,
> approve applicability, run evaluation, deploy or release. Add focused lifecycle,
> staleness, integrity, authority and no-side-effect tests; run relevant regressions,
> Ruff, Mypy, Bandit and Alembic one-head validation. Inspect/classify the final diff,
> preserve unrelated work, then autonomously commit, push, open/update a PR and merge
> only after checks pass. Update documentation from measured evidence; avoid speculative
> bulk ingestion, model tuning or new orchestration infrastructure.
