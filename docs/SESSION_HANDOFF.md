# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09 from the isolated worktree and GitHub.

- Shared local `origin/main` baseline is
  `720de41fc828f933107436d70c00ac410feafef7`, the merge commit for PR #233.
- Active worktree:
  `C:\CLASSIFIRE\.tmp\draft-client-pricing-coverage-20260909`.
- Active branch: `feat/draft-client-pricing-coverage-20260909`.
- PR #235 is open against `main`:
  <https://github.com/Slayde91/classifire/pull/235>.
- Code commit `7a1149b` adds read-only T9 pricing coverage. Code commit `9916246`
  adds bounded T13 roster-history list/read tools and compatible service pagination.
- PR #234 was closed after its verified documentation commits were incorporated into
  PR #235.
- Required PR check run 34324384038, job 102378168830, executed zero validation
  steps. GitHub states that recent account payments failed or the spending limit must
  be increased. This is an external CI/account blocker, not evidence that tests passed
  or failed.
- The dirty conflicted `C:\CLASSIFIRE` root is recovery evidence. Do not edit, reset,
  clean, resolve, broadly stage or publish from it.
- ADRs 0001/0002 remain accepted: one modular deterministic application, independent
  Scope/System Match/Estimate/Reporting capabilities, portable artifacts, bounded
  optional AI and transitional OpenClaw.

## Current implementation

PR #235 now exposes three read-only MCP operations over existing shared services:

- `preview_pricing_coverage(draft_id, technical_release_id)`;
- `list_pricing_evaluation_rosters(draft_id, before_revision)`;
- `read_pricing_evaluation_roster(draft_id, roster_id)`.

All require external-client `read`, `estimate` and `technical` scopes, strict Draft
ownership, an active mapped local user and existing pricing-review plus technical-read
permissions. Because the current external client is owner-only, successful use requires
an administrator-owned Draft. An estimator-owned or foreign Draft fails closed.

Roster listing returns newest-first pages of at most 20 summaries and an older-revision
cursor. It reports semantic roster, exact-content, manifest and mapping-inventory hashes
separately. Exact read returns the validated canonical roster, its byte hash and size.
The roster contains target-field commitments and hashes without target price values.
Only the true latest roster can be marked current, including when an older page is read.

The adapter performs no pricing, matching, grouping or integrity logic of its own. It
calls `draft_pricing_coverage` and `draft_pricing_evaluation_rosters`. It creates no client
request, roster, pricing-library row, Estimate, approval, evaluation, release or other
database record, and it does not invoke AI or OpenClaw.

## Validation evidence

- Focused roster-client integration tests: **3 passed in 43.05 seconds**.
- Related client/pricing/coverage/roster PostgreSQL selection: **46 passed in
  289.97 seconds**.
- A valid 22-revision case proved the 20-summary page bound, older-page cursor and
  current-marker behavior.
- Exact roster bytes and hashes were reproduced after rebuilding a fresh FastAPI/MCP
  application over the same PostgreSQL state.
- Missing client scopes, foreign ownership, insufficient local role, missing IDs,
  invalid cursor and corrupt stored bytes failed closed.
- Audit and relevant domain-table counts were unchanged by all client reads.
- `python -m ruff check .`: passed.
- `python -m bandit -r src`: passed; 70,139 lines scanned, no issues.
- `python -m mypy src --disable-error-code=import-untyped`: passed on 220 source files.
  Strict local Mypy still depends on absent ReportLab/PyYAML third-party stubs.
- `git diff --check`: passed before the code commit.

These are local synthetic-data results. Real OAuth, HTTPS deployment, a real ChatGPT
session and representative Dataset A/B meaning have not been demonstrated.

## Relevant local changes and open issues

The intended branch changes are:

- `src/classifire/draft_client_capability_tools.py`;
- `src/classifire/services/draft_pricing_evaluation_rosters.py`;
- `tests/test_draft_client.py`;
- `tests/test_draft_client_pricing_rosters.py`;
- the four durable project documents.

No unrelated change was observed in this isolated worktree. Temporary PostgreSQL test
state and pytest directories remain outside repository source. Verify status again before
editing or publishing.

Open issues:

- PR #235 is not shared-main capability until required checks pass and it merges.
- GitHub Actions cannot currently start required jobs because of the account
  billing/spending-limit state. Never bypass required checks.
- Real OAuth authorization, HTTPS deployment, account linking and a real ChatGPT session
  remain unconfigured and unproven.
- The client still lacks reviewed Dataset A row-observation and T6 recipe-link reads.
- Representative A/B source files, handling/redistribution rights, price meanings,
  quantity/recipe semantics and supported scale remain unverified.
- T13 grouping/split policy remains synthetic and unaccepted against representative data.
- There is no evaluation execution, calibrated confidence, commercial activation,
  production deployment, OpenClaw retirement or Human Release.

## Project health

The branch advances the accepted hybrid architecture: ChatGPT-compatible clients and the
standalone UI use the same deterministic services and PostgreSQL state. No second rules
engine, database, agent fleet or orchestration dependency was added. The new boundary is
small, permission-checked, restart-stable, integrity-checked and testable.

The main operational weakness is external CI availability. The main product weakness is
still representative evidence: synthetic tests prove software behavior but cannot prove
that real workbook meanings, split policy, recipes or prices are correct.

## Start Here / Next Session

**First task:** add bounded read-only MCP access to persisted T6 recipe-link history using
the existing recipe service.

**Why this is next:** coverage and target-blind roster history are now available through
the shared client boundary, but the client cannot inspect the reviewed Dataset A evidence
links that justify bottom-up T9 coverage. Representative source validation has higher
authority but is blocked by absent authorised files, rights and accepted meanings. Recipe-
link read parity is executable now and continues the shared ChatGPT/standalone path without
inventing domain facts.

**Prerequisites and dependencies:**

- Inspect `AGENTS.md`, `docs/GOAL.md`, Git/worktrees, `origin/main`, PR #235/checks and
  these four durable documents before editing.
- Preserve the conflicted recovery root and any unrelated local work.
- Reuse `draft_pricing_recipes.list_recipe_links` and `recipe_link_bytes`; do not
  duplicate link validity, current/stale or integrity rules in the MCP adapter.
- If a bounded list requires cursor/limit support, extend the existing service
  compatibly and prove stable ordering for existing UI callers.
- Preserve strict project ownership, `read`/`estimate`/`technical` client scopes and
  current local pricing-review plus technical-read permissions.
- Do not create or modify a link, approve evidence, calculate or activate a price,
  change an Estimate, run evaluation or grant release authority.

**Relevant files:**

- `src/classifire/draft_client_capability_tools.py`;
- `src/classifire/services/draft_pricing_recipes.py`;
- `src/classifire/draft_client_auth.py`;
- `tests/test_draft_client_pricing_rosters.py` for the current client-test pattern;
- `tests/test_draft_pricing_recipes.py`;
- the four durable project documents.

**Validation commands:**

- Run focused PostgreSQL client/recipe-link tests with the repository virtual environment,
  isolated-worktree `PYTHONPATH`, `-p no:cacheprovider` and a unique `--basetemp`.
- Run related client, pricing coverage, roster and recipe regressions.
- Run `python -m ruff check .`, relevant Mypy, `python -m bandit -r src` and
  `git diff --check`.
- Verify exact bytes after a fresh application/server construction and prove zero writes.

**Blockers:** representative semantics require authorised files and usage rights. PR
publication can proceed, but merge cannot complete while required GitHub Actions jobs
cannot start.

**Definition of done:** an authenticated authorised client can list a bounded stable page
of recipe-link summaries and read one exact integrity-checked link through the shared
service. Current/stale state and evidence hashes remain intact; access and corrupt-data
failures are closed; no write or next capability occurs; focused and related tests pass;
all four documents remain aligned; only reviewed paths are committed/pushed; required CI
passes and the PR merges where safe.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect `AGENTS.md`,
> `docs/GOAL.md`, Git/worktrees, `origin/main`, PR #235/checks and the four durable
> documents. Preserve the conflicted `C:\CLASSIFIRE` recovery root and unrelated changes.
> The highest-value executable task is bounded read-only MCP access to persisted T6 recipe-
> link history because T9 coverage and T13 roster history are now client-readable while
> the reviewed Dataset A links supporting bottom-up coverage are not. Reuse
> `draft_pricing_recipes.list_recipe_links` and `recipe_link_bytes`; extend their list
> contract compatibly only if a stable cursor/limit is required. Require strict owned-
> project access, `read`/`estimate`/`technical` client scopes and current local pricing-
> review plus technical-read rights. Do not mutate links, approve evidence, calculate or
> activate prices, change Estimates, run evaluation or grant release authority. Test tool
> metadata, bounded ordering/cursors, exact bytes after fresh-app restart, current/stale
> and corrupt-data behavior, missing scopes, foreign access, insufficient role and zero
> writes. Run focused PostgreSQL tests, related regressions, Ruff, relevant Mypy, Bandit
> and diff checks. Update all four documents from evidence and continue autonomously
> through classification, commit, push, PR, required CI and merge where safe. Never
> bypass the current GitHub Actions billing blocker or speculate about absent source data.
