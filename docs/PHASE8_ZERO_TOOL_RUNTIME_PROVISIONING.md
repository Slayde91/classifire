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
and the exact tool policy `profile: minimal` plus `deny: ["*"]`. No allow or
sandbox-allow list is present.

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
conflicting identity. Live verification creates metadata-only sessions with
`runStarted: false`, verifies the resolved provider and model, reads
`tools.effective`, and fails unless both inventories contain zero tools.

An empty inventory is necessary but not sufficient to run inference. The
application must also bind each logical Phase 8 role to its corresponding
dedicated identity, attest the resolved provider/model for the exact session,
delay token access until attestation passes, send `tool_choice: none`, and audit
the session after every attempted turn. The managed Phase 8 runtime enforces
those additional requirements.
