# Embedded workspace assistant

This increment extends the existing optional `draft_workspace_chat` service and
OpenAI Responses transport. The external ChatGPT/MCP connector is preserved.
It does not embed a signed-in ChatGPT account or copy its conversation history.

## User interaction

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
The running 8820 build remains the separately approved 6c1e2a4 until another exact
activation decision and recovery verification.

The native panel uses the application's configured OpenAI API connection. The
existing external connector makes CLASSIFIRE tools available inside ChatGPT; it is
not a browser widget or a credential for this application's model requests.
No application model/key is currently verified configured, and no real provider
response is claimed. Synthetic injected responses exercise interaction and safeguards,
not model accuracy. Model/credential configuration, external data transfer and
activation remain separately controlled.

Original documents, source pictures and complete technical files are not included
in this context increment. Saved evidence references remain claims with explicit
limitations. This is not the full-report multimodal accuracy programme.

Official integration references: [OpenAI ChatKit](https://developers.openai.com/api/docs/guides/chatkit)
and [MCP and connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp).
ChatKit describes an embeddable application chat integration. No new ChatKit framework,
workflow or connector was introduced because this application already has the bounded
transport and native UI foundations needed for this increment.
