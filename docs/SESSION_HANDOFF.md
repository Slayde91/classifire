# CLASSIFIRE Session Handoff

## Branch and project context

Verified 2026-09-09 from isolated worktrees, local tests and GitHub.

- Shared remote `main` is
  `d477ff724f3eb6f0229c376728ddba9bea1e75e9`, merge commit for PR #237.
- PR #237 is merged. Exact head
  `4ed44ec7543af95541d0d584f8aaa078ad300fde` passed run 34345679363:
  full tests, Ruff, Mypy, Bandit and the one-head Alembic check.
- Post-merge main run 34348938960 passed full tests and every repository gate on
  the exact merge commit. Prior run 34342328239 timed out at the workflow's
  30-minute limit while tests were still running; it reported no failed assertion.
- Active isolated worktree:
  `C:/CLASSIFIRE/.tmp/chatgpt-pdf-intake-20260909`;
  branch `feat/chatgpt-pdf-intake-20260909`, based on current `origin/main`.
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

The active branch adds a ChatGPT-compatible PDF intake path over the same services used
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

Current local evidence on the active branch:

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

**First task:** finish, publish and merge the active ChatGPT PDF-intake slice.

**Why this is next:** the implementation and focused validation are complete locally.
Merging it gives ChatGPT-compatible clients the missing report-file entry point while
preserving the existing human Scope gate. Leaving it local would keep the visible
prototype blocked.

**Prerequisites and dependencies:**

- Read `AGENTS.md`, `docs/GOAL.md`, current Git status/diff, `origin/main`,
  PR #237/run 34345679363, main run 34348938960 and the five relevant documents.
- Preserve the dirty recovery root and every unrelated local change.
- Verify the official file parameter remains a top-level `file` field with
  `download_url` and `file_id` required.
- Keep the host allowlist exact and operator-owned. Do not add wildcards, accept private
  DNS or persist signed URLs.
- Keep upload/scan separate from Scope interpretation and human-confirmed save.
- Do not add automatic Match, Estimate, report, approval, release, AI or OpenClaw work.

**Relevant files:**

- `src/classifire/draft_client_evidence_tools.py`;
- `src/classifire/services/remote_file_retrieval.py`;
- `src/classifire/services/draft_pdf_intake.py`;
- `src/classifire/draft_client.py`;
- `src/classifire/config.py`;
- `tests/test_draft_client_pdf_intake.py`;
- `tests/test_remote_file_retrieval.py`;
- `tests/test_draft_client.py`;
- `.env.example` and the five updated documentation files.

**Validation commands:**

```powershell
$env:PYTHONPATH=(Join-Path $PWD 'src')
$env:CLASSIFIRE_POSTGRES_TEST_URL='postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN='classifire-containment-test-drop-all'
C:/CLASSIFIRE/.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp C:/CLASSIFIRE/.tmp/pytest-chatgpt-pdf-final tests/test_draft_client.py tests/test_draft_client_pdf_intake.py tests/test_remote_file_retrieval.py tests/test_draft_pdf_intake.py
C:/CLASSIFIRE/.venv/Scripts/python.exe -m ruff check .
C:/CLASSIFIRE/.venv/Scripts/python.exe -m mypy src --disable-error-code=import-untyped
C:/CLASSIFIRE/.venv/Scripts/python.exe -m bandit -r src
git diff --check
```

**Blockers:** required CI must pass and must not be bypassed. A real ChatGPT/OAuth/HTTPS
trial requires an operator-controlled deployment and the observed exact provider file
host, but that does not block merging the fail-closed local capability.

**Definition of done:** exact MCP discovery exposes the file parameter; authorized owner
upload/scan/list/page operations reuse shared services; unsafe URLs/DNS/content and
unauthorized access fail closed; signed URLs are absent from persistence/results; no
Scope/downstream artifact runs automatically; targeted and repository checks pass; the
complete diff contains only intended files; all durable documents align; explicit paths
are committed and pushed; a direct-main PR passes exact-head CI and merges; resulting
main and its post-merge workflow are verified.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Inspect `AGENTS.md`,
> `docs/GOAL.md`, Git/worktrees, the complete active diff, `origin/main`, PR #237 and
> runs 34345679363/34348938960 before editing. Preserve the conflicted
> `C:/CLASSIFIRE` recovery root and unrelated changes. The single highest-value task is
> to finish and merge `feat/chatgpt-pdf-intake-20260909` in
> `C:/CLASSIFIRE/.tmp/chatgpt-pdf-intake-20260909`: ChatGPT file parameter -> exact-host
> public-DNS/TLS-pinned retrieval -> shared PDF retain/scan/page read -> separate
> human-confirmed Scope edit. Verify signed URLs are never retained, unsafe or
> unauthorized inputs fail closed, and no downstream capability runs. Run the listed
> PostgreSQL/client/PDF tests, Ruff, Mypy, Bandit and `git diff --check`; inspect and
> classify the full diff; then autonomously commit explicit paths, push, open a
> direct-main PR, wait for exact-head required CI and merge where safe. Completion
> requires the verified MCP schema, passing lifecycle/security tests, aligned
> documentation and a verified main merge. Avoid speculative provider hosts, AI,
> pricing, approval, release or OpenClaw changes.