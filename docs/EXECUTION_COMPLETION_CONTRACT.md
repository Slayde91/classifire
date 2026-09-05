# Execution completion acceptance contract

Status: consumer merged in PR #183; journal implementation candidate.
Baseline: d03753f (PR #183). No trusted production producer exists yet.

## Current boundary and problem

NoToolSessionAudit represents an observed Gateway audit page. The pinned
OpenClaw writer can be asynchronous, disabled or lossy; an empty page has no
completion certificate. Transports before PR #183 could return proposals after that
observation. Historical audit receipts must remain verifiable, but cannot be
reinterpreted as proof of complete capture.

## Change and trust boundary

Both visual and report transports require an application-configured completion
verifier before acquiring an inference token or sending HTTP. Missing verifier
fails closed. Independent no-tool attestation and post-call audit still run.
There is no configuration flag that makes missing evidence acceptable.

The verifier is trusted application code, supplied by the composition root,
not a Gateway response, model field, chat instruction or uploaded package. Its
contract is to authenticate a durable producer record and return typed evidence
only after verifying the producer's authority and exact invocation. A hash or
set of booleans received from a model is not verification. No production
implementation is supplied in this slice; synthetic implementations are tests.

The immutable context binds agent, session hash, canonical controller-request
hash, exact encoded request-body hash, exact response-byte hash, audit-observation
receipt hash, no-tool attestation receipt hash, dispatch time and observation time. The typed completion evidence
binds the context hash and durable producer receipt hash, terminal time, capture
interval, enabled/healthy writer state and pending/dropped/tool-action counts.

Consumer validation requires exact context identity, valid hashes and typed
nonnegative times/counts; terminal execution within the observed invocation
window; coverage starting no later than dispatch and ending no earlier than
terminal execution (never in the future); enabled healthy capture; and zero
pending, lost or tool-action records. Invalid, mismatched, incomplete, absent or
unavailable evidence cannot return a proposal. Verifier exceptions are sanitized.

These checks constrain a trusted verifier's output; they do not authenticate
arbitrary self-asserted producer data. The future producer/verifier must prove
capture started before dispatch, durable terminal ordering, loss detection and
failure handling. Polling empty pages or waiting a fixed time cannot supply it.

## Receipts and migration impact

Existing NoToolSessionAudit and its legacy hashes remain unchanged. Successful
new visual/report transport digests use version 2 and bind the validated
completion-evidence digest. Historical version-1 receipts remain historical;
this change neither rewrites nor upgrades them. Outer proposal response schemas,
canonical writes, locks, technical approval and Human Release stay unchanged.

Managed OpenClaw runtimes currently supply no completion verifier. They therefore
refuse inference dispatch after input/no-tool checks until a trustworthy producer
and verifier are implemented and wired deliberately. Existing deterministic
services, report preparation and historical verification remain available.
No provider or OpenClaw component is removed, and no real runtime is exercised.

## Acceptance evidence

Synthetic tests must cover absence before token/HTTP, valid acceptance and bound
receipt changes in both transports, invalid/untrusted shapes, identity mismatch,
stale/future/insufficient coverage, disabled/unhealthy capture, pending/lost/tool
records and sanitized verifier errors. Existing audit/no-tool, evidence binding,
controller, report and historical receipt tests remain required. Full hosted CI
and post-merge verification are publication gates, not production proof.

Next gate: implement and prove a trusted producer plus durable verification;
then wire it into composition. This consumer contract alone does not complete
OpenClaw retirement, provider execution or production readiness.


## Durable journal design (current candidate)

Current architecture has the required consumer but no durable execution producer.
Add a CLASSIFIRE service on the existing BackgroundJob table, with a distinct
job type and non-queued states so the generic worker cannot dispatch it. No schema,
migration, dependency, route or default runtime wiring is added.

Trusted application composition supplies a producer, producer identity, scoped
owner identity and a persistent journal authentication key kept outside the
database. The producer must authenticate/enforce its own capture boundary.
A local HMAC authenticates journal content and detects alteration; it does not
prove anything about remote tools outside that producer's control.

Ordering is reserve-and-commit -> trusted capture start -> commit invocation and
capture identity -> execute once -> validate terminal coverage -> commit sealed
terminal record -> reload and verify before returning completion evidence.
No producer execution occurs before the durable start record. The journal records
only IDs, hashes, times and safe codes, never prompts, evidence bytes or responses.
The producer owns capture and remote terminal assurance; this service never
manufactures those facts from an audit list.

A caller-supplied UUID identifies one invocation. Duplicate calls return only a
verified completed outcome; preparing/running/failed/interrupted invocations are
never automatically replayed. Primary-key insertion and version/status conditional
updates resolve competing callers without relying on SQLite row locks. A timeout
marks uncertain work interrupted; a late producer cannot complete it. Recovery
never treats an interrupted attempt as success or dispatches it again.

The completion verifier reopens the exact run, checks owner/producer, record seal,
state, context and coverage, then binds the durable record hash into evidence.
Authentication-key loss/rotation, deletion, tampering and wrong-owner/context reads
fail closed. Key rotation/retention and production adapter wiring remain explicit
operational follow-ups. There is no claim of malicious-database anti-rollback:
a trusted storage boundary is still required.

Acceptance requires file-backed disposable database tests for persistence/restart,
capture-before-execute ordering, duplicate/concurrent invocation, result tampering,
owner/producer/key/context mismatch, invalid/late capture, producer failure,
interruption and late completion. Managed OpenClaw remains blocked until an actual
producer meets this contract; synthetic tests are not provider parity.


## Phase 8 lifecycle integration (current candidate)

PR #184 merged the durable journal at bdd6719. Its execute wrapper cannot wrap a
transport whose verifier waits for that same wrapper's return. Add explicit
begin/complete/abort operations using the existing reservation, capture, conditional
transition and verification logic; retain execute compatibility.

An optional application-injected lifecycle begins after input/evidence/no-tool
checks and request-byte encoding, before token/HTTP. It binds exact agent/session/
request/body/attestation hashes and returns the committed dispatch timestamp.
Post-response parsing and no-tool audit remain mandatory. Completion authenticates
producer evidence for that exact context, commits/reloads the journal and supplies
the existing completion consumer. The result retains the existing version-2 schema.

Use one bound run/owner lifecycle per invocation. Duplicate begin must never
dispatch, even if a historical outcome exists; completed read/replay is a separate
journal operation. Failure after begin marks the attempt failed when storage is
available; abort failure preserves the original content-safe error and leaves an
unverified non-replayable record. An unsuccessful competing begin must not abort
another caller's active invocation. Interruption still rejects late completion.

Existing verifier-only injection stays compatible; providing both verifier and
lifecycle is refused. Managed factories supply neither and remain blocked.
The trusted capture verifier must authenticate real producer assurance; synthetic
ports prove sequencing only. There is no provider, API, schema, migration or
authority change, and no promise of remote cancellation.
