# OpenClaw contract characterisation

**Shared baseline:** `45b1f7f` (PR #180).
**Current candidate:** explicit audit continuation/oversize refusal; verify publication
before treating candidate behaviour as shared main.
**Scope:** initial source/caller inventory and bounded synthetic fallback/audit
coverage. This is not full retirement parity or proof of a live deployed fleet.

## Entry points and current ownership

The caller search included Python under `src/classifire/` and `scripts/`,
PowerShell provisioning, the controlled-write plugin, config and tests.
References in prompts/config are bindings, not execution authority.
The following source inventory must be refreshed before replacing components.

| Boundary / caller | Contract and authority | Existing evidence / remaining limit |
| --- | --- | --- |
| `scripts/run_phase8_representative_package.py` | Explicit approved package; readiness then ManagedPhase8VisualRuntime; proposal-only rollback path | `test_phase8_representative_run.py` covers approval/revision/preflight and injected runtime. No real operation performed here. |
| ManagedPhase8VisualRuntime / Phase8OpenResponsesTransport | Exact evidence/profile, role-to-runtime-agent mapping, bounded HTTP invocation; no writer | `test_phase8_openresponses_transport.py` and `test_phase8_visual_runtime.py` cover byte/profile tampering, logical roles, no tools, errors, controller integration. |
| ManagedPhase8ReportAssessmentRuntime / report transport | Report policy bound to exact documentary/visual input before token/HTTP | `test_phase8_report_openresponses_transport.py`; runtime is service composition, not a supported operator route. |
| Report and family runners | Preflight owned approved report scopes before creating an injected port; preserve separate outcomes | `test_phase8_report_assessment_runner.py` and `test_phase8_report_evidence_family_assessment_runner.py`; no API/CLI/UI runner route. |
| ProposalOnlyVisualController / report controller | Fixed stages, bounded correction, hidden human reference and protected-state checks | `test_phase8_visual_proposal.py` and `test_phase8_report_assessment_controller.py`; successful inference is not semantic approval. |
| OpenClawGatewayNoToolSessionGuard.attest | Describe absent session, create without run/worktree, re-describe exact model, obtain effective tools | Transport tests freeze method order, model policy, unsafe session creation and existing-session refusal. |
| Guard.audit | Scoped tool-action audit after attempted turn; primary audit endpoint with legacy fallback | New cases below cover fallback scope, a literal receipt digest, malformed records and safe unavailability. |
| OpenClawLoopbackGatewayRpc | Literal loopback, authenticated framing, method/parameter allowlist and bounded deadline | Runtime tests cover endpoint refusal and least-privilege framing. Broader socket/protocol failure coverage remains to inventory. |
| OpenClawCliGatewayRpc / CLI-to-loopback wrapper | Fixed no-shell invocation; PR #179 refuses unavailable creation replay; read-only unavailable fallback remains | Existing unavailable-route test plus new refusal/malformed/timeout cases below. Unknown creation outcome fails closed; no recovery or automatic replay. |
| EnvironmentGatewayTokenProvider / readiness | Lazy fixed environment key; readiness describes a fixed absent session only | Runtime tests verify no-write probe and lazy token handling. No real secret was read here. |
| Controlled-write plugin / agent API / agent_security | Default admission-only profile; host-verified identity and server/persisted scopes; signed admission ID, no physical payload or lock tool | `test_openclaw_admission_writer_manifest.py`, `test_phase8_admission_only_profile.py`, `test_agent_security_boundary.py` and submission API tests. Static plugin checks do not prove live host enforcement. |
| Provisioning config/script and deployment candidate auditor | Pinned dedicated zero-tool profiles and explicit deployment prerequisites | `config/phase8-zero-tool-agents.json`, `scripts/provision-phase8-zero-tool-agents.ps1`, `scripts/audit_phase8_admission_deployment_candidate.py`; not executed here. Clean-machine evidence remains separate. |
| CLI Mission Control bootstrap / client | Probe/register operational agents; task creation is opt-in | `test_mission_control_client.py` covers object task responses. Registration/retry/privacy and full operational parity are not demonstrated by those two tests. |
| BackgroundJob / worker | Persisted queue shell, no handlers; no durable run/stage/lease recovery | `src/classifire/models.py` and `worker.py`. Must not be mistaken for implemented retry/cancellation/crash safety. |

Test filenames above live under `tests/`. The recovery script
`scripts/recover_phase8_evidence_review_request.py` processes retained evidence;
its OpenClaw references do not make it a replacement provider executor.
Mission Control's catalog and the plugin's non-default full-controlled-write
catalog do not prove those capabilities are working or authorised on main.

## Added observable contracts

Thirteen parameterised cases extend two existing suites:

- RPC_REJECTED, RPC_OUTPUT_INVALID and RPC_PARAMS_FORBIDDEN must propagate,
  without trying fallback or switching subsequent calls to fallback.
- A non-object result from either primary or fallback is refused.
- A synthetic subprocess timeout maps to RPC_UNAVAILABLE without including
  subprocess output/stderr in the public error.
- Audit endpoint fallback preserves exact session, agent, tool-action category,
  lower time bound and limit. The legacy receipt digest is a literal golden value.
- Non-object audit envelopes, absent/non-list events and non-object event entries
  fail as TOOL_AUDIT_INVALID; malformed success cannot be hidden by fallback.
- Both audit endpoints failing produces TOOL_AUDIT_UNAVAILABLE with no raw
  gateway exception in the public error.

The changed suites passed 54 tests; the eight-file handoff suite passed 83 tests.
That initial PR #177 slice changed no implementation or runtime policy. Existing no-tool checks remain
at the transport boundary; an empty audit alone does not authorise a model turn.

## Remaining gaps and next bounded task

### Merged PR #179: uncertain creation refusal

The composed lost-reply tests failed before the fix: timeout, generic subprocess
failure and OSError could all route a completed creation to fallback; the managed
runtime also attempted fallback. The wrapper now raises RPC_OUTCOME_UNKNOWN
when the primary returns RPC_UNAVAILABLE for sessions.create. It leaves route
selection unchanged. This is a conservative outcome classification, not proof
that the remote creation occurred. Even genuine pre-launch unavailability on a
direct create is refused; normal read-only readiness can select fallback first.

An earlier read selecting fallback still permits a single creation on that
route. Read-only timeout semantics remain RPC_UNAVAILABLE. The no-tool guard
maps the new internal error to existing TOOL_ATTESTATION_UNAVAILABLE, so receipt
schemas and historical verification do not change. The managed-runtime regression
proves no later fallback, token access or HTTP inference. No session cleanup,
remote reconciliation, general idempotency or explicit caller retry guarantee is
introduced; uncertain remote state remains a recovery limitation.

Five added cases bring the focused suite to 88 passing tests; 17 additional
report/representative tests pass. Source scope is the existing CLI/fallback
wrapper only. No real Gateway or provider was contacted.

### Merged PR #180: socket deadline correction

Two fake-clock tests reproduced acceptance after the deadline elapsed during
receipt or JSON decoding. Deadline checks now run before buffered-byte
consumption and before returning a decoded result. The existing deadline and
safe RPC_UNAVAILABLE code are retained; this does not provide hard process
preemption, new retries or remote cleanup.

Thirteen additional cases freeze safe closure and no repeated creation for
close frames, EOF, timeout/OSError, reserved/fragmented/masked/binary frames,
invalid UTF-8/JSON, oversized replies and unrelated connect/request IDs.
Every case uses an injected socket, one connection, operator.write for the
creation request and no real Gateway. Existing successful read framing remains
covered. Total validation: 103 contract/security plus 17 caller tests pass.

This is bounded negative coverage, not complete WebSocket conformance, live-host
compatibility or a claim that every frame/handshake variation is covered.

### Pinned upstream audit evidence and merged PR #181 page refusal

Read-only inspection on 2026-09-05 found installed openclaw 2026.7.1-2 matching
config/phase8-zero-tool-agents.json. These are local distribution artifacts,
not proof of a running process/configuration or independently authenticated npm
release. No application module was executed and no live ledger/config was read.

| Artifact under installed openclaw/dist | SHA-256 |
| --- | --- |
| audit--uog9aNn.js | 5B898585736CF4F9BC54B99448AC8833F806F126C4D9688448104A80A7DD3E5F |
| audit-event-store-D1P32Q4Y.js | AA6640A3BF796B9058EFEAC8A23862C1620D6ED4629CE00E24B29C082D6E5783 |
| schema-BuOFpc7K.js | B5B672DD1CE3579E2B030567EF192355374C052934CB4E252B793E08647D54AB |
| server-runtime-subscriptions-OlWMLbPY.js | 17E89DDAB3F5768B39F47F68FE0AAE35F724B6352789B6514ECD34F8BB3D71FB |
| audit/audit-event-writer.worker.js | 0BF29F9872DC2995CB1370AE0E19359A9BC102FB7AA45A7CA95C77477C4B8013 |

Verified contract:

- Stock server catalog registers audit.list; audit.activity.list was not found
  as a registered RPC. CLASSIFIRE's fallback filters match the stock schema.
- Results contain events and an optional nextCursor. The store reads limit+1,
  orders newest sequence first, and returns a cursor only when another stored
  row exists. Cursor filtering is sequence < cursor; after/before are inclusive
  occurredAt bounds. Limit is 1-500 upstream; CLASSIFIRE requests 100.
- Retention is 30 days and at most 100,000 rows. Queries enforce the retention
  floor even if the requested after is older.
- The writer uses a worker thread and a bounded 4,096 pending-event queue.
  Unavailable/full queues can drop metadata; write failures are logged.
  audit.enabled=false disables new capture while existing records stay readable.
- audit.list reads the store directly; its response has no writer-health,
  coverage/loss, terminal-execution or persistence-barrier certificate.

PR #181 rejects any nextCursor presence (including malformed empty/null
values) and more than the requested 100 events as TOOL_AUDIT_INVALID. It does not
retry a malformed success or page indefinitely. Any observed tool event already
causes transport refusal, so fetching later pages cannot turn it into a valid
no-tool result. A terminal 100-event page still reports detected tool activity.
Valid legacy empty-page receipts retain the literal golden hash.

Ten new refusal cases failed before the correction; eleven added cases bring
validation to 114 contract/security plus 17 caller tests. Empty-page-with-cursor
fixtures are inconsistent/malformed upstream responses, not claimed observed
server output. A valid nonempty continuation already prevents no-tool acceptance
downstream; the correction additionally prevents issuing a partial audit receipt.

**Material remaining gap:** no cursor means only that this retained query has no
further page. It does not exclude pending/lost/disabled capture or retention loss.
Shared main through PR #182 still permits proposal return after that observation.
The current completion-consumer candidate now requires a trusted verifier before
inference dispatch and validates exact invocation/terminal/coverage evidence before
acceptance. Managed factories have no verifier and deliberately refuse dispatch.
See [Execution completion contract](./EXECUTION_COMPLETION_CONTRACT.md).

Version-2 transport receipts bind the completion digest; historical audit-page
hashes remain unchanged and never become proof of complete capture. The verifier
port is trusted application code, not a mechanism for accepting self-asserted
model/Gateway fields. A production producer and authenticated verifier remain
absent. The twelve-file synthetic suite in the handoff passes 171 tests.

**Next task:** establish durable execution journal/producer/verifier evidence,
using existing job/service boundaries where suitable. Prove pre-dispatch capture,
terminal ordering, invocation ownership, disabled/lost/pending capture refusal
and crash/replay recovery. Do not fabricate upstream guarantees, infer completion
from polling, or retire OpenClaw/no-tool guards before parity.

Before declaring full characterisation/retirement parity, also resolve:

- Broader protocol/handshake interoperability beyond the bounded socket cases above.
- Trusted audit completion, persistence/loss and retention coverage: stock API is insufficient.
- Interrupted invocation state, cancellation, duplicate delivery and recovery.
- Provisioning/plugin host identity behaviour and clean-machine reproducibility.
- Mission Control registration/retry and content-safe telemetry requirements.
- Permitted provider egress, privacy/retention/residency, secrets and tenancy.

These are gaps requiring evidence, not proposed permission to weaken guards or
build a general agent platform. Decision 0001 retirement gates remain unchanged.


### Durable journal candidate after PR #183

PR #183's consumer is merged at d03753f; main CI 33939296281 passed.
The current journal service reuses BackgroundJob with distinct non-queued states,
committed capture before producer execution, sealed terminal records, exact
owner/producer/invocation verification, and refusal to redispatch uncertain work.
It adds no API, default runtime wiring, schema or dependency. Local tests prove
27 journal cases and retain 171 transport/caller regressions; three PostgreSQL
restart/concurrency cases use the existing guarded disposable fixture.

The journal authenticates its stored records, not arbitrary remote capture claims.
A trusted producer must supply and authenticate capture/terminal evidence.
Next integrate the transport pre-dispatch/post-response lifecycle without a
circular completion dependency, and prove it synthetically. Production capture,
key custody/rotation, real cancellation and OpenClaw retirement remain gated.
