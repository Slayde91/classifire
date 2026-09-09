# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09.

- Shared origin/main is 720de41fc828f933107436d70c00ac410feafef7, the
  merge commit for PR #233.
- PR #233 head 3103236b8a466ff13dd18d0d3e97a6c7886c11c0 passed run
  34279792008: 1,921 tests, full Ruff, full Mypy on 220 source files, Bandit
  and one Alembic head.
- Post-merge main run 34281851774 attempted twice and executed zero steps.
  GitHub reported failed recent payments or an exceeded spending limit. This is
  an external CI/account blocker; the exact merge commit lacks post-merge execution.
- Active isolated worktree:
  C:\CLASSIFIRE\.tmp\draft-client-pricing-coverage-20260909
- Active branch: feat/draft-client-pricing-coverage-20260909, published as PR #235. It contains code commit
  7a1149b adds the MCP coverage tool; merge commit 9c5b69d includes the complete
  verified documentation history from PR #234.
- PR #234 was closed after all three of its documentation commits were included
  in PR #235. PR #235 is open; run 34323955126 executed zero steps and failed only
  because GitHub reported the same account billing/spending-limit condition.
- The recovery root C:\CLASSIFIRE remains on gpt/phase8-linked-original-images
  at de0cc5a with extensive staged, unstaged, conflicted and untracked recovery
  material. It was not edited, reset, cleaned, resolved, broadly staged or published.
- ADRs 0001/0002 remain accepted: one modular deterministic application,
  independent Scope/System Match/Estimate/Reporting capabilities, portable
  artifacts, bounded optional AI and transitional OpenClaw.

## Current implementation and open issues

The current candidate registers the read-only MCP tool:

    preview_pricing_coverage(draft_id, technical_release_id)

It invokes the existing deterministic
services.draft_pricing_coverage.preview_coverage function used by the standalone
pricing UI. The adapter contains no pricing, matching or orchestration rules.

The tool requires all of the following:

1. a valid mapped OAuth identity;
2. read, estimate and technical client grants;
3. strict ownership of the requested Draft;
4. current local project, estimate and technical read rights;
5. the shared service's pricing-review and technical-read permissions.

Because external clients are currently owner-only, successful coverage access requires
a Draft owned by an administrator. An estimator-owned Draft remains denied even when
its token carries all three client scopes. This deliberate current boundary needs
product-policy review before broad ChatGPT use.

The result is the exact T9 coverage contract: active-release targets, current/stale
Dataset B mapping evidence, recipe links, unlinked Dataset A evidence, reasons, status
counts and hashes. It contains no calculated price and declares every mutation,
approval, evaluation and release effect false. It creates no client request or other
database row.

Open issues:

- PR #235 is not on shared main until required checks pass and it is merged.
- GitHub Actions cannot currently start new jobs because of the account billing/spending
  state. Never bypass required checks.
- Real OAuth authorization, HTTPS deployment, account linking and a real ChatGPT
  session remain unconfigured and unproven.
- Representative A/B source files, ownership/rights and accepted recipe/quantity
  semantics have not been provided or validated.
- T13 grouping/split policy remains synthetic and unaccepted against representative data.
- Client parity is still missing for reviewed row records, T13 rosters and T6 recipe links.
- No evaluation execution, calibrated confidence, commercial activation, deployment,
  OpenClaw retirement or Human Release exists.

## Files materially changed by the current branch

Implementation:

- src/classifire/draft_client_capability_tools.py
- tests/test_draft_client.py
- tests/test_draft_client_pricing_coverage.py

Durable project documentation:

- docs/PROJECT_STATE.md
- docs/CLASSIFIRE_ARCHITECTURE.md
- docs/CLASSIFIRE_ROADMAP.md
- docs/SESSION_HANDOFF.md

The branch also includes the three prior documentation commits from PR #234 so its
governed quantity and B/T9/T13 browser evidence is not lost.

## Validation evidence

Focused command:

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp C:\CLASSIFIRE\.tmp\pytest-client-pricing-coverage-20260909-d tests/test_draft_client_pricing_coverage.py tests/test_draft_client.py::test_client_to_human_to_saved_draft_and_exact_package

Result: 3 passed in 51.79 seconds.

Broader related command used the same environment and a unique temporary directory:

    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp C:\CLASSIFIRE\.tmp\pytest-client-pricing-coverage-20260909-related tests/test_draft_client.py tests/test_draft_client_pricing.py tests/test_draft_client_pricing_coverage.py tests/test_draft_pricing_coverage.py

Result: 41 passed in 250.23 seconds.

Additional checks:

- Full repository Ruff: passed.
- Bandit over src/classifire: passed.
- Strict Mypy reached 220 source files but failed only because the local environment
  lacks ReportLab and PyYAML third-party stubs.
- Mypy with only import-untyped diagnostics disabled: passed all 220 source files.
- git diff --check passed before the implementation commit.
- Tests compare the full MCP result with the direct service result, reconstruct a
  fresh FastAPI/MCP server over the same PostgreSQL state, require identical output,
  exercise missing scopes, foreign project, estimator role and missing release, and
  prove audit/domain table counts do not change.

The first attempted test command used the system Python and failed collection because
PyJWT was absent. It did not test product behavior. Subsequent commands used the proven
repository virtual environment and isolated-worktree PYTHONPATH.

## Local-change classification

- Intended: the three implementation/test files and these four documents.
- Inherited intentionally: PR #234's documentation-only history.
- Unrelated local changes in this worktree: none observed before this documentation edit.
- Recovery-root changes: unrelated recovery evidence; untouched.
- Temporary pytest databases/directories: test-only, outside Git.

## Start Here / Next Session

**First task:** add bounded, read-only MCP access to persisted T13
pricing-evaluation roster history using the existing roster service.

**Why this is next:** the client can now inspect deterministic T9 coverage but cannot
inspect the saved target-blind training/validation/holdout commitments that govern later
evaluation. Representative Dataset B semantic validation is more authoritative but
remains blocked because authorised files, usage rights and accepted meanings are absent.
Roster read parity is executable now and advances shared ChatGPT/standalone architecture
without inventing those facts.

**Prerequisites and dependencies:**

- Inspect AGENTS.md, docs/GOAL.md, current Git/worktrees, origin/main, open
  PRs/checks and these four durable documents before editing.
- Confirm PR #235 and preserve this branch if it is still unmerged.
  Never edit the conflicted root.
- Reuse draft_pricing_evaluation_rosters.list_rosters and/or roster_bytes; do not
  duplicate roster, grouping, current/stale or integrity rules in the MCP adapter.
- Preserve strict client ownership, local pricing-review/technical-read rights and
  read/estimate/technical client grants.
- Do not expose target price values, create or modify a roster, execute evaluation,
  activate pricing, change an Estimate or grant technical/release authority.
- GitHub Actions billing is an external publication blocker. Do not bypass checks.

**Relevant files:**

- src/classifire/draft_client_capability_tools.py
- src/classifire/services/draft_pricing_evaluation_rosters.py
- src/classifire/draft_client_auth.py
- src/classifire/services/draft_client_requests.py
- tests/test_draft_client_pricing_coverage.py
- tests/test_draft_pricing_evaluation_rosters.py
- the four durable project documents.

**Validation:**

- Prove discovery metadata and exact required client scopes.
- Compare the complete client result with the existing service/bytes.
- Prove a fresh app/server reads the same persisted result.
- Prove missing grants, foreign ownership, insufficient local role, missing roster,
  stale dependencies and corrupt bytes fail closed as applicable.
- Prove no audit, request, roster, pricing-library, Estimate, technical, evaluation
  or release write occurs.
- Run focused PostgreSQL tests, related client/roster regressions, full Ruff,
  relevant Mypy, Bandit and git diff --check.

**Blockers:** representative A/B semantics cannot be validated without authorised
files and usage rights. Publication and merge cannot complete while required GitHub
Actions jobs cannot start; PR #235 run 34323955126 confirms this blocker.

**Definition of done:** an authenticated authorised client can list/read a bounded
saved T13 roster through the same shared service; output is exact, current/stale status
is preserved, held-out target prices are absent, access failures are closed, no write
or next capability occurs, focused and related tests pass, all four documents remain
aligned, and work proceeds through reviewed commit, push, PR, required CI and merge
where safe.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. First inspect AGENTS.md,
> docs/GOAL.md, Git/worktrees, origin/main, open PRs/checks and the four durable
> documents; preserve the conflicted C:\CLASSIFIRE recovery root and unrelated
> changes. Confirm PR #235 and its feat/draft-client-pricing-coverage-20260909 branch
> state before editing. The next executable task is bounded read-only MCP access
> to persisted T13 pricing-evaluation roster history. This follows the candidate
> preview_pricing_coverage tool because a ChatGPT-compatible client can see
> coverage but cannot yet see the target-blind split commitments. Reuse
> draft_pricing_evaluation_rosters.list_rosters and roster_bytes; do not duplicate
> rules, expose target prices, mutate a roster, run evaluation, activate pricing,
> change an Estimate or grant approval/release authority. Require strict owned-
> project access, read/estimate/technical client scopes and current local pricing-
> review plus technical-read rights. Test discovery metadata, exact service parity,
> fresh-app persistence, current/stale and corrupt-data behavior, missing scopes,
> foreign access, insufficient role and zero writes. Run focused PostgreSQL tests,
> related regressions, Ruff, relevant Mypy, Bandit and diff checks. Update all four
> durable documents from evidence and continue autonomously through classification,
> commit, push, PR, required CI and merge where safe. GitHub Actions billing
> currently prevents jobs from starting; never bypass required checks.
