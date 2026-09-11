# CLASSIFIRE Session Handoff

Validation checkpoint: 44 affected tests passed; six PostgreSQL-dependent tests
were skipped locally. Full Ruff, Mypy (222 files) and Bandit passed. Required
current-head CI/publication and refreshed-client acceptance remain pending.

## Current Start Here / Next Session (supersedes historical handoff below)

Branch: fix/client-proposal-schema-discovery, based on verified origin/main 5c8ee72
(PR #247 merged; required CI passed). Worktree: C:\CLASSIFIRE\.tmp\auth0-issuer-url-20260910.
Preserve the legacy root's unrelated edits, staged additions and four DU conflicts.
First task: finish proposal-schema discovery and safe error feedback, then verify merge.
Files: draft_client.py, services/draft_client_capabilities.py,
services/draft_project_packages.py, tests/test_draft_client.py and the client contract.
Done: actual tools/list has resolvable domain fields, proposal bytes stay compatible,
errors reveal useful paths without values, human confirmation remains mandatory,
relevant tests and required CI pass, and merge is verified.

Prerequisites: isolated worktree src on PYTHONPATH, unique pytest temp directory;
PostgreSQL tests need a disposable test database, never the live trial database.
Run client, capability, PDF-scope and package-evidence pytest suites, Ruff, Mypy, Bandit.
Refresh-client acceptance requires an authorized runtime update; do not implicitly
restart the live app or expand grants. The local package-verification-receipt.json
under C:\CLASSIFIRE\.tmp\chatgpt-trial-tools-20260910 records the prior Scope-only
synthetic trial PASS: three ZIP members, five references, original PDF byte-identical.
No application import was performed. One stale page-2 observation needs normal review.

### Recommended Prompt for New Session

Inspect AGENTS.md, GOAL.md, current Git/worktrees, shared main, PR/CI, project state and
roadmap before editing. Preserve unrelated changes and the conflicted C:\CLASSIFIRE
root. Finish fix/client-proposal-schema-discovery if not merged: inspect draft_client.py,
draft_client_capabilities.py, draft_project_packages.py and test_draft_client.py.
This is next because the successful synthetic PDF trial required manual JSON repairs.
Prove discovery exposes existing domain fields, raw request hashes stay compatible,
invalid-field feedback hides submitted values, and human confirmation remains required.
Run test_draft_client, test_draft_client_capabilities, test_draft_client_pdf_scope and
test_draft_package_pdf_evidence with worktree src on PYTHONPATH, unique temp storage
and a disposable PostgreSQL test DB, plus Ruff, Mypy and Bandit. Continue autonomously
through validation, classification, explicit-path commit, push, PR and merge after
required CI/review; verify the merge. Arrange refreshed-client acceptance without
assuming deployment authorization. Do not rebuild proven OAuth/PDF transport, expand
grants, use customer evidence or speculate about missing rejected payloads. After
this correction, Excel client intake through existing review services is the next
visible increment. Preserve all four product capabilities and production gates.



Validation for this increment: affected client/launcher suites passed (one PostgreSQL-only
test skipped locally); final OIDC regressions and full Ruff passed. Mypy checked 222
source files successfully and Bandit passed. Required CI and live activation remain pending.

## Start Here / Next Session

Current fix branch: `fix/auth0-oidc-token-compatibility-20260912`, isolated worktree
`C:\CLASSIFIRE\.tmp\auth0-issuer-url-20260910`. Preserve the conflicted legacy root.
PR #246 merged at `6c3b9d0` with required CI passed; external resource is active.
Human login succeeded, but discovery returned no callable tools. A verified diagnostic
confirmed the two-recipient Auth0 audience and openid/email scopes as admission blockers.
The owner approved the bounded default-off compatibility amendment and test restart.

First task: finish and verify this correction, then prove real authenticated discovery.
Relevant files: `src/classifire/draft_client_auth.py`, `tests/test_draft_client.py`,
`tests/test_external_client_demo.py`, `docs/DRAFT_CLIENT_V1_CONTRACT.md`. Run affected
pytest suites, Ruff, Mypy, Bandit and required CI. Current grants remain read/propose/export;
identity scopes must not authorize tools. No canonical authority or customer data trial.

Prerequisites: protected operator policy/keys, marked synthetic database, local app,
private tunnel and Auth0 session. Inspect the ignored operator runbook for current live
state without printing credentials. Publish only reviewed paths; verify merge before
activating the approved policy and restarting. Completion requires a signed read-only
MCP result and actual ChatGPT `list_draft_projects`; a connected label is insufficient.
The larger synthetic PDF/review/package journey remains next after discovery works.

## Recommended Prompt for New Session

Inspect AGENTS.md, Git/worktree status, current source/tests, PROJECT_STATE and roadmap
before editing. Preserve the dirty legacy root and unrelated changes. Continue the
approved Auth0 OIDC compatibility fix in the isolated auth0-issuer-url-20260910 worktree;
verify whether its branch has already merged before repeating work. The verified token
has the exact MCP audience plus issuer /userinfo and openid/email scopes; the opt-in
exception must reject other recipients/scopes and grant only existing business rights.
Inspect draft_client_auth.py, test_draft_client.py, test_external_client_demo.py and the
client contract. Run affected pytest suites with isolated PYTHONPATH and a unique temp
directory, Ruff, Mypy, Bandit and required CI. Continue scoped classification, commit,
push, PR and merge where safe. Read the ignored operator runbook for credentials-free
live context; activate/restart only the approved synthetic policy. Prove signed tools/list
and actual ChatGPT list_draft_projects before proceeding to the synthetic PDF/review/package
journey. Human login may be needed; do not fabricate results or expand permissions.

## Historical handoff (superseded where inconsistent above)

## Active correction: exact external OAuth resource

Validation: affected client and launcher suites passed (one PostgreSQL-only test skipped
locally); full Ruff, Mypy (222 source files) and Bandit passed. Required CI remains pending.

The real ChatGPT request uses the tunnel HTTPS address as its OAuth resource. The previous
policy derived its audience from the local browser origin. Optional operator-owned
`oauth_resource` now separates those values; omission preserves `base_url + "/mcp"`.
Explicit resources require HTTPS without credentials, query, fragment or whitespace.
Discovery and strict token verification use the same exact resource; changing resource,
issuer or browser origin requires restart. All signature/time/permission checks remain.
No domain schema, database migration or additional client grants are introduced.

Human Auth0 login, local authenticated MCP access and the approved tunnel discovery
correction were verified; the exact ChatGPT callback is registered. This code increment
still needs completed regression and required CI/publication before configuring the
matching synthetic Auth0 API/policy and restarting. Real ChatGPT token shape (including
OIDC scopes) and the full PDF-to-reviewed-Scope-to-package journey remain unproven.

## Current branch / next task

Use `fix/external-oauth-resource-20260911` in the existing isolated worktree. Finish tests
in test_draft_client.py and test_external_client_demo.py, Ruff/Mypy/Bandit, scoped review,
commit/push/PR and required-CI/merge. Then configure the observed exact tunnel resource
in Auth0 and the protected operator policy and restart the approved synthetic trial.
Preserve unrelated work, current permission scopes and human confirmation boundaries.
Read the local operator runbook before touching live configuration. The older prompt below
predates the observed mismatch; this continuation is the current first task.


## Start Here / Next Session

Worktree: `C:/CLASSIFIRE/.tmp/auth0-issuer-url-20260910`.
Documentation branch: `docs/connected-trial-handoff-20260911`, based on verified shared
main `255e3c68fd44b1b681563ce851a260793edd9cb0` (PR #244). Recheck branch/PR state before
editing. Preserve the conflicted legacy root and unrelated worktrees. The launcher branch
was clean and pushed at `a951b6d`; these four documentation files are the current scoped edit.

PR #244 required run 34496922963 passed. Post-merge run 34499154918 was observed running;
inspect its terminal status. PR #243 required/post-merge CI passed. Launcher tests cover
startup, restart, policy/identity/role refusals and legacy mode (three passed); both focused
optional-nbf security regressions passed again. None proves a live ChatGPT connection.

**First task:** finish the already approved synthetic human OAuth/tunnel trial, then prove
one visible PDF-to-reviewed-Scope-to-package journey. The launcher is merged; do not redo it.

**Prerequisites and files:** `scripts/run_draft_scope_demo.py`,
`src/classifire/draft_client_auth.py`, `src/classifire/draft_client.py`,
`docs/DRAFT_CLIENT_V1_CONTRACT.md`, `tests/test_external_client_demo.py` and
`tests/test_draft_client.py`. The local operator runbook is
`C:/CLASSIFIRE/.tmp/chatgpt-trial-setup-20260910.md`; protected configuration, the PKCE
helper and synthetic data are under its trial-tools directory, excluded from Git.
Use only the marked `classifire_draft_chatgpt_demo` database and existing loopback
PostgreSQL/ClamAV. Do not touch customer/canonical databases.

**Runtime checkpoint / blockers:** dedicated Auth0 human client and exact loopback callback
exist; synthetic API permissions are read/propose/export only. Machine probe remains
read-only and unmapped. Human login is pending. Inspect the existing callback process and
any private receipt before restarting; an observation timeout is not process termination.
The helper rejected wrong state under an idle concurrent connection and listens only on
127.0.0.1. No successful human policy or ChatGPT connection was verified at this checkpoint.
Browser automation was unavailable. Obtain the actual ChatGPT callback from its management
page; no guessed URL, wildcard or tenant-wide setting change. Auth0 CLI credentials are
relative to the original root directory in this Windows environment; its credential path
is locally Git-excluded. Never print, stage or copy that file into a worktree.

**Validation and definition of done:** verify actual code+PKCE token through ClientAuthority,
map only that authenticated human to the prepared estimator, check app/tunnel health and
unsigned refusal, then perform synthetic PDF upload, text/image inspection, source-linked
proposal, separate same-user browser confirmation and exact package download. Verify the
saved evidence references and retained PDF bytes. A proposal is not confirmation. Record
failures and unresolved review-link reachability honestly; do not weaken guards.
If code changes, set `$env:PYTHONPATH=Join-Path $PWD 'src'`, run
`python -m pytest tests/test_draft_client.py tests/test_external_client_demo.py -p no:cacheprovider --basetemp <unique-temp>`,
relevant PDF/client tests and `python -m ruff check .`; run Mypy/Bandit when source changes
warrant them. Complete required current-head CI and normal reviewed publication.

### Recommended Prompt for New Session

Inspect AGENTS.md, Git/status, current main/PR checks, PROJECT_STATE and the client contract
before editing. In the isolated auth0-issuer-url-20260910 worktree, preserve the conflicted
root and unrelated local work. PR #244 merged the external-policy estimator launcher at
255e3c6; do not rebuild it. The highest-value task is the approved synthetic-only human
Auth0/private-tunnel PDF-to-reviewed-Scope-to-package trial: local tests do not prove a real
ChatGPT journey. Read C:/CLASSIFIRE/.tmp/chatgpt-trial-setup-20260910.md and inspect existing
callback processes/receipts first. User sign-in and the actual ChatGPT callback are remaining
prerequisites; never invent identities or map the machine probe as human. Reuse
run_draft_scope_demo.py, draft_client_auth.py, draft_client.py and the marked synthetic
PostgreSQL/ClamAV setup. Done means real PKCE authorization, exact estimator binding,
verified app/tunnel readiness, denied unsigned requests, synthetic PDF text/image inspection,
source-linked proposal, separate same-user confirmation and exact package download with
retained provenance. Keep secrets out of output/Git; no customer evidence, paid services,
canonical writes or relaxed guards. For necessary fixes run test_draft_client.py,
test_external_client_demo.py, affected PDF tests, Ruff and required CI with PYTHONPATH=src
and unique pytest basetemp. Continue autonomously through implementation, validation,
classification, scoped commit, push, PR and merge where safe; record actual outcomes and
blockers. Do not substitute fixtures or speculative infrastructure for end-to-end proof.

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
