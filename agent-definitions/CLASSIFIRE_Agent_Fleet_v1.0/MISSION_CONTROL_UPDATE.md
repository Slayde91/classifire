# Updating all CLASSIFIRE agents in Mission Control

Mission Control is the task and review control plane. CLASSIFIRE remains the canonical estimate system.

## Prerequisites

1. Mission Control is running at `http://127.0.0.1:3000`.
2. OpenClaw Gateway is running.
3. The nine `cf-*` OpenClaw agents already exist.
4. The Mission Control API key is stored in `C:\CLASSIFIRE\.env` as `CLASSIFIRE_MISSION_CONTROL_API_KEY`.
5. This package has been copied into the OpenClaw workspaces.

## Step 1 — register or refresh the agent roster

```powershell
Set-Location "C:\CLASSIFIRE"
.\scripts\configure_classifire_mission_control.ps1
classifire mission-control-bootstrap --repo-url https://github.com/Slayde91/classifire
```

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

Use `Update-CLASSIFIRE-MissionControlAgents.ps1` from this package:

```powershell
.\Update-CLASSIFIRE-MissionControlAgents.ps1 `
  -SourceRoot "C:\CLASSIFIRE\agent-definitions\CLASSIFIRE_Agent_Fleet_v1.0" `
  -MissionControlUrl "http://127.0.0.1:3000" `
  -RepoEnvFile "C:\CLASSIFIRE\.env"
```

The script:

- finds each agent by exact `cf-*` name;
- uploads the complete `SOUL.md`;
- preserves any existing dispatch-model setting;
- sets `openclawId`, framework, capabilities, and definition version;
- does not create new agent names;
- does not modify CLASSIFIRE canonical state.

## Step 4 — verify in the Mission Control UI

For each agent:

1. Open **Agents**.
2. Confirm the exact `cf-*` name.
3. Confirm the role and OpenClaw ID.
4. Open the **SOUL** tab and confirm the full role-specific content.
5. Confirm capabilities match `FLEET_MANIFEST.json`.
6. Confirm status is idle/offline as expected.
7. Do not edit `WORKING.md` manually.

## Step 5 — create the visual physical-model workflow tasks

For every defect, use four tasks:

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

### Task D — Admission-bound initial canonical submission
- Assigned to: `cf-physical-model`
- Preconditions: Task C APPROVED plus a separately authorised, pre-existing
  signed admission
- Output: canonical IDs, submission receipt, content hash, critical unknowns
- The Phase 8 admission-only profile stops here and must not create a Physical
  Model Lock

### Task E — Physical Model Lock (inactive and deferred)
- Assigned to: no active Phase 8 tool
- Preconditions: resolved material and quantity evidence, a reviewed lock
  admission boundary, and separate current authority
- Output: Physical Model Lock and preserved critical unknowns

Do not dispatch the technical-system task until Task E has a valid lock and the
visual validator approval receipt is retained.

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
