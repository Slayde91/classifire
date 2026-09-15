# Embedded workspace assistant

This increment extends the existing optional `draft_workspace_chat` service and
OpenAI Responses transport. The external ChatGPT/MCP connector is preserved.
It does not embed a signed-in ChatGPT account or copy its conversation history.

## Explicitly saved native proposals

The local decision extension shows a recorded confirmation with its exact reviewed Scope
revision, or a separately confirmed rejection. The original generation is not rewritten.
It reuses existing reviews, does not infer decisions from later content, and adds forward
migration0049. HTTP/service and migration checks are separate from browser acceptance;
actual-app HTTP/server restart passed for the earlier decision candidate, while rendered
browser acceptance remains unverified.

The [native history contract](./NATIVE_WORKSPACE_PROPOSALS_V1_CONTRACT.md) adds
**Save proposal for later** and **Saved AI proposals** for Word/PDF/XLSX additions
and selected Scope edits. Saving discloses retention of the question, included
conversation, exact disclosed context and generated reply. Generation does not save;
retention does not confirm Scope or create a package. Reopening is permission/source/
scan checked, and stale proposals have no review controls. Ordinary advice is not
retained through this action. Limits are1 MiB,100 records per Draft and a15-minute
signed save authorization. This local schema extension requires migration0048 and a
separate approved activation. No new provider or downstream capability is invoked.

Unsaved proposals remain transient. Explicit retention preserves validated generated
fields and prepared review controls. Explicit review identities link later decisions; matching content never infers a decision. The local
[selected package history](./NATIVE_PROPOSAL_PACKAGE_HISTORY.md) extension optionally
includes the exact generation and selected decision through separate package confirmation.
Imported history remains foreign and read-only, without local proposal/approval authority.
Raw provider bytes and prompt-version reproducibility are also outside this increment.

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
general conversation store. Optional saved proposals and decisions are separate
retained records requiring migrations 0048/0049, as described above.

## Selected saved Estimate lines

Saved Estimate pages provide checkboxes and **Ask AI about selected lines** in the
working screen. Select up to 50 lines, preview the exact context, and explicitly
include commercial details and consent before sending. Selection changes clear the
old preview, conversation and consent. An empty page selection includes no line
values; it never silently expands to all lines.

The existing typed Estimate selector accepts optional `line_ids`. Omitted or null
keeps the earlier whole-Estimate context contract for existing clients. An explicit
list, including an empty list, limits context to those exact saved-revision lines.
Duplicate, invalid, oversized or missing-line selections are refused. Partial
selection excludes the overall Estimate summary; it does not calculate replacement
totals. Unknown and zero values stay distinct. With sensitive details off, prices
and line values remain withheld. Existing Scope/Estimate permissions and exact
preview-hash checks still apply before and after a reply.

This extends the current permission-checked context reader and native panel. It adds
no model, writer, migration or dependency. Advice does not edit prices or quantities,
recalculate the Estimate, approve a technical system or run downstream capabilities.
Real-provider and live acceptance remain separate from synthetic validation.

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

Migration impact of advisory context: none. Optional retention/decisions require
0048/0049. The connector, canonical models, provider settings,
OAuth/tunnel/allowlist policy and existing confirmation boundaries are unchanged.
There is no remote tool invocation or automatic transition to another capability.

## Validation and remaining limits

Implementation and exact validation results are recorded in PROJECT_STATE.md and
private synthetic UAT receipts. Do not infer operational activation from publication.
The last approved operational 8820 build was restored to 6c1e2a4 with chat disabled after 7dbc1cc passed
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

Original documents and complete technical files remain excluded from model input.
The Word/PDF/XLSX paths permit selected text/cells and verified PNG pictures; reference
claims retain their limitations. This is not full-report multimodal accuracy acceptance.

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
| Attach a defect report in chat | Native DOCX/PDF/XLSX attachment, retained-source/status cards and explicit scan reuse existing intake; saved sources reopen without chat memory | Synthetic journeys and explicit saved generation/decision history exist; complete new-control browser, real-provider/live and full-lineage acceptance |
| Read report evidence while discussing it | Native panel selects bounded Word blocks/pictures, one PDF page or XLSX header/rows/pictures for preview/consent and typed additions | Complete real-provider acceptance and broader format coverage |
| Propose and confirm a page change | Explicit Word/PDF/XLSX additions reuse their separate review; selected saved Scope replacements show field differences and validate in the manual editor before separate save | Real-provider/live acceptance, full AI lineage and remaining non-Scope action contracts |
| Download a reviewed result | Existing exact saved packages and original-bearing ZIPs; local v7 adds explicitly selected generation/decision history | Complete rendered-browser acceptance of new history choices and operational acceptance |

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
   will leave the application, then obtain provider consent. Supported Word/PDF/XLSX
   paths send only the selected text/cells and verified PNG previews. Original files,
   unselected evidence and unsupported formats are excluded.
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

The bounded DOCX, PDF and XLSX journeys are implemented and synthetically validated.
Continue acceptance of decision/package history and operational behavior. Supported
format orchestration is not a substitute for representative report accuracy.

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
- Selected Scope edit requests produce typed replacements and a field diff; other
  edit actions need their own supported contracts and review cards.
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

## First native Word attachment increment

`draft_workspace_word_ui.py` is a thin browser adapter over `word.intake()` and the
existing Word picture route. It uses the current session, write/read permissions,
CSRF and shared bounded multipart reader. It does not call external MCP or create
another identity, parser, database, source model or provider transport.

Open an existing Draft, open the assistant, then expand **Attach a Word defect
report**. The destination and accepted size are shown before upload. Explicit scan
and inspection use separate controls; text is paged in groups of five blocks with
structural locators, and pictures use the existing exact-byte reader. Duplicate
same-Draft uploads reuse the source. Current permission determines which write
controls are available; all operations recheck server authority. Source status is
processing state, not technical approval, and an expired or changed scan can still
refuse a later read. Source text is rendered as text, never executed as instructions.

The generated synthetic browser journey verified upload without scan/AI, duplicate
reuse, explicit scan, retained text/picture inspection, unchanged Scope, exact
original bytes, question preservation, collapse/dock/resize, narrow layout and
reopening after the isolated server restarted. It used disposable PostgreSQL15433
and an injected scanner verdict; it is not real malware or provider acceptance.
All 108 affected Word/client/chat/migration cases passed. Full Ruff, Mypy over 234
source files, scoped Bandit and JavaScript syntax checks passed.

This is the first C2 interaction, not the complete report-to-Scope exit. Report
contents/pictures now enter advice only through the separate explicit selection and
consent extension below. The typed-additions section now records separate Scope
and package confirmation. Existing manual Word review remains available.
Live8820 remains on the rollback build; this feature has not been activated.


## Selected Word evidence disclosure

Current architecture -> change: extend the existing typed workspace context and
advisory port with one optional Word selector and bounded internal image parts.
The shared Word reader resolves source ID, document hash, up to10 text locators and
two picture IDs under current permission, scan and retained-byte checks. No
browser-provided evidence body, arbitrary URL, original file, tool invocation,
new provider or canonical writer is accepted. Migration/dependency impact: none.

Reason: attachment inspection alone could not let users discuss the retained report.
Consequences: the preview contains exact text, picture identity/PNG hashes and sizes,
source/document/scan hashes, omitted counts and ownership/layout limitations. The
UI shows readable selected text and pictures; exact JSON retains traceability.
Selection changes invalidate preview, remembered context and consent. Source/rights
changes are checked before provider use and again before returning advice.

The same Responses adapter retains no tools/retries/persistence, fixed response
limits and safe diagnostics. Requests without selected pictures keep their existing
text-only shape. Picture requests use at most two verified PNGs, each at most2MiB;
text context remains at most64KiB and the encoded image request at most6MiB. Images
use high detail and incur image-input usage; no cost or accuracy result is claimed
from mocks. The adapter checks bytes against preview hashes and refuses remote URLs
or mismatched parts. The original document never leaves this path. The format follows
OpenAI's [image-input documentation](https://developers.openai.com/api/docs/guides/images-vision);
[gpt-5-mini](https://developers.openai.com/api/docs/models/gpt-5-mini) supports image
input. Real-provider acceptance remains separately authorized.

Validation:94 affected tests passed, including exact outgoing PNG bytes, unchanged
protected tables, no implicit inclusion, consent refusal, stale selection, expired
scan, foreign access, revoked rights during a reply and malformed/remote image parts.
The browser found a shared-reference invalidation defect; copied event selections
fixed it. Final restarted Chrome checks passed with scripted advice, zero real
provider calls, unchanged Scope and exact original download. Final desktop/mobile
screenshots were inspected. The following increment covers typed additions and
separate Scope/package confirmation synthetically; complete operational C2 remains.


## Native Word additions and separate confirmation

Choose **Propose new Scope records from selected Word evidence** in the same panel.
Select at least one Word text block and optionally pictures, preview, then explicitly
consent. Changing the action clears preview and consent. The current user needs
project write access and the latest Scope revision even to prepare this action.

The existing Responses port uses a separate strict output schema derived from the
Scope domain model; all fields, including null unknowns, are explicit, following
OpenAI's [structured output contract](https://developers.openai.com/api/docs/guides/structured-outputs).
The server enforces the same constraints for injected ports. At most25 new records
are allowed across Defects, Openings and Services. Every item needs a selected text
locator and a supported evidence basis. Text quotes must be exact substrings;
pictures must be explicitly selected. Confirmed states, invented links, duplicate
claims and blank-opening service links are refused. Known dimensions/quantities and
shared openings are retained; unknowns remain null or unlinked. Model IDs are local
graph placeholders and are remapped before composing additions with unchanged rows.
New observations, assumptions and exclusions are excluded because the existing Word
entity-review contract does not support their source bindings. Existing values remain.

The proposal card shows additions, named relationships, source quotes/rationale and
unknowns. **Review proposed Word Scope** opens the existing complete Word preview.
It does not save. The user reviews the full graph and selected source links, then
checks the existing confirmation and saves one Draft revision. Its signed token is
bound to the user, browser session, source, graph and revision and expires after15
minutes. Changed payloads, revoked rights, stale revisions and repeated saves fail
closed. Package selection/save remains a later, distinct action on the existing page;
no technical matching, estimate, report generation, canonical lock or release is run.

Unsaved proposal controls are transient and are not restored from conversation.
A separate explicit retention action saves validated generation fields and review
controls; the confirmed revision retains human Word evidence references. Raw provider
wire responses and full reproducible model execution remain excluded. This does not claim that
all AI provenance or broader report coverage is finished. Empty unsupported proposals
have no review/save control. Advice mode keeps its original contract.

Validation:127 checks (126 affected regressions plus one added pure contract test)
passed; full Ruff/Mypy, scoped Bandit and JS syntax passed. Final synthetic Chrome
upload-to-Scope-to-package acceptance passed, with distinct consent/confirmations,
exact saved graph and original DOCX in the ZIP, reopening after test-server restart
and narrow-panel checks.
Screenshots were inspected. No real provider, real scanner or customer-accuracy
acceptance was performed. No schema migration, dependency or live change was needed.


## Selected Scope replacements and manual confirmation

Select register rows and use **Ask AI about selection**, then **Propose edits to
selected Scope records**. A row supplies its Defect/Opening/Service identities;
column highlighting is not a field-level edit restriction. The exact selected IDs
and saved fields appear in the preview. Unsaved editor values are excluded. Preview
and consent are required, and a change of selection/action invalidates both.

The server supports complete replacement records for at most25 explicitly selected
Defects, Openings, Services or observations. Context ancestors are not edit targets
unless selected. All fields, including null unknowns, are required. IDs cannot be
added/deleted; unselected rows, assumptions and exclusions remain unchanged. Each
changed record needs a reason. New links must point to supplied context, and the
merged graph must still pass ordinary Scope validation. Confirmed states are refused.
Current write permission and revision are checked before and after the response.

The card shows named fields, before/after values, reasons, validation findings and
how many retained source claims become stale. **Review changes in Draft editor**
submits only `action=validate`. That screen is unsaved until the user independently
clicks **Save new revision**. Existing session/CSRF, current write permission and
optimistic revision checks apply; repeated or stale saves fail. Old evidence references
are preserved rather than replaced with model claims. An optional saved-proposal
identity links confirmation to its immutable generation. Manual editor changes remain
possible and are saved as the user's reviewed Draft. Word's signed review stays separate.

No matching, estimating, package creation, technical approval or release runs as a
side effect. Empty proposals provide no review control. Proposed edit controls are
transient unless explicitly retained; saved proposals reopen through current
rights/source checks. Match/Estimate/library/pricing edits remain unsupported. Synthetic coverage proves the mechanical review
boundary, not model accuracy or production acceptance. See PROJECT_STATE.md for the
actual tests and private receipt status.

Validation:147 distinct tests passed, including selected/unselected isolation,
multiple record kinds, total edit limit, explicit fields, stale/repeated saves,
revoked permissions, relationship conflicts and retained/stale source claims.
Full Ruff/Mypy236, scoped Bandit and JavaScript syntax passed. Synthetic browser
review/save/reopen and test-server restart preserved exact bytes; local editor changes
cleared old proposals/consent and cancelling unsaved navigation preserved local work.
Desktop/narrow/editor screenshots were inspected. No real provider call occurred.


## Native PDF attachment and inspection

Open **Attach a PDF defect report** in the same panel. The destination is the current
Draft; creating a new project remains separate. Upload retains the original through
the existing PDF policy, with same-byte reuse. **Scan and prepare report** is another
explicit action. **Inspect retained evidence** shows one page's retained text, page
locator and rendered PNG; Previous/Next page never run analysis. **Download retained
original** verifies current rights, source bytes and scan state before returning the
exact PDF as a download. **Review this PDF page** opens the existing in-app page review
with that page selected. Its suggestions and Scope confirmation retain their own
controls and configuration; none runs because a PDF was uploaded or inspected.

PDF pages are not automatically included in native chat context. Two unchecked
controls select the inspected page's text and/or image. Selecting PDF clears Word
selection and old preview/consent, and vice versa. Inspecting another page does not
silently select it. The server admits one explicit page (1-50), rejects mixed formats
and reads the exact retained evidence under current source/scan/access checks. Source kinds are
restricted to Word/PDF and remain bound to their own retained purposes; a source ID
cannot be read under the other format or another user's Draft. Both controls share
the existing session adapter and driver; no new intake pipeline or provider is added.

The initial browser check exposed PDF text/image overflow at390px. Reusing the existing
evidence-block class constrains the image and wraps retained text. Failed and expired
scans or integrity mismatches still withhold evidence and originals. Exact validation
results and remaining operational limitations belong in PROJECT_STATE.md/private receipts.

Validation:100 affected PDF/Word/chat/edit tests passed without failures/skips in432.920s.
Full Ruff/Mypy236, scoped Bandit and JS syntax passed. Final synthetic Chrome upload,
scan, both page reads, selected-page review navigation and exact original download
passed. Desktop/390px screenshots were inspected. Reopening after a test-server
restart returned identical PDF bytes and unchanged Scope with no rescan/model/package.
No real scanner, model accuracy or live acceptance is claimed.

A separate browser compatibility check also passed Word upload/scan, selected text/
picture preview, unchanged Word selection while PDFs load and exact Word download.


## Native PDF evidence and typed additions

After selecting page text and/or image, **Preview context** displays the source,
page, exact selected text and PNG hash/size. Other pages, original PDF bytes and
external links are excluded. The existing transport sends only the selected text
and verified PNG after explicit consent. Text-only and image-only requests remain
possible; an image-only proposal cannot quote text omitted from its preview.

**Propose new Scope records from selected PDF evidence** reuses the strict additions
contract: at most25 new Defects/Openings/Services, complete typed fields, explicit
unknowns and source-bound claims. Existing rows remain unchanged. Wrong page/quote/
image claims, Confirmed states and unbound rows are refused. Changed selection,
revision, rights, scan or document identity requires fresh valid context; a reply
cannot save data. The panel clears consent after producing a proposal.

**Review proposed PDF Scope** opens the existing signed PDF page review with the
complete graph, selected page and current revision. Its separate unchecked human
confirmation is the only save step. Package preview and save remain another explicit
interaction. Reopening saved results does not rerun model, scan or other capabilities.
The existing PDF human page/entity references are retained on confirmation. Validated
generated claims/rationale are retained only through the separate native save action. This
is distinct from PDF suggestion batches; the PDF review path adds no new writer
or provider. Optional native retention uses the 0048/0049 records described above.

Synthetic browser acceptance proved this sequence and the exact original-bearing
ZIP across a test-server restart. It does not establish real model accuracy, real
scanner acceptance, operational activation or a complete production C2 exit.


## Native Excel attachment and retained inspection

Open **Attach an Excel defect register** in the current Draft's panel. This retains
supported `.xlsx` evidence under the existing Scope workbook policy. **Scan and
prepare report** remains separate. **Inspect retained evidence** displays five rows
at a time and lets you change worksheets. Each cell shows its coordinate, parser type
and exact supported value; formulas are never evaluated. This is not Excel's visual
formatting, inferred physical relationships or a pricing import.

Pictures whose structural anchors intersect the displayed rows use the existing
verified PNG reader. The panel states how many other pictures are omitted. Anchors
show placement, not ownership or quantity; original and preview hashes stay distinct.
**Download retained original** returns the exact workbook under fresh rights, source
integrity and current scan checks. **Review this worksheet** opens the existing
mapping UI with that worksheet/row position. Mapping, reviewing and saving require
their own controls; browsing never runs them.

Loading or scanning Excel does not clear or extend an existing Word/PDF model
selection. Explicitly selecting Excel evidence replaces the other format selection
and invalidates old preview/consent, as described below. Model configuration can remain disabled while
these local attachment controls operate. Pending, failed, expired and corrupt sources
are withheld; cross-user, cross-format and pricing-purpose access remains refused.


Both context endpoints execute blocking context readers in the existing thread
pool. A source-lock wait therefore allows other requests and dependency cleanup to
continue; integrity locks and current authority checks are unchanged. A bounded
HTTP concurrency regression covers both the legacy Scope and workspace endpoints.

## Selected Excel evidence and typed additions

After inspection, choose a header and 1-10 distinct data rows after it, plus up to
two retained pictures from the same worksheet (4 MiB combined). The exact preview
includes every retained cell in the selected rows and header, coordinates, parser
types and selected pictures. Other rows/sheets/pictures and the original XLSX are
excluded. Formula/error cells remain source text, not evaluated quantities. A header
change clears the row/picture selection and consent. Choosing another report format
replaces this selection. Nothing is sent until a fresh preview and explicit consent.

**Propose new Scope records from selected Excel evidence** returns at most 25 new
Defects/Openings/Services in the existing additions contract plus all 12 nullable
column mappings. Text/both claims quote exact selected mapped non-formula/non-error
data cells; headers cannot support physical claims by themselves. Pictures must be
selected and claims must name a selected data-row anchor. Placement does not establish
ownership. Missing facts and mappings stay unknown. Existing rows are copied unchanged.

**Review proposed Excel Scope** shows the proposed mapping and graph through the
existing signed workbook review. The reviewer checks cells, pictures, relationships
and unknowns, then separately confirms a new revision. Package selection and save
remain separate and may include the exact original XLSX. No Match, Estimate, report,
price, technical approval or canonical release runs implicitly. Modified mappings,
stale Scope/source/rights and repeat confirmations are refused by existing guards.

Confirmed revisions retain human workbook row/entity references with mapped cells
and selected image identities. Saving the generation, included conversation and
validated claims requires the separate native retention action; it never happens
implicitly. Raw provider bytes/prompt-version history and full AI lineage remain open.
The synthetic browser/ZIP/restart checks exercise orchestration and evidence integrity;
scripted replies and an injected clean scan establish neither real model accuracy nor
malware acceptance. Exact validation and publication state belong in PROJECT_STATE.

## Session and response failures

Opening a saved proposal is tied to the current conversation context and latest
proposal choice. Clearing the conversation, changing its context or choosing another
proposal discards an older read's delayed content and errors. The last choice wins
regardless of response order; no reply grants consent or runs another capability.
Repeated saved-proposal list refreshes also accept only the latest request's
result. A delayed older success or failure cannot replace the current list/status
or restore proposal controls after a newer session refusal. A completed rejection
removes only its original proposal cards, including when another proposal was opened
or the conversation cleared while it waited. The current shipped-script suite has
35 passing Node cases; this is a synthetic DOM/event surface, not rendered-browser
acceptance. Exact validation versions belong in PROJECT_STATE.md.

The native panel treats same-origin login redirects and401 responses as an inactive
session. It asks the user to sign in again and reload the workspace; it does not replay
an upload, model request, proposal save or confirmation. Malformed JSON and unexpected
HTML show fixed messages instead of parser/server-body details. Known permission/source
errors remain explicit, and lost attachment access clears source cards. The server's
existing authentication and separate confirmation boundaries remain unchanged.

Development check: `node --test tests/js/workspace_session_test.cjs` executes the shipped
scripts with a minimal event/DOM surface. The pytest wrapper runs it when Node.js is
available and explicitly skips otherwise. This is not visual/browser acceptance.

Attachment reads also remain tied to the current page lifecycle while response bodies
are decoded. After leaving and restoring the page, an older permission/missing-source
error cannot clear freshly loaded Word, PDF or Excel cards or change their loaded
state. Current access refusals still clear inaccessible cards. Page restoration
refreshes retained-source metadata only; it does not replay uploads, scans or model
requests, select evidence, or confer consent.
