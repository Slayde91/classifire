# CLASSIFIRE OpenClaw Tools

Private role-limited OpenClaw plugin for the CLASSIFIRE canonical API.

## Security boundary

- The plugin may call only the configured loopback CLASSIFIRE API.
- Bearer tokens are read from a local secret file and are never embedded in prompts or source code.
- `before_tool_call` verifies the host-authoritative OpenClaw `agentId` and `toolCallId` before binding a tool execution to a service credential.
- Each tool is optional and must also be explicitly allowlisted for the intended `cf-*` agent.
- Human Release is not implemented by this plugin and is not exposed on the CLASSIFIRE agent API.
- The plugin does not provide shell, filesystem, browser, database, Gateway-control, cron, or elevated-exec capabilities.

## Tools

- `classifire_health` — all `cf-*` agents
- `classifire_workflow_status` — all `cf-*` agents
- `classifire_evidence_read` — `cf-intake-evidence`
- `classifire_physical_model_read` — `cf-physical-model`
- `classifire_technical_search` — `cf-technical-system`
- `classifire_package14_recommendation` — `cf-commercial-engine`
- `classifire_run_validation` — `cf-validator`
- `classifire_lock_snapshot` — `cf-output`
- `classifire_render_output` — `cf-output`
- `classifire_library_releases` — `cf-library-governance`

The initial plugin intentionally exposes read/guarded-final-stage capabilities only. Physical-model mutation, Repair Strategy selection, component derivation, quantity/labour derivation, commercial pricing application, and library mutation remain outside this first tool release until their agent-specific contracts are separately implemented and regression-tested.
