# Phase 8 zero-tool runtime provisioning

Phase 8 visual proposal inference uses two dedicated OpenClaw identities:

- `cf-phase8-visual-physical`
- `cf-phase8-visual-validator`

They are separate from the normal `cf-physical-model` and `cf-validator`
identities. The normal identities retain operational read/write tools and are
therefore ineligible for this proposal-only inference boundary.

The reviewed definitions are pinned to OpenClaw `2026.7.1-2` and
`openai/gpt-5.6`. Each dedicated identity uses an isolated workspace and agent
directory, Docker sandbox mode with no workspace access, disabled elevation,
and the exact tool policy `profile: minimal` plus `deny: ["*"]`. No tool is
allowed. The explicit empty
`tools.sandbox.tools.allow: []` override suppresses OpenClaw's inherited Docker
sandbox allow gate; it does not allow a tool. The agent-level `deny: ["*"]`
remains authoritative and the live effective inventory must still be empty.

From an exact reviewed checkout, inspect the plan:

```powershell
./scripts/provision-phase8-zero-tool-agents.ps1
```

Install the missing identities and prove their live effective inventories are
empty without sending a prompt or image:

```powershell
./scripts/provision-phase8-zero-tool-agents.ps1 -Apply -VerifyLive
```

The script refuses an existing identity whose security-relevant configuration
does not exactly match the reviewed policy. It never repairs or overwrites a
conflicting identity. It can upgrade only the exact previously reviewed v1
profile to v2's explicit empty sandbox allow override. Missing definitions and
eligible upgrades are validated and installed as one file-based batch so
Windows command-line quoting cannot alter the policy JSON.
Live verification creates metadata-only sessions with
`runStarted: false`, verifies the resolved provider and model, reads
`tools.effective`, and fails unless both inventories contain zero tools.

An empty inventory is necessary but not sufficient to run inference. The
application must also bind each logical Phase 8 role to its corresponding
dedicated identity, attest the resolved provider/model for the exact session,
delay token access until attestation passes, send `tool_choice: none`, and audit
the session after every attempted turn. The managed Phase 8 runtime enforces
those additional requirements.

Each inference stage must also carry a receipt-bound retained-file token for
every image. The linked runner revalidates those tokens through its existing
database transaction before every direct-port call, and the managed transport
repeats the check immediately before it rereads and hashes the uploaded bytes.
Missing, mismatched, or stale malware-scan evidence fails before Gateway token
access or an image request.

Stored-file and malware-scan receipt identifiers remain local. They are not
included in the model prompt, public inference response, or deterministic
session key. The internal v2 transport receipt commits those identifiers into
the existing opaque `transport_receipt_sha256`; the session-key derivation stays
unchanged so retained controller receipts remain recoverable. A newer scan
receipt therefore blocks the next stage instead of silently creating a new
session.

For managed representative runs, the exact content-safe v2 transport-receipt
preimage for every successful stage is retained in the governed local
`openresponses-transport-receipts.json` sidecar. Its validator matches each
preimage one-for-one with the controller stage's request, session, payload and
transport hashes. The v2 representative receipt binds the bundle's canonical
hash, and the completion receipt binds the exact UTF-8/LF sidecar bytes. The
sidecar contains internal file and scan-attestation identifiers and evidence
fingerprints, so it is not copied into prompts, public inference responses,
human review requests or recovered review output. It contains no paths, image
bytes, prompt text, response text, URL, token or credential.

The writer does not enforce a filesystem ACL. Operators must access-restrict the
output directory and exclude the sidecar from publication and review handoffs.
A receipt-retention failure blocks controller acceptance and final artifact
completion, but it occurs after the external response and audit; it does not
claim to prevent an already-attempted transmission.

This sidecar proves which scan-attestation references and byte metadata were
committed into each opaque transport receipt. It does not independently replay
or prove the clean/latest malware verdict: that stronger claim would require
retaining and validating the governed malware-attestation receipt or chain.
