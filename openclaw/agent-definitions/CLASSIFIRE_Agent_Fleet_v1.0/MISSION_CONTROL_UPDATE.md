# Updating all CLASSIFIRE agents in Mission Control

Mission Control is the task and review control plane. CLASSIFIRE remains the canonical estimate system.

## Prerequisites

1. Mission Control is running at `http://127.0.0.1:3000`.
2. OpenClaw Gateway is running.
3. The nine `cf-*` OpenClaw agents already exist.
4. The Mission Control API key is stored in `C:\CLASSIFIRE\.env` as `CLASSIFIRE_MISSION_CONTROL_API_KEY`.
5. The canonical fleet exists at `C:\CLASSIFIRE\openclaw\agent-definitions\CLASSIFIRE_Agent_Fleet_v1.0`.

## Step 1 — register or refresh the CLASSIFIRE roster

```powershell
Set-Location "C:\CLASSIFIRE"
.\scripts\configure_classifire_mission_control.ps1
classifire mission-control-bootstrap --repo-url https://github.com/Slayde91/classifire
```

The CLASSIFIRE bootstrap reconciles existing Mission Control agents by `config.openclawId` before considering names. It must not create a second record merely because Mission Control displays the OpenClaw identity name instead of the `cf-*` ID.

## Step 2 — sync OpenClaw agents into Mission Control

```powershell
$envFile = "C:\CLASSIFIRE\.env"
$mcUrl = "http://127.0.0.1:3000"
$keyLine = Get-Content $envFile | Where-Object { $_ -like "CLASSIFIRE_MISSION_CONTROL_API_KEY=*" } | Select-Object -First 1
$key = $keyLine.Substring($keyLine.IndexOf("=") + 1)

$headers = @{
    Authorization = "Bearer $key"
    "x-api-key" = $key
    "Content-Type" = "application/json"
}

Invoke-RestMethod `
    -Method Post `
    -Uri "$mcUrl/api/agents/sync" `
    -Headers $headers `
    -Body '{"source":"config"}'
```

## Step 3 — update SOUL and agent configuration

Run the updater from the canonical repository-controlled fleet:

```powershell
Set-Location "C:\CLASSIFIRE"

.\openclaw\agent-definitions\CLASSIFIRE_Agent_Fleet_v1.0\Update-CLASSIFIRE-MissionControlAgents.ps1 `
  -MissionControlUrl "http://127.0.0.1:3000" `
  -RepoEnvFile "C:\CLASSIFIRE\.env"
```

The script:

- resolves each Mission Control record by `config.openclawId` first, with canonical-name fallback only when necessary;
- fails closed if more than one record claims the same `openclawId`;
- preserves the Mission Control display name instead of renaming synced agents;
- updates the complete `SOUL.md`, role and CLASSIFIRE metadata through the normal `PUT /api/agents` route;
- preserves unrelated existing Mission Control config, including dispatch/model settings;
- sets `openclawId`, framework, capabilities, definition version and visual-workflow version;
- creates no Mission Control agents;
- verifies all nine agents after the update;
- does not modify canonical CLASSIFIRE estimate state.

## Step 4 — verify in the Mission Control UI

For each CLASSIFIRE agent:

1. Open **Agents**.
2. Confirm the displayed identity is the expected CLASSIFIRE identity.
3. Confirm `config.openclawId` is the corresponding stable `cf-*` ID.
4. Confirm the role matches `FLEET_MANIFEST.json`.
5. Open the **SOUL** tab and confirm the full role-specific content.
6. Confirm capabilities match `FLEET_MANIFEST.json`.
7. Confirm `classifireAgentDefinitionVersion` is `1.0`.
8. Do not edit `WORKING.md` manually.

Legacy `qf-*` agents and any historical duplicate Mission Control records are not canonical CLASSIFIRE agents. Do not assign new CLASSIFIRE tasks to them.

## Step 5 — visual physical-model workflow tasks

For every defect, use four governed passes:

### Task A — Evidence and photo reconciliation
- Assigned to: `cf-intake-evidence`
- Inputs: defect ID, report page, actual native/zoom images
- Output: retained evidence and view-reconciliation receipt

### Task B — Barrier-first draft topology
- Assigned to: `cf-physical-model`
- Inputs: actual images plus Task A receipt
- Output: non-canonical draft Barrier → Opening → Service → Relationship model

### Task C — Independent visual validation
- Assigned to: `cf-validator`
- Inputs: the same actual images plus Task B draft
- Output: APPROVED, REJECTED, or BLOCKED with issue codes
- No physical write permission

### Task D — Canonical physical write and lock
- Assigned to: `cf-physical-model`
- Preconditions: Task C APPROVED
- Output: canonical IDs, Physical Model Lock, content hash, critical unknowns

Do not dispatch the technical-system task until Task D has a valid Physical Model Lock and the visual-validator approval receipt is retained.

## Step 6 — quality-review policy

Mission Control task status is not a CLASSIFIRE gate. A task may move to `done`, but the orchestrator advances only when the matching canonical CLASSIFIRE receipt exists.

Recommended review outcomes:

```text
VERDICT: APPROVED
NOTES: <evidence-backed summary>

VERDICT: REJECTED
ISSUES: <structured issue codes>
REQUIRED_ACTION: <bounded correction>

VERDICT: BLOCKED
MISSING: <specific evidence or human decision>
```
