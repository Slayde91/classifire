# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09 from isolated worktrees, local tests and GitHub.

- Shared remote `main` is
  `aca75415c281f99ab218b564b1287c0e42bef18c`, merge commit for PR #236.
- PR #236 is merged. Exact head
  `c8b8501a3738188f61dac05c9a494e507bd18103` passed run 34340361136:
  full tests, Ruff, Mypy, Bandit and the one-head Alembic check.
- Post-merge main run 34342328239 is currently executing on exact merge commit
  `aca75415`; it is not yet recorded as passed.
- Active isolated worktree:
  `C:/CLASSIFIRE/.tmp/draft-client-row-observations-20260909`;
  branch `feat/draft-client-row-observations-20260909`.
- Feature commit `b8ed4f7` was merged non-destructively with current
  `origin/main` as local commit `627b555`; this branch also contains the aligned
  documentation reconciliation.
- The dirty conflicted `C:/CLASSIFIRE` root is recovery evidence. Do not edit,
  reset, clean, resolve, broadly stage or publish from it.
- ADRs 0001/0002 remain accepted: one modular deterministic application,
  independent capabilities, portable artifacts, bounded optional AI and
  transitional OpenClaw.

## Current implementation

Shared main now gives an authorised external client deterministic read-only access to:

- T9 pricing coverage;
- bounded T13 evaluation-roster history;
- bounded T6 recipe-link history;
- independent saved Scope, System Match, Estimate and report capabilities from
  earlier client increments.

The active branch adds:

- `list_pricing_row_observations(draft_id, source_id, profile_id,
  after_observation_id)`;
- `read_pricing_row_observation(draft_id, source_id, profile_id,
  observation_id)`.

These operations reuse `draft_pricing_intake`. Existing standalone calls retain
unbounded worksheet order. Client pages contain at most 20 records and continue from an
exact owned observation cursor. Exact reads verify canonical stored bytes and hashes.
Summaries preserve dataset, source, profile, worksheet row, definition/content hashes,
review data, uncertainty and current/stale state.

The tools require read and estimate client scopes plus the service's existing
project-read, estimate-read and library-read permissions. They create no observation,
price, Estimate, audit, approval, evaluation, release or other record. They invoke no AI
or OpenClaw path and do not run another capability automatically.

## Validation evidence

After merging exact shared main into the active branch:

- the affected PostgreSQL, client and standalone UI selection passed **48 tests**;
- exact bytes survived a fresh FastAPI/MCP application construction;
- a later valid profile revision made prior evidence visibly stale;
- 22 saved observations proved a 20-item first page and exact continuation;
- missing client scope, foreign ownership, insufficient local role, missing records,
  invalid cursors and corrupt stored JSON failed closed;
- audit and relevant domain-record counts were unchanged by client reads.

After the documentation edit, repository-wide Ruff, Mypy on 220 source files with the
known third-party stub category disabled, Bandit over 70,416 source lines and
`git diff --check` all passed. All functional evidence is synthetic. Real OAuth, HTTPS, a real ChatGPT session and representative Dataset A/B
commercial meaning remain unproven.

## Relevant local changes and open issues

Committed feature paths:

- `src/classifire/draft_client_capability_tools.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `tests/test_draft_client.py`;
- `tests/test_draft_client_pricing_row_observations.py`.

Intended documentation paths changed with this feature:

- `docs/PROJECT_STATE.md`;
- `docs/CLASSIFIRE_ARCHITECTURE.md`;
- `docs/CLASSIFIRE_ROADMAP.md`;
- `docs/SESSION_HANDOFF.md`.

No unrelated local change was observed in the isolated worktree before these document
edits. Reinspect status and the full diff before staging.

Open issues:

- The active row-observation branch still needs explicit-path documentation commit,
  push, direct PR, required CI and merge.
- The standalone UI already exposes PDF defect-report, Excel defect-report and pricing
  workbook uploads. Report intake is not yet available through a proven ChatGPT client
  journey.
- ProjectPackage currently includes selected capability artifacts and report files.
  Evidence source bodies and newer pricing-review records remain external or explicitly
  withheld; the next membership change needs clear confidentiality and redistribution
  rules.
- Real OAuth/HTTPS/account linking, representative source semantics, evaluation
  execution, calibrated confidence, commercial activation, production deployment,
  OpenClaw retirement and Human Release remain incomplete.

## Project health

The active work follows the accepted hybrid architecture. Standalone and external-client
adapters call the same deterministic PostgreSQL-backed services. The adapter adds
transport, permission checks and bounded paging without copying pricing rules or granting
new authority.

The prototype has real standalone upload controls and multiple independently callable
Draft capabilities. The main user-value gap is a proven ChatGPT-native intake-to-reviewed-
Scope journey. Source rights and representative evidence remain the principal blockers
to commercial or production claims.

## Start Here / Next Session

**First task:** finish, publish and merge the active Dataset A row-observation client
slice.

**Why this is next:** all implementation and affected tests are complete, and the branch
closes the missing read link from a T6 recipe requirement to its exact reviewed Dataset A
evidence. Leaving it local would preserve a half-finished client chain.

**Prerequisites and dependencies:**

- Inspect `AGENTS.md`, `docs/GOAL.md`, the current branch/status/diff,
  `origin/main`, PR #236, run 34342328239 and these four durable documents before
  editing or publishing.
- Preserve the conflicted recovery root and every unrelated local change.
- Confirm the active branch still contains feature commit `b8ed4f7` and merge commit
  `627b555` over `aca75415`.
- Keep `draft_pricing_intake.list_row_observations` and
  `row_observation_bytes` as the sources of permission, integrity and current/stale
  truth.
- Do not add mutation, commercial activation, Estimate changes, evaluation,
  approval/release authority, AI or OpenClaw behavior.

**Relevant files:**

- `src/classifire/draft_client_capability_tools.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `tests/test_draft_client.py`;
- `tests/test_draft_client_pricing_row_observations.py`;
- `tests/test_draft_pricing_row_observations.py`;
- the four durable project documents.

**Validation commands:**

```powershell
$env:PYTHONPATH=(Join-Path $PWD 'src')
$env:CLASSIFIRE_POSTGRES_TEST_URL='postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN='classifire-containment-test-drop-all'
C:/CLASSIFIRE/.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp C:/CLASSIFIRE/.tmp/pytest-row-client-final tests/test_draft_client.py tests/test_draft_client_pricing.py tests/test_draft_client_pricing_recipe_links.py tests/test_draft_client_pricing_row_observations.py tests/test_draft_pricing_row_observations.py tests/test_draft_pricing_ui.py tests/test_draft_pricing_coverage.py -q
C:/CLASSIFIRE/.venv/Scripts/python.exe -m ruff check .
C:/CLASSIFIRE/.venv/Scripts/python.exe -m mypy src --disable-error-code=import-untyped
C:/CLASSIFIRE/.venv/Scripts/python.exe -m bandit -r src
git diff --check
```

**Blockers:** required CI must pass and must not be bypassed. Representative commercial
semantics require authorised files and usage rights, but that does not block this
read-only transport slice.

**Definition of done:** an authenticated authorised client can page reviewed Dataset A
rows and read one exact integrity-checked record after restart. Source/profile/row
identity, hashes, review state, uncertainty and staleness remain traceable; permissions
and corruption fail closed; reads create zero records; standalone behavior remains
compatible; tests and repository checks pass; all four documents align; intended paths
are committed and pushed; a direct-main PR passes required CI and merges; resulting
`main` and its post-merge workflow are verified.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect
> `AGENTS.md`, `docs/GOAL.md`, Git/worktrees, the active branch and full diff,
> `origin/main`, PR #236/run 34342328239, and all four durable documents. Preserve
> the conflicted `C:/CLASSIFIRE` recovery root and unrelated changes. The single
> highest-value task is to finish and merge the tested Dataset A row-observation client
> slice in
> `C:/CLASSIFIRE/.tmp/draft-client-row-observations-20260909`, because it closes the
> evidence chain from pricing coverage and recipe links to the exact reviewed source
> row. Verify feature commit `b8ed4f7` and merge `627b555` over shared main
> `aca75415`; keep the client read-only, bounded and governed by
> `draft_pricing_intake.list_row_observations` and `row_observation_bytes`.
> Inspect the current docs edits, rerun the listed 48-test PostgreSQL/UI selection,
> Ruff, Mypy, Bandit and `git diff --check`, then continue autonomously through
> classification, explicit-path commit, push, direct PR, required CI and merge where
> safe. Do not add pricing activation, Estimate mutation, approval, AI or OpenClaw
> authority. Completion requires exact restart-stable reads, 20-item paging,
> fail-closed access/corruption, zero writes, compatible standalone behavior, aligned
> docs, green CI and a verified main merge.
