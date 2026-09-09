# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09 from isolated worktrees, local tests and GitHub.

- Shared baseline before this feature is
  `d477ff724f3eb6f0229c376728ddba9bea1e75e9`, merge commit for PR #237.
- PR #237 is merged. Exact head
  `4ed44ec7543af95541d0d584f8aaa078ad300fde` passed run 34345679363:
  full tests, Ruff, Mypy, Bandit and the one-head Alembic check.
- Post-merge main run 34348938960 passed full tests and every repository gate on
  the exact merge commit. Prior run 34342328239 timed out at the workflow's
  30-minute limit while tests were still running; it reported no failed assertion.
- Active isolated worktree:
  `C:/CLASSIFIRE/.tmp/chatgpt-pdf-intake-20260909`;
  branch `feat/chatgpt-pdf-intake-20260909`, opened as PR #238. Verify its current`n  exact head, CI and merge status before relying on shared publication.
- The dirty conflicted `C:/CLASSIFIRE` root is recovery evidence. Do not edit,
  reset, clean, resolve, broadly stage or publish from it.
- ADRs 0001/0002 remain accepted: one modular deterministic application,
  independent capabilities, portable artifacts, bounded optional AI and
  transitional OpenClaw.

## Current implementation

Shared main now exposes saved Scope, Match, Estimate, reporting and selected-package
operations through an opt-in authenticated MCP adapter. PR #237 completes bounded
read-only client access from T9 coverage and T6 recipe links to exact reviewed Dataset A
row observations.

The current feature adds a ChatGPT-compatible PDF intake path over the same services used
by the standalone UI:

- `upload_draft_pdf(draft_id, file)` declares
  `_meta["openai/fileParams"] = ["file"]` and accepts the documented
  `download_url`, `file_id`, optional `mime_type` and `file_name`;
- `list_draft_pdf_sources(draft_id)` returns at most 20 owned retained sources;
- `scan_draft_pdf(draft_id, source_id)` invokes the shared ClamAV/quarantine and
  disposable parser boundary;
- `read_draft_pdf_page(draft_id, source_id, page_number)` returns one bounded page,
  locator, page hash and file manifest.

Remote retrieval requires an exact lowercase DNS-host allowlist in
`CLASSIFIRE_DRAFT_CLIENT_FILE_DOWNLOAD_HOSTS`. It allows HTTPS/443 only, checks every
DNS answer is public, pins TLS to a checked address, revalidates redirects, bounds time
and bytes, requests identity encoding and validates response length, MIME and PDF magic.
A signed URL is used in memory and is never retained or returned.

Upload and scan require read/propose client scopes, current local project-write
permission and strict ownership. They mutate unapproved evidence-processing state only.
They create no observation, defect, service, opening, saved Scope or downstream
artifact. Saving interpreted Scope content still uses `propose_draft_edit` and
same-user browser confirmation.

## Validation evidence

Current feature evidence:

- hardened remote retrieval and configuration: **19 tests passed**;
- combined client, PDF intake, remote retrieval and PostgreSQL regression:
  **56 tests passed in 133.59 seconds**;
- the MCP discovery test proves the exact file metadata and nested input schema;
- the end-to-end synthetic path proves pending upload -> clean scan/parser -> page text,
  locator and hashes;
- the Scope stayed at revision 1 and no `DraftClientRequest` was created by evidence
  upload/scan/read;
- missing write scope, foreign ownership, invalid MIME and empty host configuration
  fail closed before retrieval;
- focused Ruff passed;
- focused Mypy passed on the four changed/new production modules;
- focused Bandit passed on the new client and retrieval boundaries;
- `git diff --check` passed.

The failed first PostgreSQL invocation was a test-runner setup error: its relative
`--basetemp` parent did not exist. Re-running with the repository's absolute isolated
temporary path reached application code and passed. All evidence uses synthetic PDFs
and a mocked remote transport/ClamAV verdict.

## Relevant local changes and open issues

Intended active-branch paths:

- `.env.example`;
- `src/classifire/config.py`;
- `src/classifire/draft_client.py`;
- `src/classifire/draft_client_evidence_tools.py`;
- `src/classifire/services/remote_file_retrieval.py`;
- `tests/test_draft_client.py`;
- `tests/test_draft_client_pdf_intake.py`;
- `tests/test_remote_file_retrieval.py`;
- `docs/DRAFT_CLIENT_V1_CONTRACT.md`;
- `docs/PROJECT_STATE.md`;
- `docs/CLASSIFIRE_ARCHITECTURE.md`;
- `docs/CLASSIFIRE_ROADMAP.md`;
- `docs/SESSION_HANDOFF.md`.

No unrelated local change was observed in this isolated worktree. Reinspect status and
the complete diff before staging explicit paths.

Open issues:

- The exact host used by a real ChatGPT file download has not been observed or approved.
  The default host list is empty and deliberately makes upload fail closed.
- Real OAuth, HTTPS, ChatGPT account linking and actual provider file transfer are
  unproven. Do not hard-code an undocumented provider hostname.
- PDF intake is implemented; ChatGPT file parameters for Excel/DOCX/images remain
  upcoming.
- Parsed text and page locators are evidence, not a physical-model conclusion. A real
  report still needs model interpretation plus explicit human graph review/save.
- ProjectPackage source bodies and newer pricing-review records remain external or
  withheld until redistribution/confidentiality rules are approved.
- Representative report accuracy, production tenancy/retention/monitoring, evaluation,
  commercial activation, OpenClaw retirement and Human Release remain incomplete.
- Full CI duration remains close to the 30-minute workflow timeout.

## Project health

This change follows the accepted hybrid architecture. The standalone UI and
ChatGPT-compatible adapter call the same deterministic PDF intake, storage, scanner,
parser and Scope services. It adds transport and permission checks, not another business
pipeline, database, agent or AI provider.

The feature is a working local integration prototype, not a connected ChatGPT product.
Its main value is removing the backend reason ChatGPT could not accept a selected PDF.
The next proof must show the visible real-account journey without weakening the host,
identity, review or evidence boundaries.

## Start Here / Next Session

**First task:** verify PR #238 publication, then prove the first real ChatGPT PDF-to-Scope
journey through an operator-controlled HTTPS/OAuth deployment.

**Why this is next:** the backend file contract, secure retrieval, retained upload/scan/page
flow and human Scope gate are implemented and synthetically tested. A real connected-client
trial is the shortest way to expose any wrong provider-host, OAuth, attachment, review-link
or user-flow assumption before the same pattern is extended to Excel.

**Prerequisites and dependencies:**

- Inspect `AGENTS.md`, `docs/GOAL.md`, Git/worktrees, `origin/main`, PR #238 and its exact
  required CI before editing. If the feature is not merged, finish its existing safe
  publication path first; do not duplicate it.
- Preserve the dirty `C:/CLASSIFIRE` recovery root and every unrelated local change.
- Obtain an operator-controlled HTTPS CLASSIFIRE deployment, compatible OAuth issuer/client
  configuration and a synthetic non-customer PDF approved for the trial.
- Observe and explicitly approve the real ChatGPT file-download DNS host. Keep the default
  fail-closed until then; do not add a wildcard or guess a provider hostname.
- Keep upload/scan separate from interpretation, and keep the same-user browser confirmation
  before a Scope revision is saved.

**Relevant files:**

- `src/classifire/draft_client_evidence_tools.py`;
- `src/classifire/services/remote_file_retrieval.py`;
- `src/classifire/services/draft_pdf_intake.py`;
- `src/classifire/draft_client.py` and `src/classifire/draft_client_auth.py`;
- `tests/test_draft_client_pdf_intake.py` and `tests/test_remote_file_retrieval.py`;
- `docs/DRAFT_CLIENT_V1_CONTRACT.md` and the four durable state documents.

**Validation:** rerun the 56-test PostgreSQL/client/PDF selection, Ruff, Mypy, Bandit and
`git diff --check`. In the real client, verify tool discovery, selected-file upload as
pending, explicit clean scan/parser result, one page's text/locator/hashes, separate Scope
proposal, readable browser review, same-user save, and reopen after process restart. Inspect
persistence/logs/results for absence of the signed URL and verify no Match, Estimate, report,
approval, release, AI or OpenClaw action ran.

**Blockers:** the real journey cannot run without operator-controlled HTTPS/OAuth configuration
and the observed exact provider file host. Do not weaken security to work around either.
This does not block local inspection or safe fixes to PR #238.

**Definition of done:** PR #238 is verified merged with exact-head required CI; one real
synthetic PDF completes the selected-file -> retained pending -> clean parsed page -> proposed
Scope -> human-confirmed saved revision journey; evidence records the exact deployment/client
configuration without secrets; unsafe/unauthorized cases remain closed; restart preserves
the result; unrelated changes are preserved; any required fixes and aligned documentation
pass validation and complete the normal commit/push/PR/merge workflow.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect `AGENTS.md`,
> `docs/GOAL.md`, Git/worktrees, `origin/main`, PR #238 and its exact required CI; preserve
> the conflicted `C:/CLASSIFIRE` recovery root and unrelated changes. First finish PR #238's
> safe publication if it is not already merged. The single highest-value product task is
> then to prove one real ChatGPT PDF-to-Scope journey through operator-controlled HTTPS/OAuth:
> selected synthetic PDF -> exact-host public-DNS/TLS-pinned retrieval -> retained pending
> source -> explicit scan/parser -> bounded page read -> separate Scope proposal -> same-user
> browser review/save -> restart/reopen. Obtain the actual provider download host and keep
> the allowlist fail-closed; never guess or use a wildcard. Verify signed URLs are absent
> from persistence/logs/results and that no Match, Estimate, report, approval, release, AI
> or OpenClaw action runs. Run the documented 56-test PostgreSQL/client/PDF selection, Ruff,
> Mypy, Bandit and `git diff --check`. Record measured evidence, update aligned documentation,
> preserve unrelated changes, and autonomously inspect, implement only proven fixes, validate,
> classify, commit, push, open/update the direct-main PR, wait for exact-head CI and merge
> where safe. Do not begin Excel or speculative provider work until this journey is proven.