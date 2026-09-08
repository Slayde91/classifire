# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-09 from the clean isolated worktree
`C:\CLASSIFIRE\.tmp\docs-pr231-final-state-20260909`.

- Current documentation branch: `docs/pr231-final-state-20260909`, created from
  `origin/main` at `dc5884bee30443af7ffc034e7d4d5a8ef50b0742` (PR #231 merge).
- PR #231 head `8a714059eef4294f47732aaa797a98e461395fe3` passed run
  34256909957: 1,915 tests, full Ruff, full Mypy on 217 source files, Bandit and
  one Alembic head. Post-merge main run 34259076280 passed the same gates on
  `dc5884bee30443af7ffc034e7d4d5a8ef50b0742`, including 1,915 tests.
- PR #230 run 34246140519 passed 1,915 tests and every repository gate.
  Post-merge main run 34248498975 passed the same gates on the exact merge commit,
  including 1,915 tests and Mypy on 217 source files.
- PR #229 previously merged the bounded T10 read-only bottom-up proposal. Its
  exact-head run 34241209469 and post-merge run 34243723658 passed 1,915 tests and
  all repository gates.
- The accepted architecture remains a deterministic modular core with independently
  callable Scope, System Match, Estimate and Reporting capabilities, portable versioned
  artifacts, bounded optional AI and transitional OpenClaw.
- The recovery root `C:\CLASSIFIRE` remains on
  `gpt/phase8-linked-original-images` at `de0cc5acab14dd9f6ac421d164880a6da22b3721`
  with extensive staged, unstaged, conflicted and untracked recovery material. Do not
  reset, clean, resolve, broadly stage or publish from it.

## Merged change and open issues

PR #231 contains one narrow T10 presentation hardening change:

- the quantity input no longer uses browser-level `required`, allowing CLASSIFIRE's
  deterministic backend to display the governed withheld reason for a blank quantity;
- the result page now displays coverage, technical release, target, recipe-link and
  observation hashes already present in the proposal;
- the regression test proves blank-quantity withholding and every displayed dependency;
- AGENTS.md, GOAL.md and the four project documents select the governed quantity basis
  as the next task.

The current documentation branch changes only the four project records to replace
candidate/feature-branch wording with the verified PR #231 merge state. It contains no
product-code change.

The service contract, arithmetic, database schema, migrations and authority boundaries
are unchanged. T10 remains read-only: it changes no Estimate, library, technical approval,
evaluation result or release state.

Open issues remain. Quantities are still one-off preview inputs and are not governed
project records. T10 supports one current confirmed `sell_price` observation per frozen
requirement, with no multi-observation selection, yield, productivity, waste, pack,
recovery, margin or comparable method. Representative recipe semantics, actual source
rights/layouts and T13 grouping remain unvalidated. There is no commercial activation,
evaluation run, production deployment, OpenClaw retirement or production-readiness proof.

## Validation evidence

Real Chrome 152 UAT used only synthetic data in disposable PostgreSQL database
`classifire_draft_t10_demo_20260909_v2` and the loopback application on port 8822.
It proved:

- reviewer login and navigation from pricing coverage to T10;
- a blank quantity renders `Result: Withheld` and `quantity required`;
- `2 each x $300 = $600.00` is shown with exact dependency identities and hashes;
- a lower-privilege estimator receives HTTP 403;
- canonical JSON downloads before and after server restart are byte-identical;
- both 2,999-byte downloads have SHA-256
  `53fa19cf9fdfc68ca504d4431edb4a73c05a5a7046bab88d1360e28b4f4aeac7`;
- the embedded proposal SHA-256 is
  `faca050aa216b559921b578b6f52cfc4f06cb855181c861beefeabe7e971dadf`;
- browser screenshots were visually inspected and show the approved CLASSIFIRE logo;
- server logs contain no traceback, exception, HTTP 5xx or application error.

The successful synthetic evidence is retained outside Git at
`C:\CLASSIFIRE\.tmp\t10-browser-artifacts-20260909-v2`. The first database
`classifire_draft_t10_demo_20260909` is retained as diagnostic evidence: its intentionally
mis-shaped helper fixture produced two frozen requirements with only one link, and
CLASSIFIRE correctly withheld the proposal.

Focused T6/T9/T10 PostgreSQL validation passed **13 tests in 176.65 seconds**:

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t10-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp tests/test_draft_pricing_bottom_up.py tests/test_draft_pricing_coverage.py tests/test_draft_pricing_recipes.py

Ruff was accidentally pointed at the Jinja HTML template once; those syntax messages
were a command misuse, not product failures. The correct Ruff target passed.
Repository-wide Ruff passed, targeted Mypy passed on the T10 UI and service, Bandit
passed across `src`, Alembic reports the single head
`0045_draft_pricing_recipe_links`, and `git diff --check` passed. The disposable
server and Chrome processes were stopped and loopback ports 8822/9223 were verified closed.

## Start Here / Next Session

**First task:** implement the first governed project-quantity basis used by T10.

**Why this is next:** the browser-proven prototype can calculate an amount, but the user
must retype a quantity every time. A retained quantity tied to the exact saved Scope and
frozen recipe requirement is the smallest step that turns the calculation into a
trustworthy project workflow. It is also the prerequisite for later yield, productivity,
waste, pack and recovery logic.

**Prerequisites and dependencies:** inspect repository and GitHub state before editing.
Use a fresh clean worktree from current `origin/main`; preserve the conflicted root and
unrelated worktrees. Reuse existing Draft ownership, revision, canonical JSON/hash,
append-only review and pricing permission patterns. The quantity must bind to a selected
saved Scope revision and exact frozen recipe requirement. Determine the supported
quantity source from the actual Scope contract; never infer it from defect count, free
text or recipe notes.

**Relevant files/components:** `src/classifire/models.py`, existing additive Alembic
migrations, `src/classifire/services/draft_pricing_bottom_up.py`,
`src/classifire/services/draft_pricing_recipes.py`,
`src/classifire/draft_pricing_ui.py`,
`src/classifire/templates/draft_pricing.html`, Scope revision services/contracts,
and the T6/T9/T10 tests.

**Blockers/limits:** no representative customer quantities or approved conversion rules
are available. Use synthetic data. Do not add yield, productivity, waste, pack, recovery,
margin, comparables, AI, customer evidence, canonical release, deployment or OpenClaw
changes in this slice.

**Definition of done:** an authorised user can select a current saved Scope revision and
frozen requirement, preview an explicit quantity/unit without writing, explicitly save an
immutable hash-bound quantity record, reopen history after restart and download exact
JSON. Foreign, stale, changed, replayed, missing or unit-incompatible dependencies fail
closed without writes. T10 consumes only the latest current compatible saved basis and
withholds otherwise. Existing manual preview behaviour remains understood and no
Estimate or approval authority is added. Add focused service/UI/migration/permission/
restart tests, visually inspect the browser flow, run applicable PostgreSQL tests, Ruff,
targeted Mypy, Bandit, Alembic one-head and diff checks, then classify and publish safely.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect AGENTS.md,
> GOAL.md, PROJECT_STATE.md, the architecture, roadmap, handoff, Git/worktrees, current
> origin/main, recent PRs and CI. Preserve the conflicted C:\CLASSIFIRE root and all
> unrelated local work; use a fresh clean current-main worktree. Implement the single
> highest-value next slice: a governed T10 project-quantity basis bound to an exact saved
> Scope revision and frozen recipe requirement. Reuse existing revision, ownership,
> permission, canonical JSON/hash and append-only review patterns. Provide no-write
> preview plus explicit immutable save/reopen/history/download; make T10 consume only the
> latest current compatible basis and withhold foreign, stale, changed, missing or
> unit-incompatible inputs. Never infer quantity from defect counts or notes. Relevant
> components are models/migrations, Scope revision contracts, draft_pricing_bottom_up,
> draft_pricing_recipes, draft_pricing_ui, draft_pricing.html and T6/T9/T10 tests. Use
> synthetic data; do not add yield/productivity/waste/pack/recovery/margins, AI, customer
> evidence, release authority, deployment or speculative breadth. Run focused PostgreSQL
> service/UI/migration/permission/restart tests, visually inspect the browser, then Ruff,
> targeted Mypy, Bandit, Alembic one-head and diff checks. Update the four project docs
> from evidence and continue autonomously through classification, commit, push, PR,
> passing CI, safe merge and post-merge verification.
