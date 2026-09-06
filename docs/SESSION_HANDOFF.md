# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-07 from shared main
5b517c232d8ac7a455176fcd67055771a8df73c9, the merge commit for PR #218.
Exact PR head 02451aaaaf99c8667846ca36650fdd8d0af52b91 passed required run
34058657496 before merge. Post-merge main run 34059650587 was in progress at this
reconciliation and must be checked before claiming that separate run passed.

ADRs 0001/0002 remain accepted. CLASSIFIRE is one modular deterministic
application with independently callable Scope, System Match, Estimate and
Reporting capabilities, portable artifacts and optional bounded AI. OpenClaw
remains transitional. PR #218 adds no AI, agent, model, canonical write,
commercial activation, deployment or release authority.

## Relevant local changes and open issues

PR #218 extends the existing Draft pricing path:

- migration 0042 adds append-only draft_pricing_row_observations;
- the existing pricing page reconstructs exact rows from a saved profile;
- an administrator with pricing:approve can preview and explicitly save one
  product, material, labour or service observation from a current approved
  general_pricelist profile;
- the envelope binds Draft, dataset/source/profile/decision/row hashes, exact
  cells, price meaning, normalized reference, evidence state, unresolved
  fields, reviewer and time;
- confirmed observations reject unresolved fields; unusable or formula/error
  rows, stale/changed/replayed/foreign/corrupt inputs fail closed;
- reopen and exact JSON download verify stored bytes and bindings;
- later source versions preserve old observations and mark them stale;
- Product, LabourComponent, PricingLibraryRecord, LibraryRelease,
  TechnicalVariant, Estimate, prediction, system-match and release effects
  remain false.

Local validation on the rebased feature branch:

- 43 focused feature, UI, migration, deployment and packaging tests passed;
- all 62 changed/new migration-consumer and feature tests passed;
- repository-wide Ruff passed;
- targeted Mypy passed on five changed source files;
- repository-wide Bandit passed;
- git diff --check passed;
- Alembic reports one head: 0042_draft_pricing_row_observations.

The real browser and separate-process restart journey has not yet been completed
for PR #218. TestClient exercised real FastAPI routes, sessions, CSRF, rendered
HTML, redirects, persistence and downloads with a synthetic XLSX. Browser
automation previously failed to initialize because its Windows sandbox helper
exited during setup. Retry when available; do not claim visual proof without it.

Actual Dataset A and B layouts, ownership, redistribution rights, price meaning,
tax/date/unit/inclusion semantics and representative record counts remain
unverified. Use synthetic fixtures until those decisions are authorized.

The recovery root C:\CLASSIFIRE remains on
gpt/phase8-linked-original-images at de0cc5a, with 46 unstaged tracked changes,
14 staged additions and four DU conflicts at last inspection. Do not reset,
clean, resolve, broadly stage or publish from it. Preserve unrelated worktrees.
The earlier synthetic listener on port 8819 was process 37032 at last check and
is not production.

## Start Here / Next Session

**First task:** implement one reviewed Dataset B Firefly
system/configuration mapping through the existing pricing UI.

**Why this is next:** Dataset A now has an exact normalized-row evidence record,
but Firefly B still has only source/profile approval. A reviewed B observation
and resolved technical identity are required before CLASSIFIRE can persist an
honest T13 train/validation/holdout roster or compare system prices without
alias, configuration or version leakage.

**Prerequisites and dependencies:** inspect current Git/worktrees, origin/main,
the latest required CI and these documents before editing. Use a clean current-main
worktree. Reuse DraftPricingSource/Profile/Decision, the Dataset A row-observation
hash/audit/download pattern, TechnicalVariant and technical release governance,
and the early-T13 contract. Require a current approved firefly_system_prices
profile and an eligible approved technical identity. Retain unmatched and
ambiguous outcomes explicitly. Do not infer identity from filename or price.

**Relevant files/components:**

- src/classifire/models.py: DraftPricingSource*, DraftPricingRowObservation,
  TechnicalVariant and LibraryRelease;
- src/classifire/services/draft_pricing_contract.py;
- src/classifire/services/draft_pricing_intake.py;
- src/classifire/services/draft_pricing_evaluation_contract.py;
- src/classifire/services/technical.py and technical release services;
- src/classifire/draft_pricing_ui.py and pricing templates;
- migration 0042 and deployment_lineage.py;
- Dataset A observation, pricing UI, technical governance and migration tests;
- roadmap T2-T8, T12 and T13.

**Definition of done:** an authorised user can open a current approved Dataset B
profile, inspect exact row values/cells, choose one usable row, and preview then
save an immutable observation mapped to an eligible exact TechnicalVariant and
configuration identity, or explicitly save unmatched/ambiguous status with a
reason and unresolved fields. Reopen after restart and download identical
canonical JSON. Bind all Dataset B source/profile/decision/row hashes and the
technical release/variant identity and hashable field snapshot.

Reject stale source/profile/decision/technical release, changed row or variant,
duplicate/replay, foreign access, invalid or formula/error cells, corrupt stored
JSON and price-only identity claims. Preserve old history as stale. Do not grant
technical approval, activate a pricing library, change an Estimate, reveal a
holdout target, run a model, create a system match, deploy or release.

**Validation commands:** resolve paths first and use the disposable PostgreSQL
database.

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-b-map-tests-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp <targeted tests>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads

**Blockers requiring validation:** the real B schema and rights are unknown; the
current parser cap may not support the reported B row count; stable
system/configuration identity and alias rules need representative evidence.
Current pricing review is effectively administrator-only because pricing_manager
lacks owned Draft reads. Do not broaden global visibility as a shortcut.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. First inspect AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, architecture, roadmap, handoff, current
> Git/worktrees and GitHub main/PR/CI before editing. Preserve the conflicted
> C:\CLASSIFIRE root and unrelated changes;
> use a clean current-main worktree. Implement the single highest-value next
> task: a working UI to review one exact approved Dataset B row and save,
> reopen and download an immutable Firefly system/configuration observation
> mapped to an eligible exact TechnicalVariant, or explicitly unmatched/
> ambiguous with reason and unresolved fields. Reuse existing pricing source/
> profile/decision, Dataset A observation, technical-release, canonical hash,
> audit, lock and download patterns. Reject stale, changed, replayed, foreign,
> formula/error, corrupt and price-only identity claims. Grant no technical,
> pricing-library, Estimate, prediction, holdout-target, system-match, release
> or deployment authority. Use synthetic data until real rights and semantics
> are verified. Add focused contract/service/UI/migration/no-side-effect tests,
> browser/restart/exact-download proof where available, Ruff, Mypy, Bandit,
> one Alembic head and required CI. Inspect the full diff, preserve unrelated
> work, then autonomously commit, push, open/update a PR and merge only when
> checks and repository rules allow. Update docs from measured evidence and
> avoid speculative breadth.
