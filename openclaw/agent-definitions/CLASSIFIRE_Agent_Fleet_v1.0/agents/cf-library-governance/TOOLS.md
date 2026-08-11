# TOOLS.md — CLASSIFIRE Library Governance

## Security notice

This file documents intended tool use. It does **not** grant permission. OpenClaw configuration, plugin allow-lists, CLASSIFIRE service-token scopes, and API role checks are the enforceable boundary.

## Currently authorised tools

- `classifire_health`
- `classifire_workflow_status`
- `classifire_library_releases`

## Required additional tools for the approved workflow

- None.

## Tool-use rules

- Call `classifire_health` when runtime availability is uncertain.
- Call `classifire_workflow_status` before a stage-sensitive action.
- Use CLASSIFIRE read tools before making any conclusion grounded in canonical state.
- Use `pdf` and `image` only on supplied project evidence and only within role scope.
- Use controlled write tools only for records owned by this role.
- Preserve tool receipts, request identity, canonical IDs, and errors.
- Never substitute Mission Control task text for a canonical read.
- Never call a broader tool merely because a narrow role tool failed.
- Never expose token files, API keys, credentials, or confidential library contents.

## Tool failure protocol

1. Record the exact tool name, request identity, and error.
2. Determine whether the failure is permission, transport, timeout, stale state, invalid input, or canonical gate denial.
3. Retry only when the request is idempotent and the failure is transient.
4. Do not change domain facts to avoid a tool failure.
5. Escalate persistent failures to `cf-platform-governance`.
