# CLASSIFIRE Session Handoff

## Current branch and project context

The current source-linked client Scope candidate is in
`C:/CLASSIFIRE/.tmp/client-pdf-scope-review-20260910` on
`feat/client-pdf-scope-review-20260910`, based on main `2150286` (merged PR #238).
PR #238's post-merge run 34358486420 passed. The independent download deadline fix is
PR #239. Its initial run 34360392428 failed Linux type checking on the Windows-only
CREATE_NO_WINDOW constant. Correction `000aa3f` uses an explicit platform guard; the
Linux-targeted type check and 33 retrieval tests passed. Recheck current-head CI before merging. Do not confuse the two branches or test scopes.
Preserve the conflicted root and all unrelated local work.

ADRs 0001/0002 remain accepted: shared deterministic core, independent capabilities,
optional AI and transitional OpenClaw. This increment changes neither architecture direction
nor canonical authority. No deployment, customer evidence or real provider run occurred.

## Current implementation and relevant changes

`review_pdf_scope` extends the existing `propose_capability` union with a retained source,
exact document hash/page, expected Scope revision, full graph and explicit target IDs.
Preparation calls the shared PDF preview and retains a pending request only. The browser
shows source raster/text, selected item labels and proposed graph. Confirmation passes the
verified preview hash to the existing PDF save service, which rechecks exact dependencies
and appends server-generated page/entity/reviewer references. No downstream capability runs.
Generic Scope edits and the original command hash shapes remain compatible.

Relevant code:
- `src/classifire/services/draft_client_capabilities.py`
- `src/classifire/services/draft_client_requests.py`
- `src/classifire/draft_client_capability_tools.py`
- `src/classifire/templates/draft_client_request.html`
- `tests/test_draft_client_pdf_scope.py`
- Shared services: `draft_pdf_intake.py`, `draft_scope.py`.

The five architecture/roadmap/state/handoff/client-contract documents are also updated.
No unrelated changes were observed in this isolated worktree; classify the actual diff again
before staging. PR #239's files belong to its separate clean worktree.

## Validation and limitations

The initial three PostgreSQL/MCP tests passed, proving human-confirmed page linkage,
source-change refusal and owner/scope/forged-target refusal. They verify the real rendered
HTTP review and PNG endpoint. The broader 57-test client/page-review regression passed in 294.69 seconds. Full Ruff, Mypy (222 files, local untyped-import
diagnostics disabled) and Bandit passed. The final no-downstream-record confirmation
test also passed in 17.50 seconds.

A synthetic review HTML snapshot is at
`C:/CLASSIFIRE/.tmp/pytest-client-pdf-review-regression/test_client_pdf_review_saves_o0/synthetic-review.html`.
Browser automation failed twice at runtime initialization with a sandbox helper error.
Visual browser acceptance is unverified; HTTP tests alone do not finish that milestone.
The temporary loopback render server has been stopped. An existing service on port 8816
was preserved. Real HTTPS/OAuth/ChatGPT linking remains unproven; the operator's deployment
URL and OAuth provider have been requested, without requesting credentials.

## Start Here / Next Session

First finish verification and publication of this source-linked Scope increment. It closes
an actual provenance gap in the planned ChatGPT PDF journey: generic edits cannot attach
trusted page references. Inspect Git, tests and PR state before editing; do not rebuild it.

Prerequisites: preserve root recovery evidence; use the isolated worktree and shared venv;
use only the disposable PostgreSQL test database and synthetic sources. Verify PR #239's
required checks before merging it, then reconcile current main without dropping local work.
Use existing human confirmation and page-save guards, never client-declared review authority.

Validation commands (choose a fresh temporary directory when rerunning):

```powershell
$env:PYTHONPATH=(Join-Path $PWD 'src')
$env:CLASSIFIRE_POSTGRES_TEST_URL='postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN='classifire-containment-test-drop-all'
C:/CLASSIFIRE/.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp C:/CLASSIFIRE/.tmp/pytest-client-pdf-review-next tests/test_draft_client_pdf_scope.py tests/test_draft_client_capabilities.py tests/test_draft_client.py tests/test_draft_pdf_scope_review.py
C:/CLASSIFIRE/.venv/Scripts/python.exe -m ruff check .
C:/CLASSIFIRE/.venv/Scripts/python.exe -m mypy src --disable-error-code=import-untyped
C:/CLASSIFIRE/.venv/Scripts/python.exe -m bandit -q -r src
git diff --check
```

Definition of done: pending proposal leaves Scope unchanged; authorized human review displays
source and proposed graph; confirmation saves exact page/target/reviewer provenance; stale,
foreign, invalid and replayed actions fail closed; prior commands work; tests/static checks
pass; intended files are committed/pushed and required PR CI passes before merge. Record any
remaining visual acceptance limitation honestly. The subsequent product task is the actual
ChatGPT PDF-to-reviewed-Scope journey through an operator-controlled HTTPS/OAuth deployment.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from repository evidence. Inspect AGENTS.md, GOAL.md, Git/worktrees,
> docs/PROJECT_STATE.md, the roadmap, current PR #239 checks and the active diff before editing.
> Preserve the conflicted root and unrelated work. Finish the source-linked client Scope
> increment in C:/CLASSIFIRE/.tmp/client-pdf-scope-review-20260910 on
> feat/client-pdf-scope-review-20260910: review_pdf_scope must reuse shared PDF preview/save
> through the existing human-confirmation workflow, bind exact page/scan/Scope/targets and
> retain server-generated provenance without downstream actions. Inspect the typed command,
> request dispatcher, review template and test_draft_client_pdf_scope.py; run the documented
> client/PDF/PostgreSQL regressions, Ruff, Mypy, Bandit and diff checks. Verify the actual
> rendered browser page when automation works; otherwise keep that acceptance unproven.
> Reconcile PR #239/main safely, classify and commit only intended files, push, create/update
> the direct-main PR and merge only after required CI passes. Then pursue the real ChatGPT
> PDF-to-Scope trial using the operator's HTTPS/OAuth deployment; do not guess provider hosts,
> bypass review gates, process customer data or start unrelated speculative work.
