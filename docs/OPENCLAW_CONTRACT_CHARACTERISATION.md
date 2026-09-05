# OpenClaw contract characterisation

**Shared baseline:** `c679405` (PR #179).
**Current candidate:** loopback buffered/decoded-response deadline enforcement; verify publication
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

### Current socket candidate

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

**Next task after merge: establish audit completeness from pinned upstream
semantics.** Inspect the 100-event limit, time window and any verified
pagination/truncation fields before adding synthetic acceptance/refusal tests.
A well-formed event list alone does not prove complete coverage. Preserve
legacy receipt hashes and independent no-tool attestation; identify missing
upstream evidence rather than inventing a protocol.

Before declaring full characterisation/retirement parity, also resolve:

- Broader protocol/handshake interoperability beyond the bounded socket cases above.
- Audit pagination/window/completeness assumptions and fallback semantics.
- Interrupted invocation state, cancellation, duplicate delivery and recovery.
- Provisioning/plugin host identity behaviour and clean-machine reproducibility.
- Mission Control registration/retry and content-safe telemetry requirements.
- Permitted provider egress, privacy/retention/residency, secrets and tenancy.

These are gaps requiring evidence, not proposed permission to weaken guards or
build a general agent platform. Decision 0001 retirement gates remain unchanged.
