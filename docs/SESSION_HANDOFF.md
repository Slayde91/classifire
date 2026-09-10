# CLASSIFIRE Session Handoff

## Start Here / Next Session

Worktree: C:/CLASSIFIRE/.tmp/auth0-issuer-url-20260910.
Branch: feat/external-client-demo-20260911, based on shared main 8b2c72f (PR #243).
PR #243 required and post-merge CI passed. Preserve the conflicted root and unrelated work.

Validation: three launcher tests passed in 104.19 seconds, covering actual main.py/MCP
startup through TestClient, restarts, unsigned request denial, policy preservation, role and
identity/scope refusals, and the original local-token mode. Full Ruff and Mypy (222 source
files) and the application Bandit scan passed. The dedicated PostgreSQL trial was prepared and reopened with the same
estimator ID, one active estimator and zero projects; no listener started. Required CI and
real human OAuth/ChatGPT linking remain outstanding.

First task: finish validation/publication of the external-policy demo launcher, then use
it for the approved synthetic-only Auth0/tunnel trial. Files: scripts/run_draft_scope_demo.py,
tests/test_external_client_demo.py, DRAFT_CLIENT_V1_CONTRACT.md and current project docs.
Success: an isolated estimator is prepared without serving; exact operator policy survives
startup/restart; missing authentication and mismatched/broader identities/scopes fail closed;
existing administrator demos cannot be adopted; original --client-demo still works.

Validation: PYTHONPATH must point to this worktree's src. Run pytest on
 tests/test_external_client_demo.py with no cacheprovider and a unique basetemp, full Ruff,
and relevant CI before merge. The test exercises main.py/MCP/login/brand endpoints through
TestClient and subprocess restarts; it does not prove actual Auth0/ChatGPT linking.
For real PDF trials use only the separately marked classifire_draft_chatgpt_demo database,
existing loopback PostgreSQL/ClamAV, and the protected operator directory from the runbook.
No guessed human subject, callback or M2M-to-human mapping is permitted.

### Recommended Prompt for New Session

Inspect AGENTS.md, Git/worktree state, code/tests and PR checks before editing. Continue
feat/external-client-demo-20260911 in the isolated auth0-issuer-url-20260910 worktree; preserve
unrelated changes and the conflicted root. Finish the existing external-policy launcher
increment through tests/test_external_client_demo.py, full Ruff, required CI and scoped
commit/push/PR/merge. It must prepare only a synthetic estimator, preserve exact operator
policy, reject wrong directory/user/resource/scope bindings and retain --client-demo.
Reuse ClientAuthority/main.py; do not create another auth layer. Then resume the approved
synthetic Auth0/tunnel PDF-to-reviewed-Scope trial using the contract and local operator
runbook at C:/CLASSIFIRE/.tmp/chatgpt-trial-setup-20260910.md. Verify actual human subject,
client and ChatGPT callback; keep the M2M probe unmapped. No paid services, customer evidence,
canonical writes or secret output. Do not redo proven work or claim connection success
from token fixtures alone. Record actual validation, Git results and remaining blockers.

Earlier checkpoints below are historical.

## Pre-merge client permission correction

PR #241 follow-up fixes the client grant check for v3 packages containing retained foreign
archives. Both technical and estimating grants are required regardless of archive version;
native v3 without an origin does not acquire unrelated grant requirements. Ten client-capability
tests passed in 41.20 seconds, including six actual-token scope combinations. Full Ruff and
Mypy (222 files) and the affected-file Bandit scan passed. Current-head CI must pass before
merge; the earlier d452d33 run does not validate this correction. No deployment occurred.


## Current branch and project context

Active worktree: `C:/CLASSIFIRE/.tmp/package-pdf-evidence-20260910`.
Branch: `feat/package-pdf-evidence-20260910`, created from `origin/main` at
`8164d29dbcc6ffc4fe4f309c5fd8bf583cc7f3fd` (PR #240 merge). PR #240 required run
34365672716 and post-merge run 34368312777 passed. PR #239 is merged at `a54a128`.
The earlier PDF image/review worktree is clean. Preserve the conflicted legacy root,
all unrelated worktrees and all customer/operational data. No deployment occurred.

## Active implementation and local changes

Candidate ProjectPackage v3 explicitly includes up to four reviewed local project PDFs.
The existing UI selects files, previews membership, saves and downloads an immutable ZIP.
Empty PDF selection omits the new field, preserving v1/v2 selection serialization.
V3 keeps existing extended archive/member/recursion bounds. Supplier source bodies remain
withheld. Import retains exact evidence bytes and a v2 origin mapping, leaving Scope claims
foreign. Original ZIP and ancestor re-export must check every binary's current scan state.

Changed code: `draft_project_packages.py`, `draft_package_import.py`,
`draft_package_materialization.py`, `draft_import_reports.py`,
`draft_project_package_ui.py`, and the project/imported-package templates.
New test: `tests/test_draft_package_pdf_evidence.py`. Architecture, roadmap, project state,
package contract and this handoff describe the candidate; these are not completion claims.
Candidate commits are on PR #241; verify its latest head, CI and merge state before resuming.

## Findings and verification

Final PDF-evidence tests: 3 passed in 57.58 seconds. These cover real HTTP selection/save/
download, source drift and semantic tamper refusal, two import generations, reopen/exact bytes,
foreign permission refusal, shared quarantine and active PDF actions. Earlier broader package,
import, attachment and UI regression: 28 passed; stricter attachment-policy regression: seven
passed (overlapping coverage). Full Ruff and diff checks passed on the final code. Full Mypy
(222 files, local untyped-import diagnostics disabled) and Bandit passed. No production code
changed after those checks. Required GitHub checks and publication remain outstanding.

Initial tests exposed and corrected fixture route ordering, an explicit empty v3 origins
inventory, source-purpose collision, and global native-PDF source uniqueness. Do not weaken
those guards: imported evidence uses a separate owned imported-attachment binding while
preserving native PDF storage purpose. Inspect `evidence_intake()` carefully: it must retain
strict imported PDF format checks as well as purpose, ownership and shared quarantine.
Legacy native upload behavior must remain unchanged. No migration has been added.

Browser automation could not initialize. HTTP tests are not visual browser acceptance.
The operator's existing HTTPS test URL and OAuth provider were requested for the real
ChatGPT trial; no credentials requested and no answer received at this snapshot. That trial
remains unverified. Excel client upload stays after the PDF trial; this package work proceeds
independently against synthetic evidence.

## Start Here / Next Session

First publish the validated portable reviewed-PDF package lifecycle before another feature.
This closes the verified gap where downloaded packages carry PDF references but omit the
original project PDFs needed outside CLASSIFIRE. Inspect Git and current tests before editing.

Prerequisites: isolated worktree, shared venv, disposable PostgreSQL on port 15432, synthetic
fixtures only. Reuse source intake, exact archive validation and imported attachment guards.
Do not change stored-file purpose or global native-PDF source uniqueness to force tests.

```powershell
$env:PYTHONPATH=(Join-Path $PWD 'src')
$env:CLASSIFIRE_POSTGRES_TEST_URL='postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN='classifire-containment-test-drop-all'
C:/CLASSIFIRE/.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp C:/CLASSIFIRE/.tmp/pytest-package-pdf-next tests/test_draft_package_pdf_evidence.py tests/test_draft_project_packages.py tests/test_draft_package_import.py tests/test_draft_package_materialization.py tests/test_draft_import_reports.py tests/test_draft_project_package_ui.py tests/test_draft_package_import_ui.py
C:/CLASSIFIRE/.venv/Scripts/python.exe -m ruff check .
C:/CLASSIFIRE/.venv/Scripts/python.exe -m mypy src --disable-error-code=import-untyped
C:/CLASSIFIRE/.venv/Scripts/python.exe -m bandit -q -r src
git diff --check
```

Definition of done: explicit UI selection/save/download works; included bytes match reviewed
sources; import creates no trusted review claims; strict scan/format/permission/integrity
checks protect direct and ancestor downloads; legacy packages remain byte-compatible;
regressions and required CI pass; relevant docs are reconciled; reviewed changes are
committed, pushed, PR-reviewed as required and merged. Verify actual browser/restart where
available, otherwise label that acceptance incomplete. No deployment or real evidence use.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Inspect AGENTS.md, GOAL.md, Git status,
> docs/PROJECT_STATE.md, roadmap and the current diff in
> C:/CLASSIFIRE/.tmp/package-pdf-evidence-20260910 on feat/package-pdf-evidence-20260910.
> Preserve the conflicted root and unrelated changes. Verify and publish the active ProjectPackage v3
> opt-in reviewed-PDF lifecycle: shared package composition/inspection, exact source binding,
> existing UI save/download, owned imported attachments, foreign review state and guarded
> scan/download/re-export. Inspect evidence_intake's purpose and strict PDF format policy;
> never weaken storage or ownership guards. Preserve legacy v1/v2 bytes and source withholding.
> Run the documented package/import/attachment/UI regressions, Ruff, Mypy, Bandit and diff
> checks; verify rendered UI when tooling works and label any limitation. Update documentation
> from results, classify/stage only intended files, commit, push, create a main-targeted PR and
> merge only after required current-head CI passes. No customer evidence, deployment or
> speculative adjacent feature. Real ChatGPT linking awaits operator HTTPS/OAuth details.
