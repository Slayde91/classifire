# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09 from isolated worktrees and GitHub.

- Shared remote `main` is
  `324f66a2e73330589e43b2ca17529eaf8de61bfe`, the verified merge commit
  for PR #235.
- PR #235 is merged. Exact head run 34329434461 attempt 2 passed the full test suite,
  Ruff, Mypy, Bandit and the one-head Alembic check. Post-merge main run 34336769556
  passed the same repository gates on the exact merge commit.
- PR #236 now targets `main` directly:
  <https://github.com/Slayde91/classifire/pull/236>.
  Its current head before this documentation reconciliation is
  `d3054db83a4f03948487b9917aa21d86484d37ac`. Exact code-head run
  34333784853 passed every repository gate.
- PR #236 worktree:
  `C:/CLASSIFIRE/.tmp/draft-client-recipe-links-20260909`;
  branch `feat/draft-client-recipe-links-20260909`.
- The next slice is active but uncommitted in
  `C:/CLASSIFIRE/.tmp/draft-client-row-observations-20260909`;
  branch `feat/draft-client-row-observations-20260909`, based on PR #236 head.
- The dirty conflicted `C:/CLASSIFIRE` root is recovery evidence. Do not edit,
  reset, clean, resolve, broadly stage or publish from it.
- ADRs 0001/0002 remain accepted: one modular deterministic application, independent
  capabilities, portable artifacts, bounded optional AI and transitional OpenClaw.

## Current implementation

Merged PR #235 gives an authorised client the same deterministic T9 coverage result used
by the standalone application and bounded list/exact-read access to persisted target-blind
T13 roster history.

PR #236 adds:

- `list_pricing_recipe_links(draft_id, before_link_id)`;
- `read_pricing_recipe_link(draft_id, link_id)`.

The recipe-link list returns at most 20 newest-first summaries with a stable older-link
cursor. The shared service preserves its original ascending unbounded behavior for the
standalone UI. Exact read returns one validated canonical link, its byte hash and size.
Both operations require read, estimate and technical client scopes, strict Draft ownership,
an active mapped local user and existing pricing-review plus technical-read permissions.
They create no client request, link, price, Estimate, approval, evaluation, release or
other record and do not invoke AI or OpenClaw.

The active row-observation work adds two uncommitted operations:

- `list_pricing_row_observations(draft_id, source_id, profile_id,
  after_observation_id)`;
- `read_pricing_row_observation(draft_id, source_id, profile_id, observation_id)`.

They reuse `draft_pricing_intake`, require only read plus estimate client scopes
and retain the service's project/estimate/library permission checks. The existing UI keeps
its unbounded row-order call; the client page is capped at 20 and uses an exact observation
cursor.

## Validation evidence

PR #236:

- focused recipe-link client integration: **3 passed in 67.02 seconds**;
- related PostgreSQL selection: **56 passed in 511.49 seconds**;
- exact code-head workflow 34333784853: full tests, Ruff, Mypy, Bandit and Alembic passed.

Active row-observation branch:

- focused PostgreSQL integration: **3 passed**;
- exact bytes survived fresh FastAPI/MCP application construction;
- a valid profile revision made the prior observation visibly stale;
- missing scope, foreign ownership, insufficient local role, missing IDs, invalid cursor
  and corrupt content failed closed;
- 22 observations proved a 20-item first page and exact continuation in worksheet order;
- audit and relevant domain-table counts were unchanged by client reads;
- focused Ruff passed and `git diff --check` passed;
- related regressions and repository-wide checks have not yet run.

All evidence is synthetic. Real OAuth, HTTPS, a real ChatGPT session and representative
Dataset A/B semantics remain unproven.

## Relevant local changes and open issues

PR #236 contains only its recipe-link code, tests and these four documents. This
documentation reconciliation must be committed, pushed and receive required CI before
merge.

The row-observation worktree currently contains intended changes to:

- `src/classifire/draft_client_capability_tools.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `tests/test_draft_client.py`;
- new `tests/test_draft_client_pricing_row_observations.py`.

No unrelated change was observed in either isolated worktree at the last inspection.
Verify status and the base before editing or publishing.

Open issues:

- PR #236 still needs its final documentation-head CI and merge.
- The row-observation branch is stacked on PR #236 and must be reconciled to
  `main` after #236 merges.
- Report intake still lacks client parity.
- Real OAuth authorization, HTTPS deployment, account linking and a real ChatGPT session
  remain unconfigured and unproven.
- Representative A/B files, rights, price meanings, recipe/quantity semantics and scale
  remain unverified. T13 split policy remains synthetic.
- Evaluation execution, calibrated confidence, commercial activation, production
  deployment, OpenClaw retirement and Human Release remain absent.

## Project health

The work follows the accepted hybrid architecture: standalone and ChatGPT-compatible
interfaces call the same deterministic services and PostgreSQL state. The client adapters
add permission, pagination and transport only. No business rule, second database, agent
fleet or orchestration dependency was added.

GitHub Actions is executing again. Representative source evidence is now the principal
external product blocker: synthetic tests prove software behavior but cannot prove real
workbook meanings, recipe validity, split suitability or commercial accuracy.

## Start Here / Next Session

**First task:** finish, publish and merge the active Dataset A row-observation client
slice after PR #236 is safely merged.

**Why this is next:** a client can follow coverage to a roster and recipe link, but still
cannot open the reviewed Dataset A row cited by that link from shared `main`.
The local slice closes that evidence-chain gap using existing deterministic services and
already has focused proof.

**Prerequisites and dependencies:**

- Inspect `AGENTS.md`, `docs/GOAL.md`, Git/worktrees,
  `origin/main`, PR #236 and its checks, then inspect the four durable documents
  before editing.
- Preserve the conflicted recovery root and every unrelated local change.
- Let the PR #236 documentation head pass required CI and merge it normally. Verify the
  merge commit, fetch `main`, then retarget/reconcile the row branch without
  resetting or discarding work.
- Keep `draft_pricing_intake.list_row_observations` and
  `row_observation_bytes` as the source of permissions, integrity and
  current/stale truth.
- Do not add observation mutation, pricing activation, Estimate changes, evaluation,
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
C:/CLASSIFIRE/.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp C:/CLASSIFIRE/.tmp/pytest-row-client-final tests/test_draft_client_pricing_row_observations.py tests/test_draft_pricing_row_observations.py tests/test_draft_client_pricing.py tests/test_draft_client_pricing_recipe_links.py -q
C:/CLASSIFIRE/.venv/Scripts/python.exe -m ruff check .
C:/CLASSIFIRE/.venv/Scripts/python.exe -m mypy src --disable-error-code=import-untyped
C:/CLASSIFIRE/.venv/Scripts/python.exe -m bandit -r src
git diff --check
```

**Blockers:** representative semantics require authorised files and usage rights. This
does not block the read-only client slice. Required CI must pass and must not be bypassed.

**Definition of done:** an authenticated authorised client can list a stable bounded page
of exact-source/profile row summaries and read one exact integrity-checked observation.
Current/stale state and source, profile, row, definition and content identities remain
traceable; access and corruption failures close; no write or automatic next capability
occurs; focused and related tests plus repository checks pass; all four documents align;
reviewed paths are committed and pushed; a correctly based PR passes required CI and is
merged; the resulting `main` commit is verified.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect
> `AGENTS.md`, `docs/GOAL.md`, Git/worktrees,
> `origin/main`, PR #236 and its checks, and the four durable documents.
> Preserve the conflicted `C:/CLASSIFIRE` recovery root and unrelated changes.
> The highest-value task is to finish the active Dataset A row-observation client slice
> in `C:/CLASSIFIRE/.tmp/draft-client-row-observations-20260909` because
> shared clients cannot yet open the reviewed rows cited by recipe links. First merge
> PR #236 only after its exact documentation head passes required CI, verify/fetch
> `main`, then safely reconcile the row branch. Reuse
> `draft_pricing_intake.list_row_observations` and
> `row_observation_bytes`; preserve exact Draft/source/profile identity,
> service permissions, integrity, current/stale state and existing UI ordering. Keep the
> client read-only and bounded; add no pricing activation, Estimate change, approval, AI
> or OpenClaw authority. Reinspect the current diff and focused tests, run the related
> PostgreSQL selection, Ruff, Mypy, Bandit and `git diff --check`, update all
> four documents from evidence, then continue autonomously through classification,
> commit, push, correctly based PR, required CI and merge where safe. Completion requires
> exact restart-stable reads, 20-item paging, fail-closed permissions/corruption, zero
> writes, aligned docs, green CI and a verified `main` merge.
