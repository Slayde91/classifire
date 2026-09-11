# CLASSIFIRE Session Handoff

## Start Here / Next Session - Word client increment

Use `C:\CLASSIFIRE\.tmp\word-client-20260912`, branch
`feat/word-client-20260912`, based on c132709. Preserve the conflicted legacy root.
The local adapter/typed command/template/tests and client contract are uncommitted.
PR #253 contains only the parent Word review/package work and remains under required
CI 34657065137; verify current state before integrating its merge. No Word deployment
has occurred; the existing Excel app on port 8820 must remain untouched.

First task: finish the Word client interaction's gated publication.
Files: `draft_client_word_tools.py`, `draft_client.py`,
`services/draft_client_capabilities.py`, `services/remote_file_retrieval.py`,
`templates/draft_client_request.html`, `tests/test_draft_client_word.py`,
`tests/test_remote_file_retrieval.py`, and `docs/DRAFT_CLIENT_V1_CONTRACT.md`.
Prerequisites: isolated synthetic PostgreSQL on 15433 (never live 15432), selected
worktree src in PYTHONPATH and parent PR merge. 40 integrated checks and one Edge journey passed; screenshot inspected.
Mypy (229), Ruff and Bandit passed. Final authentication/PDF regressions and corrected tool-catalogue test passed;
all 81 distinct selected tests now pass. No validation process remains running.

Validation: pytest Word client, client workbooks, client capabilities and remote file
retrieval tests; Ruff, Mypy and Bandit; isolated Edge journey via
`C:\CLASSIFIRE\.tmp\test_word_client_playwright.py`. Existing process handles/results
are in the ignored operator runbook. Poll running handles before launching anything.
Done: exact discovery schema, retained text/picture reads, visible proposal and separate
human confirmation prove one evidence-linked revision with unknowns preserved; relevant
regressions pass, docs match evidence, reviewed commit is pushed and required CI/review
passes before a verified merge. Live activation is a separate permission boundary.

### Recommended Prompt for New Session

Continue CLASSIFIRE in `C:\CLASSIFIRE\.tmp\word-client-20260912`. Inspect AGENTS.md,
Git/diff, project state, roadmap, running processes and PR #253 before editing. Finish
the existing Word MCP/typed-review increment because standalone Word evidence needs
the same governed client path as PDF/Excel. Reuse its adapter, capabilities, request
template and tests; preserve unrelated local work and the live Excel app. Verify parent
PR merge, run Word/client-workbook/capability/retrieval pytest tests in isolated PostgreSQL
15433 with this worktree's PYTHONPATH, run Ruff/Mypy/Bandit and the synthetic Edge review
journey. Fix evidenced failures, update docs, classify changes, commit explicit paths,
push, open PR and merge only after required checks/review pass. Completion requires
exact discoverable schemas, no Scope write before browser confirmation, traceable saved
evidence and preserved unknowns. Do not deploy Word, widen grants, process real evidence
or perform speculative architecture work. Poll existing jobs rather than restarting.

Validation checkpoint: 105 integrated Word/PDF/Excel/package/import/report tests
passed in 427.25 seconds (the deliberate duplicate-ZIP fixture emitted its expected
warning). Another 50 mixed-evidence/output checks and one complete Edge journey
passed. Ruff, Mypy (228 source files), Bandit and single Alembic head passed. The final
73 client/PDF review regressions also passed (279.06 seconds). Local validation is
complete; required hosted CI/review and actual merge remain to be verified.

## Start Here / Next Session: finish Word review and portability publication

First inspect `C:\CLASSIFIRE\.tmp\word-scope-review-20260912`, branch
`feat/word-scope-review-20260912`, its diff/head/upstream, PR and required CI. It is
based on verified main c5d4774 (PR #252 merged after CI 34653404693). The parent
inspection checkout is separate; the conflicted legacy root remains recovery evidence.

Candidate: shared Word graph editor, explicit text/picture selection, exact no-write
preview and same-user browser confirmation; Scope v7 provenance; optional original
Word membership in ProjectPackage v5; import/re-export quarantine and all report
profiles. Relevant files: `draft_scope_docx_ui.py`, `draft_scope_docx_review.py`,
`draft_scope_evidence.py`, shared `draft_scope.js`/templates, package/import services,
report render-version services, tests/test_draft_scope_docx_review.py and
 tests/test_draft_word_evidence_outputs.py. Contract: DRAFT_SCOPE_DOCX_V1_CONTRACT.md.

Verified earlier in this candidate: 13 integrated Word review/package tests, 50
mixed-evidence/output regressions and the complete synthetic Edge journey. Exact
Word upload/download bytes, separate blank/shared openings, unknown quantities,
confirmation and reload were checked. Review/package screenshots and PDF cover/
provenance page were inspected. Browser harness is ignored local
`.tmp/test_word_review_playwright.py`; downloaded ZIP is
`.tmp/playwright-word-scope-package.zip`. These are synthetic ASGI-app tests, not a
live ChatGPT/Word deployment or customer acceptance.

Prerequisites and blockers: use only disposable PostgreSQL on loopback15433, database
`classifire_containment_test`, with explicit destructive-test opt-in. Never point
these fixtures at the running app's database15432. Existing app on8820, OAuth/tunnel,
PDF trial revision3 and approved Excel activation remain unchanged. Do not deploy
Word or run a live migration without separate authorization. Real ChatGPT Excel
acceptance still awaits refreshed tools and separate human confirmations; independent
Word development need not wait for it. No canonical writes/locks/releases are authorized.

Validation: set PYTHONPATH to this worktree's src; use unique pytest basetemp and
`-p no:cacheprovider -o addopts= -q`. Run Word review/intake, PDF/Excel review,
package/import, all evidence-report and client regressions. Run `python -m ruff
check .`, `python -m mypy src`, `python -m bandit -r src`, `python -m alembic heads`.
For Playwright add this worktree's tests and `.tmp/playwright-tools-20260911` to
PYTHONPATH; its disposable route bridge uses HTTPS and lets Edge follow redirects.

Definition of done: current-head local checks pass; visible review/reopen/download
and provenance are verified; exact diff contains no secrets/unrelated work; contracts,
state, architecture and roadmap agree; commit/push/PR pass required CI/review and
actual merge commit is recorded. Do not restart a live CI run due to polling timeout.
After verified merge, the next feature is thin Word client tools over the same core;
no duplicated parsing, graph schema or client-side confirmation power.

### Recommended Prompt for New Session

Finish CLASSIFIRE's Word review/package milestone through verified merge. Inspect
AGENTS.md, GOAL.md, docs/PROJECT_STATE.md, roadmap, architecture, Git/worktrees and
PR/CI before editing. Use feat/word-scope-review-20260912 in its isolated .tmp
worktree; preserve unrelated local work and the conflicted root. Parent PR #252
merged at c5d4774. The candidate adds Word text/picture-linked human review, Scope
v7, ProjectPackage v5 originals and report/import provenance; do not rebuild proven
work. Inspect draft_scope_docx_ui.py, services/draft_scope_docx_review.py, shared
scope evidence/editor, package/import/report services and their Word tests/contracts.
Complete any remaining regression or publication gap: use disposable PostgreSQL15433
with explicit test opt-in, affected pytest, Ruff, Mypy, Bandit, one Alembic head and
the synthetic Playwright review/reopen/exact-download journey. Done means verified
provenance/unknowns/security/history, aligned docs and a current-head CI/review-gated
merge with recorded commit. Continue autonomously through fixes, validation,
classification, commit, push, PR and merge where safe; poll live jobs without
restarting them. Do not deploy, change OAuth, use customer evidence or grant canonical
or release authority. If already merged and proven, report that evidence instead of
repeating it; identify thin Word client access as the next feature.

The following workbook handoff is historical runtime context, not a new restart request.

## Start Here / Next Session: prove refreshed ChatGPT Excel acceptance

PR #249 merged at a02e895; PR #250 merged at
27cd8bf114cb39caff42ae7150be0d66505fd01f after required CI 34609140246 succeeded.
Do not repeat implementation/publication. This documentation branch is
docs/workbook-trial-activation-20260912 in the matching .tmp worktree; inspect its
actual head/PR before publishing or treating it as merged.

### Current runtime and preserved work

The user approved the synthetic update after merge, and it completed. Runtime
checkout: C:\CLASSIFIRE\.tmp\package-workbook-evidence-20260911,
branch feat/package-workbook-evidence-20260911, tested head 8fc4855; loopback port
8820, process 23084/session 33857 at verification. Recheck process ownership before
any action. The same database, storage, OAuth policy and tunnel were retained.
Do not ask again for the already completed activation or restart unnecessarily.
Old trial checkout auth0-issuer-url-20260910 remains unchanged as recovery context.

Live Playwright login/package view and actual authenticated ChatGPT read passed.
Saved draft 4243d286-6be4-4063-9dcc-06c171c94aee remains revision 3, with Scope SHA
1ed4098d75b3680305186120dcad7e06dcac594fd396981cd6cf8600bb7820a2.
The check made no project changes. Screenshot .tmp/live-excel-package-readiness.png
was visually inspected. Merge monitor 85548 completed; session 33857 now runs the app,
not a waiting deployment job. Do not terminate it as cleanup.

Preserve unrelated root work (last inventory: 46 modified files, 14 additions,
four DU conflicts, 52 untracked entries; unreadable old test dirs limit inventory).
Implementation worktree is clean. Ignored operator helpers/receipts/fixtures are
local test evidence, not production files or canonical data.

### First task, prerequisites, validation and done

First task: complete the real ChatGPT Excel trial. Refresh of Classifire Test was
requested; current session metadata lacks the new tools. Inspect actual discovery
before proceeding, not a connected label. Use a new synthetic project through its
normal human-confirmed creation; preserve the PDF trial. Fixture:
C:\CLASSIFIRE\.tmp\synthetic-defect-register-chatgpt.xlsx (7,669 bytes; SHA
2fb41f642e0ebd30853c6493ea02860ab63634491f56209e0dac0fc30d2a54b5), copied exactly
from the tested package, two sheets/two pictures. It has not been uploaded.

Relevant files: draft_client_workbook_tools.py; services/draft_scope_xlsx.py,
draft_client_capabilities.py, draft_project_packages.py, draft_package_import.py,
draft_import_reports.py; client/package templates; workbook/client/package tests.
Contracts are shared with the standalone UI. Exact schemas and redacted field errors
are merged; do not recreate manual JSON workarounds or another schema pipeline.

Done: real discovered Excel tools, retained/clean source, bounded cell and image
inspection, evidence-linked proposal, separate human confirmation, saved Scope,
reviewed package selection with original XLSX, and downloaded original-byte/hash
verification. Preserve uncertainty, formula text without evaluation and explicit
picture associations. Do not run matching/pricing/release automatically.

For any required fix, use a fresh isolated current-main worktree. Set PYTHONPATH to
its src; run affected client/workbook/package tests with -p no:cacheprovider and a
unique --basetemp. PostgreSQL tests require a disposable loopback15433 database named
classifire_containment_test and explicit destructive-test opt-in; NEVER use live15432.
Test container is stopped. Run Ruff/Mypy/Bandit as warranted, then scoped commit/push/
PR/CI/merge. Existing local suites and required PR #250 CI passed; do not rerun them
without a new change or unresolved concern. Playwright is isolated in .tmp/playwright-tools-20260911.

Blocker for client acceptance: refreshed tools and selected synthetic attachment,
then actual human decisions. No implementation failure is established. Full production
scope remains incomplete; a successful synthetic trial is not production completion.

### Recommended Prompt for New Session

Inspect AGENTS.md, GOAL.md, Git/worktrees/main/PR/CI, current docs and code before
editing. Preserve unrelated root changes and the running synthetic app. PR #249/#250
are merged; test activation and read-only browser/ChatGPT verification passed. The
single next task is real refreshed-ChatGPT Excel acceptance, because code/browser
proof does not prove the client upload-to-download journey. Verify current runtime
and tool discovery; refresh is pending. Use .tmp/synthetic-defect-register-chatgpt.xlsx
in a separate synthetic project through normal human-confirmed creation. Inspect
workbook MCP/shared Scope/package services and their contracts. Prove upload, clean
scan, cells/pictures, proposal, human confirmation, saved Scope and package download
containing exact workbook bytes. Preserve unknowns, formula-text-only processing,
permissions and existing PDF trial; never auto-confirm human gates or run pricing.
If a concrete failure requires a fix, work on isolated current main, run affected
client/workbook/package regressions using disposable PostgreSQL15433 (never live15432),
explicit test opt-in, worktree src and unique temp; run Ruff/Mypy/Bandit and browser
checks. Continue autonomously through implementation, validation, classification,
commit, push, PR and passing-checks merge where safe. Do not rebuild merged work,
widen grants, use customer evidence or invent production completion. Record actual
acceptance evidence and the next verified gap.

Earlier handoffs below are historical; do not repeat their completed tasks.

Final local validation checkpoint: 51 existing client regressions passed. The three
workbook cases passed after restoring fixture registrations; the selected review-image
endpoint now has an explicit PNG assertion. Playwright rendered the evidence screen,
loaded its picture and confirmed the form, producing revision 2/four source references
in disposable PostgreSQL. The screenshot was visually inspected. This is an ASGI-test
browser proof, not a real hosted/ChatGPT Excel trial. The earlier 37-case workbook/
retrieval/deadline suite passed. Full Ruff, Mypy (223 files) and Bandit passed.
No required CI/merge or activation is claimed yet. Older failure notes below explain
resolved fixture setup and route-order corrections; they are not current blockers.


## Current Start Here / Next Session: finish Excel client candidate

Worktree C:\CLASSIFIRE\.tmp\client-excel-evidence-20260911; branch
feat/client-excel-evidence-20260911 based on verified origin/main bd591384 (PR #248).
Candidate edits are not yet committed/published. Preserve the separate running trial
worktree and conflicted legacy root. Trial PID 26048/session 1515 runs the merged
schema correction; its saved Scope remains revision 3. ChatGPT schema refresh requested.

First task: finish the Excel client lifecycle. Files: draft_client_workbook_tools.py,
services/draft_client_capabilities.py, services/remote_file_retrieval.py,
templates/draft_client_request.html, client registration and associated tests/contracts.
The new tools reuse existing XLSX services; review requires explicit row/image targets.
Initial workbook/download suite: 37 passed. Broader client suite: 51 passed plus three
fixture setup errors (import cleanup removed fixture registrations); explicit bindings
are restored and rerun is underway. Static checks passed. Do not call the failed run a pass.

Disposable PostgreSQL container classifire-client-xlsx-test-pg uses loopback 15433 and
classifire_containment_test; never run destructive fixtures against trial port 15432.
Set worktree src on PYTHONPATH and the documented test URL/explicit destructive opt-in;
run client/workbook/PDF/capability and remote-file/deadline regressions sequentially.
Playwright 1.62.0 is in ignored .tmp/playwright-tools-20260911, outside app dependencies.
An ignored test_xlsx_client_playwright.py renders/confirms via the ASGI test transport;
this proves browser interaction, not deployment. Do not run concurrent database suites.
Done: passing regression + review proof, accurate docs, scoped diff, required CI and
verified merge. Real refreshed-client Excel acceptance follows authorized activation.

### Recommended Prompt for New Session

Inspect AGENTS.md, GOAL.md, Git/worktrees/main/PR/CI and current project docs before
editing. Preserve unrelated work, the conflicted C:\CLASSIFIRE root and running trial
checkout. Finish feat/client-excel-evidence-20260911 in its isolated worktree. It is
next because PDF client review is proven and defect-register Excel support already
exists in shared standalone services. Inspect the workbook MCP adapter, typed
ReviewXlsxScope, explicit remote file-kind checks, human request template and tests.
Finish fixture-corrected tests, browser review and scope-v5 provenance checks; preserve
PDF defaults, current permissions, unknown quantities and separate human confirmation.
Use a disposable PostgreSQL test DB on 15433, worktree src on PYTHONPATH, unique temp
storage and sequential suites. Run workbook/client/PDF/capability and retrieval/deadline
tests plus Ruff, Mypy and Bandit. Proceed autonomously through classification, commit,
push, PR and merge only after required CI/review; verify merge. Keep live activation
and refreshed ChatGPT acceptance separate. Do not expand grants, use customer data,
claim XLSX binary packaging, or rebuild the completed PDF/OAuth trial. Preserve all
four ultimate capabilities and production gates; avoid speculative extensions.


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
