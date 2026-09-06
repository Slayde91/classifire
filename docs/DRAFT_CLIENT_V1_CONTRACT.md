# Draft client v1: authenticated MCP and human confirmation

## Status and purpose

2026-09-06. Local implementation on `feat/chatgpt-draft-client-20260906`; verify
live PR/head/CI before assuming shared publication. This is a first ChatGPT-compatible
client surface over the existing standalone core, not production OAuth deployment
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
`classifire:draft:export`. Proposal/export tools also require read. No mapping is
inferred from an email address or client payload. User permissions remain additional
requirements; token scopes never grant a role or canonical authority.

Accepted tokens are RS256 access JWTs (`typ: at+jwt`) with the configured kid,
issuer, exact `/mcp` resource audience, subject, client ID, token ID, scope, integer
iat/nbf/exp and at most 900 seconds of lifetime. Private keys, remote key headers,
unrecognized algorithms/claims used for authority, unknown accounts/clients,
wrong audiences and expired tokens fail closed. No client-selected URL is fetched.
The application rereads policy for revocation and account/client/scope changes.
Issuer/resource changes require restart. Keys are operator-pinned; automatic JWKS
refresh and issuer introspection are not implemented. Local token-ID revocation is
immediate; issuer-only revocation can otherwise lag until token expiry.

Serve `/.well-known/oauth-protected-resource/mcp` with exact issuer/resource and all
three supported scopes. The SDK supplies the bearer challenge and protocol handling.
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
Import/inspection remains available in the standalone UI, not a new MCP upload tool.

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
linking, remaining independent capability tools and production acceptance remain open.
