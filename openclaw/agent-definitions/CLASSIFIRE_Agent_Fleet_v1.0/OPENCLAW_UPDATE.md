# Updating the OpenClaw CLASSIFIRE agents

## 1. Create or refresh the existing agents

Run the repository's existing setup first because it creates workspaces and identities:

```powershell
Set-Location "C:\CLASSIFIRE"
.\scripts\setup_classifire_openclaw.ps1
```

## 2. Copy this markdown package into the workspaces

Assuming this package is extracted to `C:\CLASSIFIRE\agent-definitions\CLASSIFIRE_Agent_Fleet_v1.0`:

```powershell
$SourceRoot = "C:\CLASSIFIRE\agent-definitions\CLASSIFIRE_Agent_Fleet_v1.0\agents"
$WorkspaceRoot = "C:\CLASSIFIRE-OpenClaw"

Get-ChildItem -LiteralPath $SourceRoot -Directory | ForEach-Object {
    $target = Join-Path $WorkspaceRoot $_.Name
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -LiteralPath (Join-Path $_.FullName "*.md") -Destination $target -Force
}
```

Do this **after** `setup_classifire_openclaw.ps1`; the old setup script otherwise rewrites its shorter workspace files.

## 3. Apply role-limited plugins

```powershell
.\scripts\install_classifire_openclaw_plugin.ps1
.\scripts\install_classifire_controlled_write_plugin.ps1
```

The repository still needs the validator visual-read grant described in `TOOL_GRANT_MATRIX.md` before the full visual review workflow is enabled.

## 4. Validate OpenClaw

```powershell
openclaw config validate --json
openclaw doctor --lint --json
openclaw gateway restart
openclaw gateway status --require-rpc --timeout 30000
openclaw agents list --bindings
```

## 5. Verify effective tools

Create one test session for each agent and inspect `tools.effective`. At minimum verify:

- intake can read evidence, PDF/images, and register evidence;
- physical can read evidence/model, inspect images, write physical scope, and lock it;
- validator can read evidence/model and inspect images, but cannot write physical scope;
- technical cannot read confidential pricing or write physical scope;
- commercial cannot select technical systems;
- no agent has Human Release.

## 6. Workspace file behaviour

- `AGENTS.md` is the complete operational prompt.
- `SOUL.md` shapes behaviour and decision posture.
- `IDENTITY.md` supplies the role identity.
- `TOOLS.md`, `TASK_BOUNDARIES.md`, `WORKFLOWS.md`, and `PROMPTS.md` are role references.
- Do not manually edit `WORKING.md`; Mission Control/OpenClaw may manage it as runtime scratch state.
