# CLASSIFIRE Session Handoff

CI status snapshot: 2026-09-12 01:20 UTC. Named runs may finish after this audit;
re-query them before activation or publication decisions.

Reconciled 2026-09-12. Read this with [PROJECT_STATE.md](./PROJECT_STATE.md),
[architecture](./CLASSIFIRE_ARCHITECTURE.md) and [roadmap](./CLASSIFIRE_ROADMAP.md).
Repository evidence overrides this dated checkpoint.

## Branch and project context

- Documentation worktree: `C:\CLASSIFIRE\.tmp\docs-reconcile-current-state-20260912`,
  branch `docs/reconcile-current-state-20260912`, based on main c496baf and safely
  fast-forwarded to 7847288. Its intended upstream is the same-named origin branch.
  This change
  includes documentation only; no implementation or runtime changes are bundled.
- Shared main after correction: 7847288511267e78be1de42019bc11d9ec303e40, PR #255.
  Word inspection/review/package/client source is merged. Do not implement it again.
- PR #254 merged before CI finished after an auto-merge request. This is a disclosed
  process failure, not completed CI. The main protection endpoint reports unprotected.
  Use explicit successful-check verification, never `--auto` as an enforcement substitute.
- Parent main run 34658986190 failed its midnight-sensitive technical activation test
  after 1,894 passes. Fix 18418f3 is in separate PR #255; production logic is unchanged,
  all 23 targeted tests and hosted run 34662942874 passed. PR #255 merged 7847288
  at 2026-09-12 01:12:24 UTC.
- Word PR CI 34662617629 passed; merged-main run 34662645680 ended cancelled
  (not a pass). Corrected-main run 34664119693 remains in progress. Re-query current
  results. Slow observation does not mean a live job stopped.
- Existing app: 127.0.0.1:8820, PID 23084, earlier Excel checkout/build 8fc4855.
  No Word activation, live database migration, OAuth grant or tunnel change occurred.
  Listener existence does not prove client acceptance or database correctness.

The full target remains incomplete: broader evidence/physical-model coverage, complete
portable history, representative technical/commercial semantics and production gates.
The first governed quantity-basis feature already exists in PR #233.

## Local changes and publication classification

The documentation replaces contradictory accumulated checkpoints, keeps detailed T1-T14
and Phase 0-16 exits, separates implementation from planned work and supplies one task
order and one paste-ready prompt. Root `CLASSIFIRE_ARCHITECTURE.md`,
`CLASSIFIRE_ROADMAP.md` and `SESSION_HANDOFF.md` are links to the maintained docs, not
second copies. AGENTS/GOAL receive only necessary stale-priority corrections.

See [LOCAL_CHANGE_CLASSIFICATION.md](./LOCAL_CHANGE_CLASSIFICATION.md) for every root
tracked path and logical untracked group. Legacy root de0cc5a has 46 unstaged modifications,
14 staged additions, four DU conflicts and an interrupted cherry-pick. It stays untouched.
All unknown/private/generated material is excluded. Prior Word and test-clock feature
commits remain on their own clean branches and are not restaged into this documentation PR.

## Start Here / Next Session

**First task: I2 — prepare and complete one controlled Word client acceptance journey.**
Source and synthetic browser tests already exist. The useful next step is bringing the
existing trial app up to the validated code and proving one real client interaction,
not rebuilding intake/review or another orchestration layer.

Prepare all reviewable work before asking for activation permission:

1. Inspect current source, Git/PR/CI and the existing operator startup configuration.
   PR #255 is merged as 7847288; do not recreate the correction. Run 34664119693 and
   the documentation PR may still be live; poll their exact handles/results.
2. Identify the exact deployable commit, current runtime checkout, database version,
   retained storage, existing policy bindings and startup command without printing keys,
   connection secrets or signed URLs. Verify prerequisites rather than copying stale paths.
3. Prepare an explicit synthetic-only backup/restore, migration-0047, restart and rollback
   plan. Rehearse relevant migration/compatibility checks on a disposable database.
4. Present the concrete plan for owner approval. **Do not update/restart the existing
   app, migrate its database or alter OAuth/tunnel configuration without that approval.**
5. After approved activation and read-only readiness checks, refresh client discovery and
   conduct one selected DOCX -> scan -> text/picture reads -> typed Scope proposal ->
   user browser confirmation -> reopened Scope -> original-bearing ZIP journey.
   Human confirmation is not granted by a chat message or an automated browser test.

Relevant files/components: `scripts/run_draft_scope_demo.py`,
`src/classifire/draft_client_word_tools.py`, `src/classifire/draft_client.py`,
`src/classifire/services/draft_client_capabilities.py`, shared Word intake/review,
client request UI, project-package/import services and
`src/classifire/migrations/versions/0047_draft_scope_docx_sources.py`.

Prerequisites/blockers: successful exact-head/current-main checks, owner activation
approval, available existing test deployment/OAuth/tunnel, runtime attachment metadata
and separate user confirmation. Word code is merged; activation is not already approved.
Keep the loopback Excel app and retained test data intact until the approved update.
Do not widen grants, repeat OAuth setup or use customer evidence implicitly.

Validation: use the exact selected checkout's src in PYTHONPATH. Run targeted tests only
when preparing a new runtime/migration combination or diagnosing an actual failure:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
# Disposable PostgreSQL only; start/verify an isolated test database before this block.
$env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15433/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest tests/test_draft_client_word.py tests/test_draft_scope_docx_review.py tests/test_migrations_draft_scope_docx_sources.py -p no:cacheprovider --basetemp C:\CLASSIFIRE\.tmp\pytest-word-acceptance-next -o addopts= -q
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Use a fresh basetemp if the named path exists. Never point destructive fixtures at the
live database on 15432. Run applicable type/security checks for any code change and
inspect the browser/ZIP output. Use actual tool results, saved revisions/source hashes
and downloaded original bytes as acceptance evidence, not chat descriptions.

Definition of done: authorized updated runtime survives restart; current tools are
actually callable; separate user confirmation saves a traceable revision; two services
can share one opening while a separate blank opening remains service-free; unsupported
quantities/dimensions remain null; the downloaded ZIP contains the exact retained source.
No matching, pricing, technical approval or canonical release runs implicitly. Record
any unsupported input/client limitation rather than inventing evidence. For a necessary
code correction, continue through explicit staging, commit, push, PR and verified checks/
review/merge; no auto-merge shortcut or branch deletion.

## Validation performed for this reconciliation

Source/configuration/contracts and staged/unstaged inventories inspected; current PR/CI
and protection endpoint checked; listener checked read-only; one Alembic head verified.
Focused checks: `test_draft_scope_docx.py`, `test_draft_pricing_recipe_contract.py`
and `test_draft_pricing_evaluation_contract.py`: 32 passed in 10.15s. A local validator
checked 53 relative links plus explicit source paths across ten edited documents,
UTF-8/encoding markers and code fences; no errors. `git diff --check` passed.
No full local suite, live migration or live client acceptance was run for these docs.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE with one controlled Word-to-Scope-to-package client acceptance journey. First inspect AGENTS.md, Git/worktrees/upstream/diff, docs/PROJECT_STATE.md, current PR/CI and the existing test runtime; preserve unrelated changes and the conflicted C:/CLASSIFIRE root. Word PRs #252-#254 and test-clock correction #255 are merged; do not rebuild them. The loopback app on 8820 still runs the earlier Excel build. Inspect scripts/run_draft_scope_demo.py, Word client/intake/review services, client requests, project packages and migration 0047. Prepare an exact commit, backup/restore, migration, restart and rollback plan; verify current-main CI and rehearse relevant checks in disposable PostgreSQL15433, never live15432. Obtain explicit approval before updating/restarting/migrating the app or changing OAuth/tunnel configuration. After approval, refresh tools and prove synthetic DOCX upload, scan, text/image reads, typed proposal, separate user browser confirmation, reopening and exact original-bearing ZIP download. Keep unknowns null and run no downstream capability implicitly. Validate affected Word/client/review/migration/package pytest tests with this checkout's PYTHONPATH and fresh basetemp, inspect browser/ZIP outputs, and run relevant Ruff/Mypy/Bandit checks for code changes. Fix only evidenced issues; classify and commit explicit files, push, reuse/create the correct PR, and merge only after observed exact-head successful CI/reviews. Poll live jobs without restarting; never use --auto as a substitute for checking gates. Record actual runtime/revision/hash/merge evidence and limitations; do not claim production readiness or use customer evidence.
```

The full ordered recommendations and uncertainties are in
[PROJECT_STATE.md](./PROJECT_STATE.md#recommended-next-actions). This prompt targets I2
preparation; incomplete hosted checks remain prerequisites, not reasons to reimplement I1.
