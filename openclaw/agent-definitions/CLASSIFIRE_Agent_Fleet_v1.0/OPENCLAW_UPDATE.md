# Updating the OpenClaw CLASSIFIRE agents

## 1. Install or refresh the canonical Agent Fleet

The repository-controlled setup reads `FLEET_MANIFEST.json`, validates all nine agents and all seven required Markdown files per agent, creates missing OpenClaw agents, refreshes existing agents, copies the canonical files into each workspace, and synchronises identity metadata.

```powershell
Set-Location "C:\CLASSIFIRE"
.\scripts\setup_classifire_openclaw.ps1
```

Canonical fleet source:

```text
C:\CLASSIFIRE\openclaw\agent-definitions\CLASSIFIRE_Agent_Fleet_v1.0
```

Workspace root:

```text
C:\CLASSIFIRE-OpenClaw
```

Do not maintain a second writable copy of the fleet as the authoritative source.

## 2. Apply role-limited plugins

```powershell
.\scripts\install_classifire_openclaw_plugin.ps1
.\scripts\install_classifire_controlled_write_plugin.ps1
```

The CLASSIFIRE read-only plugin grants `cf-validator` canonical evidence/physical-model reads plus PDF/image inspection while preserving the validator's no-write boundary. The controlled-write plugin remains role-limited and does not grant Human Release.

## 3. Validate OpenClaw

```powershell
openclaw config validate --json
openclaw doctor --lint --all --json
openclaw gateway restart
openclaw gateway status --require-rpc --timeout 30000
openclaw agents list --bindings
```

## 4. Verify effective tools

At minimum verify:

- intake can read evidence, inspect PDF/images, and register evidence;
- physical can read evidence/model, inspect images, submit physical scope, and lock it;
- validator can read evidence/model, inspect PDF/images, and run validation, but cannot write or lock physical scope;
- technical cannot write physical scope and cannot use Package 14 as technical authority;
- commercial cannot select or lock technical systems;
- output cannot mutate upstream estimate state;
- no agent has Human Release.

Markdown files do not grant authority. Effective permissions are enforced by OpenClaw grants, plugin allow-lists, CLASSIFIRE service-token scopes, and API role checks.

## 5. Workspace file behaviour

- `AGENTS.md` is the complete operational prompt.
- `SOUL.md` shapes behaviour and decision posture.
- `IDENTITY.md` supplies the role identity.
- `TOOLS.md`, `TASK_BOUNDARIES.md`, `WORKFLOWS.md`, and `PROMPTS.md` are role references.
- Do not manually edit `WORKING.md`; Mission Control/OpenClaw may manage it as runtime scratch state.

## 6. Legacy agents

The old `qf-*` QUANTIFIRE agents may still be present during migration. They are not the canonical CLASSIFIRE fleet and must not receive new CLASSIFIRE workflow tasks.
