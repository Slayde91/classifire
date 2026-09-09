# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09 from isolated worktrees and GitHub.

- Shared remote `main` remains
  `720de41fc828f933107436d70c00ac410feafef7`, the PR #233 merge commit.
- Dependency PR #235 is open and unmerged at
  `eab351e3110524b957db50730a169376d63020a1`:
  <https://github.com/Slayde91/classifire/pull/235>.
- Active worktree:
  `C:\CLASSIFIRE\.tmp\draft-client-recipe-links-20260909`.
- Active branch: `feat/draft-client-recipe-links-20260909`.
- Stacked PR #236 targets PR #235's branch:
  <https://github.com/Slayde91/classifire/pull/236>.
- Code commit `9175d8f` adds bounded read-only T6 recipe-link list/exact-read tools and
  compatible service pagination.
- The required GitHub checks cannot currently start because the repository account has
  failed payments or an exceeded spending limit. Treat every zero-step check as an
  external CI blocker, not as test evidence, and never bypass required checks.
- The dirty conflicted `C:\CLASSIFIRE` root is recovery evidence. Do not edit, reset,
  clean, resolve, broadly stage or publish from it.
- ADRs 0001/0002 remain accepted: one modular deterministic application, independent
  capabilities, portable artifacts, bounded optional AI and transitional OpenClaw.

## Current implementation

PR #235 exposes deterministic T9 pricing coverage plus bounded T13 roster history through
three read-only MCP operations. Stacked PR #236 adds:

- `list_pricing_recipe_links(draft_id, before_link_id)`;
- `read_pricing_recipe_link(draft_id, link_id)`.

The list returns at most 20 newest-first summaries with a stable older-link cursor. The
shared service preserves its original ascending unbounded behavior when the standalone UI
calls it without pagination arguments. Exact read returns one validated canonical link,
its byte hash and size. Summary output includes release, technical target, recipe,
requirement, interpretation, evidence and exact-content identities and reports whether the
link's dependencies remain current.

Both tools require external-client read, estimate and technical scopes, strict Draft
ownership, an active mapped local user and existing pricing-review plus technical-read
permissions. They create no client request, recipe link, price, Estimate, approval,
evaluation, release or other database record. They do not invoke AI or OpenClaw.

## Validation evidence

- Focused recipe-link client integration: **3 passed in 67.02 seconds**.
- Related client/pricing/coverage/roster/recipe PostgreSQL selection: **56 passed in
  511.49 seconds**.
- A valid 22-link case proved the 20-summary page bound and stable older-page cursor.
- Exact canonical content and hash were reproduced after a fresh FastAPI/MCP application
  was constructed over the same PostgreSQL state.
- A changed technical dependency remained readable with `current: false`.
- Missing scopes, foreign ownership, insufficient local role, missing IDs, invalid
  cursors and corrupt stored bytes failed closed.
- Audit and relevant domain-table counts were unchanged by client reads.
- Full Ruff passed.
- Bandit scanned 70,290 source lines and found no issues.
- Mypy passed all 220 source files with only the locally absent ReportLab/PyYAML
  third-party import-stub category disabled.
- `git diff --check` passed before the code commit.

One intermediate focused run failed because the test attempted to start the same MCP HTTP
session manager twice. The product operation had already passed. The harness was corrected
to exercise stale state inside its existing client session, after which all three focused
tests passed.

These are synthetic local results. Real OAuth, HTTPS, a real ChatGPT session and
representative Dataset A/B semantics remain unproven.

## Relevant local changes and open issues

The intended PR #236 changes are:

- `src/classifire/draft_client_capability_tools.py`;
- `src/classifire/services/draft_pricing_recipes.py`;
- `tests/test_draft_client.py`;
- `tests/test_draft_client_pricing_recipe_links.py`;
- the four durable project documents.

No unrelated change was observed in this isolated worktree. Temporary test databases and
pytest directories remain outside repository source. Verify status before editing or
publishing.

Open issues:

- PR #236 depends on unmerged PR #235. Do not retarget or merge it into `main` until the
  dependency is safely present or the diff is otherwise reconciled.
- Required GitHub Actions jobs cannot start because of the billing/spending-limit state.
- Real OAuth authorization, HTTPS deployment, account linking and a real ChatGPT session
  remain unconfigured and unproven.
- Reviewed Dataset A row observations and report intake still lack client read parity.
- Representative A/B files, rights, price meanings, quantity/recipe semantics and scale
  remain unverified.
- T13 split policy remains synthetic and unaccepted against representative data.
- Evaluation execution, calibrated confidence, commercial activation, production
  deployment, OpenClaw retirement and Human Release remain absent.

## Project health

The stacked slice continues the accepted hybrid architecture: the standalone UI and
ChatGPT-compatible client call the same deterministic service and PostgreSQL state. It
adds no second business-logic path, database, agent fleet or orchestration dependency.
The new read boundary is bounded, permission-checked, integrity-checked, restart-stable
and explicit about stale dependencies.

The principal operational blocker is GitHub Actions billing. The principal product gap is
representative evidence: synthetic tests prove software behavior but cannot prove real
workbook meanings, recipe validity, split suitability or commercial accuracy.

## Start Here / Next Session

**First task:** add bounded read-only MCP access to reviewed Dataset A row-observation
history using the existing pricing-intake service.

**Why this is next:** clients can now inspect T9 coverage, T13 roster commitments and T6
recipe links, but they cannot open the exact reviewed Dataset A observations referenced by
those links. That missing read prevents a client from following the evidence chain to the
retained source row. Representative source validation has higher authority but remains
blocked by absent authorised files, rights and accepted meanings. Row-observation parity
is executable without inventing those facts.

**Prerequisites and dependencies:**

- Inspect `AGENTS.md`, `docs/GOAL.md`, Git/worktrees, `origin/main`, PRs #235/#236 and
  their checks, plus these four documents before editing.
- Preserve the conflicted recovery root and all unrelated local work.
- Reuse `draft_pricing_intake.list_row_observations` and `row_observation_bytes`; do not
  duplicate source/profile/current/integrity rules in the MCP adapter.
- The list currently requires exact Draft/source/profile identity and orders by source row.
  Add bounded stable pagination compatibly only if needed; preserve existing UI callers.
- Derive client scopes from the existing source/profile command boundary and require the
  shared local permissions; do not grant extra technical or commercial authority.
- Do not create or modify an observation, activate a pricing library, calculate a price,
  change an Estimate, run evaluation or grant approval/release authority.

**Relevant files:**

- `src/classifire/draft_client_capability_tools.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `src/classifire/draft_client_auth.py`;
- `tests/test_draft_client_pricing_recipe_links.py` for the latest client-test pattern;
- existing row-observation service/UI tests;
- the four durable project documents.

**Validation:** prove discovery metadata, bounded stable ordering, exact bytes after fresh
application construction, current/stale and corrupt-data behavior, missing scopes,
foreign ownership, insufficient local role and zero writes. Run focused PostgreSQL tests,
related pricing/client regressions, full Ruff, relevant Mypy, Bandit and `git diff --check`.

**Blockers:** representative semantics require authorised files and usage rights. PR
publication may continue, but required CI and merge cannot complete while GitHub Actions
jobs cannot start.

**Definition of done:** an authenticated authorised client can list a bounded stable page
of reviewed row-observation summaries for an exact source/profile and read one exact
integrity-checked observation through the shared service. Current/stale status and source,
profile, decision, row and content hashes remain intact; access/corruption failures are
closed; no write or automatic next capability occurs; focused and related tests pass; all
four documents remain aligned; reviewed paths are committed/pushed; required CI passes;
and stacked dependencies are merged safely in order.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect `AGENTS.md`,
> `docs/GOAL.md`, Git/worktrees, `origin/main`, PRs #235/#236 and their checks, and the
> four durable documents. Preserve the conflicted `C:\CLASSIFIRE` recovery root and
> unrelated changes. The highest-value executable task is bounded read-only MCP access to
> reviewed Dataset A row-observation history because clients can read T9 coverage, T13
> rosters and T6 recipe links but cannot inspect the exact observations those links cite.
> Reuse `draft_pricing_intake.list_row_observations` and `row_observation_bytes`; preserve
> exact Draft/source/profile identity, current/stale and integrity rules, and existing UI
> ordering. Add compatible stable pagination only if required. Derive the minimum client
> scopes from existing source/profile commands and preserve local pricing permissions. Do
> not mutate observations, activate prices, change Estimates, run evaluation or grant
> approval/release authority. Test metadata, bounded ordering/cursors, exact fresh-app
> reads, stale/corrupt data, missing scopes, foreign access, insufficient role and zero
> writes. Run focused PostgreSQL tests, related regressions, Ruff, relevant Mypy, Bandit
> and diff checks. Update all four documents from evidence and continue autonomously
> through classification, commit, push, PR, required CI and dependency-ordered merge where
> safe. Never bypass the GitHub Actions billing blocker or speculate about absent data.
