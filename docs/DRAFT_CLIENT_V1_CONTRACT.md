# Draft client v1: authenticated MCP and human confirmation

## Status and purpose

2026-09-09. Shared main `d477ff724f3eb6f0229c376728ddba9bea1e75e9` includes
the authenticated Draft client and read-only pricing evidence history through PR #237.
The PDF-file amendment below is implemented and locally validated in this commit;
verify its shared publication status from Git before relying on it. This is a
ChatGPT-compatible surface over the standalone core, not production OAuth deployment
or proof of a connected ChatGPT account. ADRs 0001/0002 remain accepted.

OpenAI's current [MCP server guide](https://developers.openai.com/plugins/build/mcp-server)
and [authentication guide](https://developers.openai.com/plugins/build/auth) describe
MCP-backed integrations and an OAuth resource server with a separate authorization
server. This implementation uses that boundary. It performs no OpenAI API inference
and needs no model API key for its local client proof.

## Callable behavior

| Tool | Result | Mutation boundary |
| --- | --- | --- |
| `list_draft_projects` | Up to 50 owned Draft IDs/revisions and a continuation ID | Read only; no administrator cross-owner access |
| `read_draft_scope` | Explicit saved Scope revision with validation/provenance | Read only; no refresh of downstream work |
| `upload_draft_pdf` | Retained pending PDF source plus content hash and review link | Explicit evidence intake only; no scan, interpretation or Scope change |
| `list_draft_pdf_sources` | Up to 20 owned retained PDF-source states and review links | Read only |
| `scan_draft_pdf` | Current malware-scan and bounded parser result | Evidence-processing state only; no physical claim or Scope change |
| `read_draft_pdf_page` | One parsed page, locator, page hash and file manifest | Read only; extracted text remains unapproved evidence |
| `propose_draft_project` | Durable request ID, status, expiry and review URL | No Project/Draft until human confirmation |
| `propose_draft_edit` | Validated proposed full Scope content and expected revision | No Scope change until human confirmation; preserve entity IDs |
| `propose_project_package` | Explicit saved selection, preview hash and package revision bound to request | No package until human confirmation |
| `read_client_request` | Pending/rejected/confirmed request and saved result identities | Same local user, external subject and client |
| `project_package_download` | Hash/size and authenticated backend/browser download links | Exact saved ZIP; current included-content rights and quarantine |

MCP tools never confirm requests. Open `/client-requests/{id}`, sign in as the mapped
human, inspect readable proposed/current Scope content or selected package revisions,
then confirm or reject with CSRF protection. Login returns only to an exact local
review ID. Confirmation is a Draft authoring act, not technical approval or release.
Existing Scope services attribute the saved human-confirmed revision to that user;
client proposal/decision audit records retain the client and resulting revision.

`draft_client_requests` retains command, bounded canonical JSON/hash, local owner,
verified identity lease (no raw token), expiry, decision and result. One transaction
claims the pending decision and invokes the shared command. A failed command rolls
back the decision; replay or simultaneous confirmation cannot execute twice. The
PostgreSQL two-confirmation test produced one project. New proposals are not given
a distributed idempotency guarantee: a retried proposal can create another pending
request, and the human must choose which request to confirm.

## OAuth resource boundary

Install the optional extra: `python -m pip install -e ".[chatgpt]"`.
Set `CLASSIFIRE_DRAFT_CLIENT_CONFIG` to an operator-owned JSON file. No routes or MCP
imports activate in the standard app unless this path is configured. CI installs
`.[dev,postgres,chatgpt]`. MCP 2.1.1 and PyJWT 2.13.0 are the locally tested versions;
both packages declare MIT licenses. Version ranges remain below their next majors.

The file contains `base_url` (exact HTTPS origin), `issuer` (exact issuer string),
`public_keys` (kid -> public RS256 JWK), `subjects` (issuer subject -> existing local
User UUID), `clients` (client ID -> allowed scopes), and optional `revoked_token_ids`.
Supported scopes are `classifire:draft:read`, `classifire:draft:propose`, and
`classifire:draft:export`, plus `classifire:draft:technical` and
`classifire:draft:estimate`. Proposal/export tools also require read. No mapping is
inferred from an email address or client payload. User permissions remain additional
requirements; token scopes never grant a role or canonical authority.

Accepted tokens are RS256 access JWTs (`typ: at+jwt`) with the configured kid,
issuer, exact `/mcp` resource audience, subject, client ID, token ID, scope, integer
iat/nbf/exp and at most 900 seconds of lifetime. Private keys, remote key headers,
unrecognized algorithms/claims used for authority, unknown accounts/clients,
wrong audiences and expired tokens fail closed. The PDF upload tool is the sole current
client-selected URL fetch: it requires HTTPS, an exact operator allowlist, public DNS
addresses pinned through TLS, bounded redirects/time/bytes, identity encoding, accepted
PDF media types and PDF magic. Signed download URLs are never stored or returned.
The application rereads policy for revocation and account/client/scope changes.
Issuer/resource changes require restart. Keys are operator-pinned; automatic JWKS
refresh and issuer introspection are not implemented. Local token-ID revocation is
immediate; issuer-only revocation can otherwise lag until token expiry.

Serve `/.well-known/oauth-protected-resource/mcp` with exact issuer/resource and all
five supported scopes. The SDK supplies the bearer challenge and protocol handling.
The selected external authorization server must provide discovery, authorized
callback/client registration, authorization-code + PKCE S256, consent, correct
resource/audience and compatible access-token issuance. It owns login/token refresh.
Those provider settings and a real linking flow have not been demonstrated here.
Never weaken verification merely to accept an incompatible provider token.

Client proposals have a 1 MiB request/payload bound and a 100-active-pending-request
limit per user. The latter is an application admission limit, not a production
concurrent quota/retention policy. Scope inputs reuse existing strict validation.
MCP requests check the configured host/origin. Tokens stay in Authorization headers;
client endpoints are not a browser-cookie API. Raw database exceptions are suppressed
from tool results. Production TLS, proxy/rate limiting, key rotation, revocation,
tenancy/retention and deployment monitoring require operational validation.

## Saved files and authority

`GET /api/draft-client/{draft_id}/packages/{package_id}` requires a currently valid
bearer token and export scope; it returns exact saved ZIP bytes with no-store/nosniff.
The normal browser download instead requires the CLASSIFIRE session. Neither link
contains a bearer token or a public signed URL. The host/user must use the relevant
authenticated download method; in-chat file attachment behavior is not yet proven.
Selected PDF intake is now available through the MCP file parameter described below.
Package import, Excel defect-report upload and pricing-workbook upload remain standalone-
only operations.

All included Match/Estimate/report rights and imported ancestor scan/quarantine
checks remain in shared package services. Download does not generate reports,
recalculate totals, run a provider, promote an imported claim or write a lock.
Migration 0036 adds only the request table; it refuses downgrade over retained
review history. Selected ProjectPackage v1/v2 contracts and original bytes remain.

## Local synthetic demonstration

Use a new marked demo directory; never point this command at customer storage:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py --port 8812 --data-dir C:\CLASSIFIRE\.tmp\draft-client-demo-20260906 --client-demo
```

Login: `scope-demo@example.test` / `synthetic-scope-demo-only`. The launcher generates
an ephemeral signing key in memory and writes a synthetic public policy and 15-minute
token inside the marked directory. It enables loopback HTTP only in test mode.
It is not an OAuth authorization server, and the token is not a real customer secret.
Do not paste tokens into chats, logs or commits. Restart refreshes the test token;
old pending requests still expire at their original accepted authorization deadline.

The local official SDK + Chrome proof creates a request, confirms it, saves a Scope
edit with unknown quantity, confirms a selected ZIP and compares client/browser
bytes. A process restart preserved the same artifact and verified sign-in return
and rejection. Local receipts are listed in SESSION_HANDOFF.md. Full ChatGPT account
linking and production acceptance remain open. The independent-capability amendment
below has separate local proof.


## ChatGPT PDF evidence-file amendment

Following OpenAI's current [file-parameter reference](https://developers.openai.com/plugins/reference),
`upload_draft_pdf(draft_id, file)` declares the top-level `file` input in
`_meta["openai/fileParams"]`. The strict object accepts the current ChatGPT runtime
fields `download_url`, `file_id`, optional `mime_type` and optional `file_name`.
Only `download_url` and `file_id` are required. File bytes do not pass through the
1 MiB MCP JSON request body.

The operator must set `CLASSIFIRE_DRAFT_CLIENT_FILE_DOWNLOAD_HOSTS` to a comma-separated
or JSON list of exact lowercase DNS hosts observed for the configured integration.
The default is empty and fails closed with `CLIENT_FILE_POLICY_INVALID`. Wildcards,
IP literals, non-HTTPS URLs, user information, non-443 ports, fragments, unsafe paths,
malformed escapes, non-public DNS answers, unexpected compression, oversized bodies,
wrong media types and non-PDF bytes are refused. DNS answers are checked and the TLS
socket is pinned to the checked public address to prevent DNS rebinding. Every redirect
is revalidated. Errors contain only stable codes.

A successful upload calls the same `draft_pdf_intake.retain_pdf` service as the browser
UI and stores only immutable bytes, source hash/size and the safe original filename.
It starts pending and untrusted. `scan_draft_pdf` is a separate explicit action through
the shared ClamAV/quarantine and disposable parser boundary. `read_draft_pdf_page` returns
one bounded page with locator/hash after a current clean scan. None of these actions
creates an observation, defect, service, opening or saved Scope revision. The client must
use `propose_draft_edit`, followed by same-user browser review, to save interpreted Scope
content. AI interpretation remains optional and unapproved until that review.

Upload and scan require read/propose client scopes plus current local project-write and
strict owner checks. Listing/page reads require read scope and project-read. The signed
download URL is used once in memory and is not written to the request table, audit log,
source row, retained metadata or tool response. Synthetic tests cover MCP discovery,
exact upload/scan/page flow, unchanged Scope revision, zero client proposals, permissions,
invalid metadata, empty configuration, URL validation, DNS rebinding, redirects, MIME,
content encoding, length, PDF magic and secret-redacted failures. A real ChatGPT account,
production OAuth/HTTPS, the provider host allowlist and real file transfer remain unproven.

## PDF-to-Scope review operation

`propose_capability` accepts `action: review_pdf_scope`, `draft_id`, `source_id`,
`expected_revision`, `page_number`, `expected_document_hash`, full Scope `content`, and
1..100 explicit `targets` (`target_kind`: defect/opening/service, `target_id`). Read/propose
client grants and current owner/project-write rights are required. No technical/estimate
grant is added for Scope-only review. Page/entity bounds and semantic validation reuse the
existing PDF services; arbitrary provenance or reviewer fields are forbidden.

Preparation binds the exact shared preview and makes only a pending request. The review
screen presents retained page raster/text, proposed graph and selected item labels. The
same-user CSRF-protected confirmation rechecks the frozen inputs, then invokes the existing
page-save service with the verified review hash. Server-generated references bind source,
page, target content, reviewer and time. Changed source/scan/Scope/targets, lost permissions
or replay are refused. Generic edits remain available and do not manufacture page references.
No subsequent Match, Estimate or report is run. Existing command hashes and artifact readers
remain compatible; no migration is required.

## Independent-capability amendment (migration 0037)

`propose_capability(operation)` accepts a strict action-specific object. All actions
include `draft_id`; missing required or extra fields are rejected. The operation stops after
its one requested use case and requires a separate human session confirmation.

| Action | Explicit inputs | Shared operation |
| --- | --- | --- |
| `create_match` | Scope revision, active release ID, opening/service target IDs | Saved unapproved candidate retrieval |
| `review_match` | Match ID, expected revision, every candidate decision/notes | Append keep/reject/unreviewed decisions; no technical approval |
| `review_match_constraints` | Match ID, expected revision, candidate ID, exact thickness/gap inputs and evidence note | Append v2 partial measured-limit review |
| `review_match_service_size` | Same identities; thickness/gap plus measured size range and two size meanings | Append v3 partial review; preserve size history |
| `create_estimate` | Scope revision, optional paired Match ID/revision, AUD | Create an empty Draft estimate independently of matching |
| `add_estimate_line` | Estimate ID, expected revision, shared AddLine contract | Validate quantity/unit/recovery and append a manual line |
| `override_estimate_line` | Estimate ID/revision, line ID, shared Override contract | Preserve original value and append reasoned history |
| `set_estimate_line_status` | Estimate ID/revision, line ID, active/omitted, reason | Omit/restore without deleting history |
| `apply_workbook_rate` | Estimate ID/revision, line/source IDs, explicit worksheet mapping/row, expected document/row hashes, recovery note | Shared source-bound rate application; retain original rate and override history |
| `scope_report` | Scope revision, optional paired Match ID/revision | Scope-only or scope-and-system saved PDF/XLSX |
| `estimate_report` | Estimate ID/revision, estimate-only/complete profile | Render that saved estimate snapshot; missing technical data stays unavailable |

Preparation validates shape, permissions and readable selected inputs, binds their
hash and saves a proposal. It does not execute the domain writer/renderer. Confirmation
performs full existing business validation; invalid domain data leaves the request
pending without a partial artifact. Selected historical revisions are deliberate
inputs; later upstream changes mark outputs stale rather than rewriting them. Edits
require the expected current revision. No client method confirms a proposal.

Additional tools: `list_technical_releases`, `list_capability_artifacts` (one of
system-match/estimate/scope-report/estimate-report; existing 20-row service limits),
`read_capability_artifact` (saved envelope plus staleness), and `report_download`.
Estimate reports require their parent estimate ID. Report IDs identify immutable
snapshots, so report reads reject a separate revision number. Downloads return
hash/size and authenticated/browser links to the exact saved bytes, never a new render.

Bearer endpoints are `/api/draft-client/{draft_id}/reports/{report_id}/{format_name}`
and `/api/draft-client/{draft_id}/estimates/{estimate_id}/reports/{report_id}/{format_name}`;
formats are PDF/XLSX. Browser counterparts use the existing `/download?format=...`
route. Export scope and current included-content domain permissions are mandatory.

Technical scope is needed for Match content and nested technical inputs; estimate
scope is needed for commercial content. Sensitive data remains guarded in reports,
lists and package downloads. A v2 archive retains entire original ZIPs, so both
sensitive scopes are required conservatively even for a Scope-only local selection.
Existing grants remain unchanged until the operator explicitly adds scopes. Tools
with conditional content advertise their common minimum scope; callers must obtain
the required extra advertised resource scopes for the chosen operation. Real
ChatGPT consent/reauthorization behavior remains unproven.

Migration 0037 extends the retained command check without changing artifact schemas;
it preserves existing requests and refuses downgrade over new retained history.
Workbook upload/scan remains in the standalone UI; the pricing amendment below
exposes preview and confirmed selection. Measured review and workbook selection use
the existing capability request discriminator; neither requires a new migration.
No inference provider, canonical lock or release is exposed.

Current demo: port 8813, marked `client-capabilities-demo-20260906` directory, with
`--client-demo --seed-technical-library`. Official SDK/Chrome proof covers independent
estimating before matching, preserved overrides, separate candidate review, four
profiles and eight byte-identical browser/client downloads. PROJECT_STATE.md and
SESSION_HANDOFF.md record validation, restart and publication checkpoints.


## Measured-review amendment

Both actions use `save_constraint_review` and its shared `validate_inputs`. Base
`inputs` requires `substrate_thickness_mm`, `annular_gap_min_mm`,
`annular_gap_max_mm` and `measurement_note`. The size action additionally requires
`service_size_min_mm`, `service_size_max_mm`, `service_size_basis` and
`source_size_basis`. Missing/extra keys and number-to-string coercion are refused.
Measurements are decimal strings in millimetres (up to four decimal places) or
`null` for unknown; thickness/size must be positive, gaps nonnegative, and supplied
minimums cannot exceed maximums. The evidence note is nonblank, at most 2,000 characters.
Size meanings are `unknown`, `outside_diameter`, `nominal_diameter`,
`rectangular_dimensions` or `bundle_envelope`; the shared rules determine which
comparisons remain unresolved. Source interpretation is an unapproved human claim.

Preparation binds the selected saved Match and expected revision and requires
technical scope/current local rights. The separate human screen compares proposed
values with saved measurements/findings; its saved panel cannot submit another
measurement form. Confirmation alone invokes the shared writer and rechecks active
release, retained source bytes/quarantine, target/candidate and revision. A stale,
foreign-source or otherwise invalid command leaves no partial revision or decision.
A v3 review cannot be downgraded to v2 and silently lose service-size history.

Results remain `partial_unapproved`, with unassessed conditions and exact prior
revisions. Historical reports keep their selected review and PDF/XLSX bytes after
later changes; staleness is separate from saved output. Keeping a candidate or
recording a value within a numeric limit never approves technical compatibility.

Synthetic demo: `--port 8814 --data-dir C:\CLASSIFIRE\.tmp\client-measured-demo-20260906
--client-demo --seed-service-size-library`. The existing fixture seeds labelled test
source/approval/clean metadata; no real scanner or technical approval is claimed.
See PROJECT_STATE.md and SESSION_HANDOFF.md for the actual validation checkpoint.


## Workbook-pricing amendment

This implementation extends the existing retained-workbook service. It does not add
an upload/scan tool, formula engine, pricing inference, approval or library-release
operation. Local validation passed; use PROJECT_STATE.md and SESSION_HANDOFF.md for proof
and the publication checkpoint.

| Read tool | Inputs and bounded result |
| --- | --- |
| `list_pricing_sources` | `draft_id`; up to 20 owned workbook metadata entries (`id`, filename/hash/size, scan/status/readiness, document hash). Metadata readiness is not proof of current usable bytes. |
| `preview_pricing_rows` | `draft_id`, `source_id`; `sheet_index=1`, `header_row=1`, `mapping=null`, `after_row=0`. Returns `mode`, verified `source`, up to five `rows`, `next_after_row` and `limit=5`. |

Both tools require read/estimate client scopes, current local estimate/library read
permission and client ownership. Preview invokes the existing retained-source reader:
PostgreSQL quarantine support, a current clean scan, intact bytes and valid normalized
document are required. It performs no scan, provider call or Draft mutation.

Without a mapping, preview supplies worksheet names/dimensions and five physical rows
at a time. Cells retain address/type and show at most 200 characters with explicit
`truncated` and `original_length` fields. With a mapping, rows are the complete shared
pricing preview records: exact cells/values, worksheet/row/column mapping, row hash
and unresolved problems. Mapped provenance is not truncated. `after_row` is an actual
worksheet row number; `next_after_row=null` ends paging. Mapping/cursor fields reject
string/boolean coercion and out-of-range positions.

The verified source binding is `source_id`, `source_sha256`, `document_sha256`,
`scan_sha256`, `filename` and `size_bytes`. It identifies the bytes, normalized document
and current scan selected for this proposal, without embedding credentials or paths.

`apply_workbook_rate` requires `draft_id`, `estimate_id`, `expected_revision`,
`line_id`, `source_id`, `sheet_index`, `header_row`, `mapping`, `row_number`,
`expected_document_hash`, `expected_row_hash` and `recovery_note` (1-4,000 characters;
confirmation requires nonblank text). Hashes are 64 lowercase hexadecimal characters.
The mapping requires positive integer columns for `reference`, `description`, `unit`,
`rate`, `currency` and `tax_basis`. Optional `rate_date`, `labour`, `materials`,
`inclusions` and `exclusions` accept a positive integer or null and default to null.
The shared validator checks actual bounds and duplicate columns; no columns are guessed.

Preparation requires proposing/estimating scopes plus current write/library rights,
reads the saved Estimate and target line, calls `draft_pricing_intake.preview`, checks
the submitted document/row hashes and binds source/scan/row/line inputs to the durable
request. The human screen shows those exact cells, problems, recovery note and saved
line/totals. Preparation does not apply a rate or claim complete domain validation.

Only separate same-user browser confirmation invokes `draft_pricing_intake.apply_rate`.
It rechecks rights, current input binding and revision; shared rules refuse unresolved
rates, formulas, unsupported currency/tax/units and a unit mismatch with the target
line. Failure leaves the request pending without a partial Estimate revision. A new
scan or changed source/document/line requires a fresh proposal. Completed browser
request history also checks current `library:read`; client receipt metadata remains
separate from protected pricing content.

The saved Estimate v2 selection preserves the source and row, original rate, reasoned
override event and `unreviewed` status. Later manual overrides keep that history.
Existing estimate-only/complete reports and packages retain their selected snapshots,
source provenance and current permission checks. No new table, migration, dependency,
OAuth scope or artifact schema is added. Pre-existing command input hashes retain
their original five-key shape so already pending manual requests survive this upgrade.
