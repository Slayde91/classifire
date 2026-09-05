# Execution completion acceptance contract

Status: implementation candidate under accepted hybrid Decision 0001.
Baseline: 4ab8723 (PR #181). No trusted production producer exists yet.

## Current boundary and problem

NoToolSessionAudit represents an observed Gateway audit page. The pinned
OpenClaw writer can be asynchronous, disabled or lossy; an empty page has no
completion certificate. Current transports can return proposals after that
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
