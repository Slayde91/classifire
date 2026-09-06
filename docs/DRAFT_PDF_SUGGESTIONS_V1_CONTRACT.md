# Optional Draft PDF suggestions and Scope v6 contract

Status: implemented on `feat/draft-pdf-suggestions-20260906`, based on
`d2640defd00c23892691da79990a510bee59b2a0`. Actual test, browser/restart, CI and
publication evidence belongs in [PROJECT_STATE.md](./PROJECT_STATE.md). The configured
OpenAI transport exists, is disabled by default, and has no real-provider execution
proof at this checkpoint. Scripted fixtures and mocked HTTP checks are not a live AI
accuracy, cost, privacy or production acceptance result.

ADRs [0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md) and
[0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md) remain unchanged.
The feature extends the shared Draft workflow with an optional, bounded interpretation
step. It does not replace OpenClaw, retire any existing protection, introduce an agent
fleet or authorize canonical physical-model, technical, commercial, lock or release work.

## One page, one optional proposal, explicit human review

The existing [retained PDF workflow](./DRAFT_PDF_EVIDENCE_V1_CONTRACT.md) remains the
source boundary. A human chooses one current clean retained page and explicitly
confirms sending its extracted text and rendered image to the configured suggestion
provider. The returned structured suggestions are retained separately from saved Scope.
A person reviews the original suggestions beside the source, edits the complete graph,
selects every suggested item they keep, removes rejected items, previews and confirms
one new unapproved Draft revision. Rejecting the whole batch changes only its retained
status/audit; it does not save a Scope revision.

Manual page review, the manual editor and the
[Excel mapping workflow](./DRAFT_SCOPE_XLSX_V1_CONTRACT.md) remain available without AI.
Failure, unavailable configuration, empty output or stale suggestions do not start
matching, estimating or canonical processing. No client/MCP suggestion command is added.

| Component | Implemented responsibility |
| --- | --- |
| `draft_pdf_suggestion_contract` | Strict page-only request/output shapes and bounded local proposal keys; no database or canonical IDs |
| `draft_pdf_suggestion_transport` | Optional fixed-endpoint OpenAI request, response policy and safe error codes |
| `draft_pdf_suggestions` | Current source/actor/revision checks, generation retention, no-write review preview and atomic explicit application/rejection |
| `draft_pdf_suggestion_ui` | Session/CSRF/source-consent forms and signed same-session confirmation through shared services |
| Shared Scope/evidence/report/package services | Normalized graph, v6 provenance, conditional revisions, old readers, immutable snapshots and portable historical claims |

Browser routes start at `/scopes/{draft_id}/evidence/{source_id}/suggestions`.
Generation is an explicit POST; a retained suggestion has detail, preview, confirm and
reject routes. Mutating forms require CSRF. Generation requires `consent=yes`; final
save separately requires `confirm=save`. The preview token binds actor, Draft, source,
suggestion, browser session and review hash with a purpose-specific SHA-256 signer
and 15-minute expiry. No selection or provider response grants standing authority.

## Source and identity boundaries

Generation requires an active human with `project:write`, current `project:read`,
Draft owner/administrator access, a matching saved revision/document hash and the
existing PostgreSQL retained-byte/quarantine locks plus current clean scanning.
Retained suggestion rows are accessible only to their creating human within the
permitted Draft; administrator access to a Draft alone does not claim another user's
pending generation. Reading originals rechecks current source access and clean bindings.

The service checks write authority again after rendering and before provider execution,
then checks actor, source and Scope again after the call. Page/source/hash drift,
revocation, quarantine or revision change prevents retention/application. Existing
source guards remain mandatory; SQLite supports the manual path and disposable tests,
not an alternative containment implementation for real uploaded evidence.

The provider receives one page's text and PNG. It does not receive the project graph,
pricebooks, canonical identifiers, admission/lock authority or tools. Its short local
keys can link only returned suggestions of the correct kinds. CLASSIFIRE assigns new
Draft UUIDs, resolves those local links and validates the resulting graph. These IDs
are not Phase 8 canonical Defect/Opening/Service records. Existing items are not silently
merged by label or replaced by a model-selected database ID.

## Proposal semantics and limits

The strict output has four arrays: `defects`, `openings`, `services`, `observations`.
Each item has a unique local key, `basis`, `quote` and `rationale`, plus its permitted
kind-specific fields. Unknown fields, broken or duplicate links, duplicate keys,
invalid types and unsupported authority/measurement fields are refused. All arrays may
be empty; an empty result supplies no reviewable Scope change.

| Boundary | Implemented limit |
| --- | --- |
| Selected source | One page from the existing bounded retained PDF contract; no whole-report or cross-report inference |
| Input to the port | At most 20,000 text characters and 4 MiB PNG; the existing raster fits 1200x1600 pixels |
| Proposed items | At most 25 total; at most 5 defects and 10 each openings, services and observations |
| Local keys/links | 1..32 constrained key characters; each service has at most 10 distinct returned opening keys |
| Text | Labels at most 200; descriptions/observations at most 4,000; substrate/service type at most 500; rationale 1..1,000 |
| Evidence basis | `page_text`, `page_image` or `both`; quote at most 500 characters |
| Normalized output | 64 KiB maximum |
| Retained generation | 128 KiB UTF-8 proposal record; at most 20 retained generations per Draft, including terminal batches |
| Saved Scope | Existing graph/288 KiB artifact and 100-reference limits; preview checks the actual successor, without truncation |

For `page_text`/`both`, a nonblank quote must occur exactly in the selected extracted
text. `page_image` requires an empty quote. A matched quotation only demonstrates text
location; it does not establish that the interpretation is correct. A picture can
support an uncertain visual proposal without becoming a measurement or technical fact.
Image-only readability, hidden/opposite faces, material identity, service continuity,
scale and physical relationships still require human evidence review. This is not a
general OCR pipeline or a calibrated image-recognition claim.

All generated opening dimensions and service quantities are **null**. Generated
openings/services are `Inferred`; observations are `Unresolved`. Opening `blank` starts
false, and the service's `each` unit is a placeholder with quantity withheld. A human
may edit these fields in the ordinary Draft editor; their original suggested values
remain retained separately. One defect, row, visible mark or proposed item never implies
quantity one. No numeric confidence, FRL, technical suitability, selected product,
price or approval is generated by this contract.

## Configured transport and execution limits

Configuration uses `draft_pdf_suggestions_enabled` (default false), an explicit
`draft_pdf_suggestions_model` and secret `draft_pdf_suggestions_api_key`; there is no
default model or key. A server-injected scripted port supports isolated synthetic
validation and is labelled as such in the UI. It is not a public provider-switching tool.

The actual OpenAI adapter sends one HTTPS POST to the fixed Responses endpoint. It
requests structured JSON with the frozen `draft-pdf-suggestions-v1` instructions,
`store=false`, `stream=false`, `tools=[]`, `tool_choice=none` and at most 12,000 output
tokens.
There are no retries, conversation IDs, prior-response links, redirects, environment
proxy adoption or alternate endpoint configuration. TLS verification remains enabled.
Page content is explicitly treated as untrusted evidence, not instructions.

The encoded request is bounded to 6 MiB and the response body to 256 KiB. Non-success,
incomplete/refused/tool output, multiple text results, duplicate JSON keys, nonfinite
values, invalid schema and unsupported content/encoding fail closed with safe codes.
The adapter uses five-second connect/write/pool timeouts, a 60-second read timeout,
and a 90-second elapsed-response budget checked after headers, each unbuffered raw
chunk and completion. It requests identity encoding and does not decompress
responses. These per-I/O limits and elapsed checks are not a hard whole-call
wall-clock deadline or end-to-end cancellation guarantee. Real network latency, interruption behavior, model
compatibility, accepted-result cost and throughput still require authorized measurement.

Only the selected page is submitted when explicitly requested and configured. This
implementation does not verify account/provider retention settings or grant permission
to process customer evidence. No credentials, raw HTTP response, model reasoning body,
full prompt or source body are stored in audit fields or portable suggestion claims.
Provider execution remains subject to existing authorization and deployment gates.

## Retained generation and hashes

Migration `0039_draft_pdf_suggestions` follows 0038. It adds `DraftPdfSuggestion` /
`draft_pdf_suggestions` with Draft/source/creator foreign keys, base revision, exact
proposal JSON/hash, `pending`/`applied`/`rejected` status and optional applied revision.
It indexes Draft and source, bounds the proposal text, and requires an applied revision
to be non-null and exactly base revision + 1; other statuses require null. Downgrade
refuses retained data loss. Prior source tables, Scope/report/package bytes and
migration history are not backfilled or rewritten.

The retained record contains the complete normalized generation with application-issued
Draft item IDs, original proposed values, source bases, quotes and rationales. Its
request binding records source ID/byte hash/size/name, normalized document and scan
hashes, page/locator/text hash, base Scope hash, rendered PNG hash, extracted-text digest,
prompt version, provider and requested model. Requested and returned model identifiers
remain distinct where the provider resolves an alias.

- `input_sha256` hashes that exact canonical request binding. It is not the serialized
  HTTP request body's hash or an assertion that the provider attested to that hash.
- `page_image_sha256` identifies the exact PNG supplied to the port; PDF/source hashes
  identify the underlying retained evidence independently of its rendering.
- For the OpenAI adapter, `response_sha256` hashes the exact accepted response-body
  bytes. A scripted port supplies its synthetic response digest. The raw response is
  not retained; the bounded normalized generation is retained instead.
- `proposal_sha256` hashes the exact locally retained proposal JSON. The service also
  checks internal duplicated bindings, item semantics and current page quote/digest
  consistency; a self-reported checksum alone is insufficient.

Below the per-Draft quota, an identical pending request can be reused without another
provider call. The existing Draft lock serializes this preparation, including the call;
it is a bounded prototype interaction, not a general job scheduler or concurrency claim.
Generation writes only its proposal/audit atomically. It does not advance the Scope.
The record is a local generation receipt, not a signed provider attestation, Phase 8
execution receipt or replacement for the existing OpenClaw execution protections.

## Human application, Scope v6 and historical compatibility

`preview_suggestion` validates the complete edited graph with no writes or autoflush.
Every retained proposed item still present in the graph must be explicitly selected;
removed items are excluded. Manual additions receive no automatic suggestion reference.
The preview binds the generation ID/hash, source/page, actor, base Scope/revision,
complete final payload and selections, and checks the exact successor byte/ref budget.
Confirmation regenerates that preview under current checks, then atomically appends
one Scope revision, marks the batch applied and records audit events. Stale/tampered,
expired/foreign-session, replayed, rejected, revoked or source-changed requests save
nothing. A failed persistence/audit operation cannot leave a partially applied graph.

`CLASSIFIRE-DRAFT-SCOPE-v6` extends the existing `evidence_refs` union. Old v1-v5 shapes,
hashes and readers remain unchanged. New AI-assisted PDF entity references retain
`method=human_page_entity_review` and add one strict `suggestion` claim. Defect, opening
and service targets remain distinct. `observation` is an entity target only for this
v6 suggestion path; legacy observation/page references retain their original form.

The `suggestion` object has exactly: `schema=CLASSIFIRE-DRAFT-PDF-SUGGESTION-CLAIM-v1`,
`suggestion_id`, `provider` (`openai`/`scripted`), `model`, `prompt_version`,
`input_sha256`, `response_sha256`, `page_image_sha256`, UTC `generated_at`,
`proposed_item`, `basis`, `quote`, `rationale`. Its original normalized item has the same
Draft target ID and conservative original states/null measurements. The outer
`target_sha256` covers the complete human-reviewed final item, including its links/state.

Manual edits retain the old target hash and original suggestion. Deleted entity targets,
including AI-assisted observations, retain historical claims and become stale. Ordinary
same-target/source/page re-review refreshes the human claim without silently dropping
its original AI metadata. Earlier revisions remain exact. The original legacy PDF
observation-deletion pruning behavior is unchanged. Later PDF, Excel, manual and import
saves preserve v6 once present, including mixed old references and empty-ref successors.

Imports mark every reference `imported_unverified`; matching UUIDs, provider names or
hashes grant no local execution, current source access or human approval. Nested AI
metadata is a portable historical assertion. Current source freshness remains separate
from saved target/review status and from the original suggested content.

## Reports, packages and remaining acceptance

| Profile | Scope v6 | Scope v5 | Scope v4 | Earlier Scope inputs |
| --- | --- | --- | --- | --- |
| Scope-only | 7 | 5 | 3 | 1 |
| Scope-and-system | 8 | 6 | 4 | 2 |
| Estimate-only | 8 | 6 | 4 | 1 manual / 2 pricing sources |
| Complete | 9 | 7 | 5 | 3 |

New reports display original proposals, model/prompt/hash metadata, human-reviewed
facts and saved reference status as literal escaped content. They do not re-run AI or
upstream capabilities. Existing retained JSON/PDF/XLSX downloads remain exact. Selected
ProjectPackage inventory includes each entire reference at
`artifacts/scope.json#/evidence_refs/<index>`; old import archives/history remain retained.
Source PDFs, PNG bodies, raw provider responses and unselected/rejected generation
records are not added to portable packages. The accepted reference's original-item claim
is portable; the full local generation/history remains in its guarded database record.

Focused tests include `test_draft_pdf_suggestion_contract.py`,
`test_draft_pdf_suggestion_transport.py`, `test_draft_pdf_suggestion_http.py`,
`test_draft_pdf_suggestion_boundaries.py`, `test_draft_pdf_suggestions.py`,
`test_draft_pdf_suggestion_ui.py`, `test_draft_suggestion_evidence.py` and
`test_migrations_draft_pdf_suggestions.py`, alongside prior PDF/Excel/report/package
regressions. [PROJECT_STATE.md](./PROJECT_STATE.md) records actual results and remaining
browser/restart, CI/review and publication evidence. Synthetic success does not establish
real-provider or customer-evidence acceptance, production privacy/isolation, model
accuracy, full source portability, operational retention or OpenClaw retirement.
