# Embedded workspace assistant

This increment extends the existing optional `draft_workspace_chat` service and
OpenAI Responses transport. The external ChatGPT/MCP connector is preserved.
It does not embed a signed-in ChatGPT account or copy its conversation history.

## Implemented advisory interaction

One collapsible panel is included in the authenticated application layout. On wide
screens it can dock beside the workspace, and a labelled width control keeps it
usable without covering the register. On small screens it uses the available width.
The register's **Ask AI about selection** action passes selected record identities;
users do not need to copy cell contents. Library tables offer explicit record
selection in the panel. Exact saved review and estimate context follows supported
detail pages and the register's applied selection.

The panel first previews the server-read context. Selected technical/library/pricing
details require an explicit preview option. Sending requires separate consent and
the exact preview hash. Nothing is sent while browsing, selecting records or viewing
the local preview. The assistant cannot save a Scope, select or approve a technical
system, change a price, run a downstream capability or release output.

The conversation includes both user questions and assistant replies as unverified
history, retaining each reply's uncertainty and reference labels. It retains at most
three complete exchanges within a 24,000-byte window. A reply whose qualified text
exceeds the per-turn limit is displayed but clears the remembered/follow-up window;
the interface explains that limit rather than dropping its qualifications.
Selection or saved-input changes invalidate preview and consent. Optional browser-tab
memory expires after 30 minutes and is scoped to the authenticated user and exact
context hash. Remembered text is displayed only after a fresh successful matching
preview; logging out or explicitly clearing removes it. There is no server-side
conversation store or new database migration.

## Architecture and boundaries

Current architecture: authenticated page -> selected Scope context -> existing
ChatPort -> optional bounded OpenAI Responses request.

Change: use that same path for the shared workspace panel, with typed selectors for
projects, saved Scope rows, exact saved system reviews/estimates and supported
library records. Permission-checked readers resolve identifiers. The frontend does
not serialize arbitrary screen contents, hidden forms, file paths or credentials.

Reason: the existing Scope-only panel could not support in-context questions across
the main working screens and sent previous questions without assistant replies.

Consequences: the optional model sees only the previewed, explicitly selected data
and bounded unverified conversation. Mutable selected context is hashed and rechecked
before provider use and before returning the answer. Missing information stays
unknown; a library entry or saved candidate never implies technical approval.

Migration impact: none. The connector, canonical models, provider settings,
OAuth/tunnel/allowlist policy and existing confirmation boundaries are unchanged.
There is no remote tool invocation or automatic transition to another capability.

## Validation and remaining limits

Implementation and exact validation results are recorded in PROJECT_STATE.md and
private synthetic UAT receipts. Do not infer operational activation from publication.
The running 8820 build was restored to 6c1e2a4 with chat disabled after 7dbc1cc passed
startup and its first browser reply but failed the follow-up HTTP 502. Fresh recovery,
browser reopening and exact Word ZIP checks passed. The historical cause remains
unknown; all earlier provider requests are consumed. New testing and activation
require a fresh exact approved plan.

The native panel uses the application's configured OpenAI API connection. The
existing external connector makes CLASSIFIRE tools available inside ChatGPT; it is
not a browser widget or a credential for this application's model requests.
Protected gpt-5-mini configuration and one synthetic connection reply were verified
before activation. The live first reply preserved unknown fields but broadened
uncertainty about a source-described separate opening. Neither that response nor
injected browser tests establish customer accuracy.

### Bounded failure diagnosis

The existing Responses adapter records one server warning on transport/response
failure: fixed reason category, random locally generated request UUID, HTTP status
when available, elapsed milliseconds and accepted response-byte count. The UUID is
also sent as X-Client-Request-Id and contains no user/project identity. No exception
text/traceback, provider header/body, prompt, reply, source/context, credential or
free-form error data enters this warning. Successful advice is not logged.

Categories distinguish network/timeouts, HTTP rejection, unsupported content/encoding,
byte/time limits, invalid JSON, incomplete response, unexpected output/refusal and
invalid advice. HTTP status is only an observation: 429 alone cannot distinguish
quota from rate limiting. The browser retains CHAT_PROVIDER_FAILED without diagnostic
internals. Model, time/token limits, no tools, no retries and admission boundaries
are unchanged. No database or conversation store is introduced.

This extends the current transport only for diagnosis because masking distinct
failures prevented targeted correction. Migration impact: none. Offline mocks verify
redaction, one-call failures, follow-up separation, partial reads and cleanup. The new
diagnostic can identify a recurring failure class; it cannot reconstruct the older
redacted 502. OpenAI documents [error categories](https://developers.openai.com/api/docs/guides/error-codes)
and [client request references](https://developers.openai.com/api/reference/overview#debugging-requests).
These mechanisms do not grant permission for automatic retries.

Original documents, source pictures and complete technical files are not included
in this context increment. Saved evidence references remain claims with explicit
limitations. This is not the full-report multimodal accuracy programme.

Official integration references: [OpenAI ChatKit](https://developers.openai.com/api/docs/guides/chatkit)
and [MCP and connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp).
ChatKit describes an embeddable application chat integration. No new ChatKit framework,
workflow or connector was introduced because this application already has the bounded
transport and native UI foundations needed for this increment.

## Approved target experience

The owner's 2026-09-13 design intention is to upload defect reports through the
ChatGPT integration in the CLASSIFIRE UI and interact with data on the current page.
The native panel is the working surface; the existing external ChatGPT/MCP connector
remains available over the same backend. The native panel uses an application API
connection, not an embedded signed-in ChatGPT website or shared ChatGPT account history.
No connector rebuild or new ChatKit dependency is required by this intention.

| User need | Current evidence | Required extension |
| --- | --- | --- |
| Ask about selected page data | Native typed selectors, preview/consent and advisory replies implemented | Complete separately approved real browser activation/acceptance |
| Attach a defect report in chat | Existing PDF/Word/XLSX UI/client intake services; no file input in the chat panel | Native attachment control and retained-source/status cards using existing intake |
| Read report evidence while discussing it | Existing format readers; current chat sends saved text context only | Explicit source text/image selection, bounded evidence preview and provider consent |
| Propose and confirm a page change | Existing typed client requests and browser confirmation; native chat has no write action | Supported action routing, review/diff card and distinct human confirmation |
| Download a reviewed result | Existing exact saved packages and original-bearing ZIPs | In-context access to the same package review, separate confirmation and exact download |

### Report attachment to saved Draft

1. Attach a supported report in the panel and choose the destination project/Draft.
   If a new project is needed, present and confirm that creation separately. Display
   file identity, source purpose, supported limits and accepted/refused status.
2. Upload to CLASSIFIRE retained storage through existing authenticated intake.
   Display the retained source and scan state. Upload does not send a file to OpenAI,
   create Scope entities, assign a system or approve a technical/commercial fact.
   Repeated clicks or retries must not silently duplicate sources or confirmed writes.
3. Explicitly request scan/processing; show bounded progress, failure/unsupported
   reasons and the retained source on reopening. Only clean, currently permitted
   exact bytes may be read. Reuse existing parsers; do not invent OCR/layout coverage.
4. Inspect retained text, tables and pictures beside the conversation. Preserve
   document/page/paragraph/table/cell/picture locators and exact original hashes.
   Document contents are untrusted evidence, never executable user instructions.
5. Request analysis; preview exactly which clean text/image evidence and page records
   will leave the application, then obtain provider consent. The existing chat
   transport currently accepts text only: image/original transfer is planned and
   requires its own bounded contract and validation, not an implicit full-file send.
6. Present a typed Draft proposal with source references, unknowns and conflicts,
   and a before/after review for existing records. Blank openings may have zero
   Services. Unresolved links remain held for review rather than guessed into the
   linked working register; do not erase them merely to satisfy a schema.
7. A separate, explicit same-user confirmation appends the reviewed revision through
   existing services. Recheck source hashes, target revision, rights and expiry.
   Changing selection, editing the page or losing permission invalidates the review.
   Refresh visible saved rows only after the confirmed write succeeds; show failures.
8. Reopen the exact saved revision and its retained evidence. Package configuration,
   package confirmation and original-bearing ZIP download are separate explicit
   actions. Scope confirmation never creates a package or runs Match/Estimate/Report.

Start with one supported synthetic DOCX journey, reusing Word intake/review and
ProjectPackage services; apply the same interaction to supported PDF/XLSX afterwards.
This ordering does not make Word parsing a substitute for general report accuracy.

### Working with data on the page

- Carry current screen/project, selected Defect, Opening, Service or multiple rows,
  selected technical systems/library/pricing records and exact Scope/Estimate
  revisions through typed selectors. Use permission-checked server readers.
- Let users analyse defects/services, review substrate uncertainty, explain systems
  and pricing, draft wording, find inconsistencies and summarise selected data.
  Prices do not establish technical suitability; unknown quantities remain unknown.
- Clearly identify the included selection. Unsaved edits, off-screen unrelated rows,
  hidden form values, credentials and entire library bodies are not silently captured.
  Change of context requires a fresh preview and invalidates stale proposed actions.
- Future explicit edit requests produce supported typed proposals and review cards.
  Advice alone remains read-only. Unsupported or ambiguous intent stays a question
  or a stated limitation; it cannot fall through to arbitrary tools or a hidden write.
- Requests to another capability remain independent and explicitly invoked, with its
  own prerequisites and review. Preserve current protected-state and release gates.
- Keep the panel available across the working screens without displacing dense data.
  Retain collapsible/docked/resizable layout and qualified bounded conversation.
  Reopening project/source/request/revision state uses durable application records,
  not transcript text. Do not promise indefinite conversation memory.

### Acceptance for the next implementation

Prove an actual browser journey: attach -> explicit scan -> source inspection ->
preview/consented analysis -> typed proposal -> distinct human confirmation ->
updated page -> reopen -> distinct package confirmation -> exact original-bearing ZIP.
Inspect source and ZIP bytes as well as visible controls; count actual provider calls
and record model/latency/cost limitations without claiming customer accuracy.

Also prove malformed/oversized/quarantined files, unsupported layouts, foreign
sources, expired sessions/requests, stale revisions, duplicate submits, changed
selection, unavailable scanner/provider and prompt injection fail safely. Advice,
preview and denied actions must leave domain rows unchanged. Preserve blank openings
and unresolved links. No downstream capability runs implicitly. Use synthetic data,
selected-checkout PYTHONPATH and fresh test directories; database tests use disposable
15433, never live15432. Real-provider/customer evidence and operational activation
retain their separately approved scope.
