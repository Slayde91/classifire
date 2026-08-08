# CLASSIFIRE controlled rename plan

## Objective

Rename the active product and development project from **QUANTIFIRE** to **CLASSIFIRE** while preserving the integrity of the controlled QUANTIFIRE v2.13 source baseline, immutable hashes, database migration lineage, retained audit records, historical snapshots, and historical output evidence.

New product attribution after cutover:

> CLASSIFIRE is an estimating system produced and developed by Ceasefire PFP.

## Core rule

Do **not** perform an unrestricted repository-wide `QUANTIFIRE -> CLASSIFIRE` replacement.

There are two classes of references:

1. **Active product identity** — rename to CLASSIFIRE.
2. **Historical / controlled provenance** — retain QUANTIFIRE exactly where it identifies the imported v2.13 source release, historical hashes, old schema identifiers, prior snapshots, migration history, audit evidence, or source filenames.

The rename must not change historical evidence merely to make old records display the new product name.

---

## Phase 1 — Rename active runtime identity

Change active product-facing strings:

- application title and description
- active attribution string
- UI headings and navigation labels
- current README and operator documentation
- active output titles and generated filenames
- current workbook/PDF metadata
- health endpoint product name
- log/event descriptions created after cutover
- current Mission Control workspace labels
- current OpenClaw agent display names
- active skill/documentation names

Recommended constants after cutover:

```python
PRODUCT_NAME = "CLASSIFIRE"
ATTRIBUTION = "CLASSIFIRE is an estimating system produced and developed by Ceasefire PFP."
LEGACY_PRODUCT_NAME = "QUANTIFIRE"
LEGACY_BASELINE_VERSION = "v2.13"
```

Do not generate new audit events claiming old QUANTIFIRE records were originally CLASSIFIRE records.

---

## Phase 2 — Rename Python distribution and package

Current:

```text
project distribution: quantifire
Python package:       quantifire
CLI command:          quantifire
source directory:     src/quantifire
```

Target:

```text
project distribution: classifire
Python package:       classifire
CLI command:          classifire
source directory:     src/classifire
```

Required `pyproject.toml` changes:

```toml
[project]
name = "classifire"

[project.scripts]
classifire = "classifire.cli:app"

[tool.setuptools.packages.find]
where = ["src"]
include = ["classifire*"]
```

Update all active imports such as:

```python
from quantifire...
```

to:

```python
from classifire...
```

This includes tests, scripts, installer checks and runtime launchers.

### Temporary compatibility option

For one transition release, an optional `quantifire` compatibility shim may re-export `classifire` so local scripts do not fail immediately. Remove the shim after all integrations are migrated.

---

## Phase 3 — Windows workspace rename

Current workspace:

```text
C:\QUANTIFIRE
```

Target:

```text
C:\CLASSIFIRE
```

Do this only after the current branch is committed and clean.

From a PowerShell window outside the repository:

```powershell
Set-Location C:\
Rename-Item -Path "C:\QUANTIFIRE" -NewName "CLASSIFIRE"
Set-Location "C:\CLASSIFIRE"
```

### Recreate the virtual environment

Do **not** keep the old `.venv` after moving/renaming the workspace. Windows virtual-environment launchers contain absolute paths.

```powershell
Remove-Item -Recurse -Force .\.venv
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Verify:

```powershell
python -c "import classifire; print(classifire.__version__)"
classifire --help
python -m pytest -q
```

---

## Phase 4 — Environment/config rename

Current settings prefix:

```text
QUANTIFIRE_
```

Target prefix:

```text
CLASSIFIRE_
```

Examples:

```text
CLASSIFIRE_SECRET_KEY
CLASSIFIRE_DATABASE_URL
CLASSIFIRE_SESSION_HTTPS_ONLY
CLASSIFIRE_MISSION_CONTROL_URL
CLASSIFIRE_MISSION_CONTROL_API_KEY
CLASSIFIRE_OPENCLAW_CONFIG_PATH
CLASSIFIRE_OPENCLAW_STATE_DIR
```

During one transition release, support old `QUANTIFIRE_*` variables as deprecated aliases if operational continuity is required. New documentation and deployment manifests must use only `CLASSIFIRE_*`.

Update `.env.example` and the local `.env` deliberately. Never commit secrets.

---

## Phase 5 — Local database filename

Current default:

```text
data/quantifire.db
```

Target:

```text
data/classifire.db
```

This is a file rename, not a schema reset.

Before changing it:

```powershell
Copy-Item .\data\quantifire.db .\data\quantifire-pre-classifire-backup.db
Rename-Item .\data\quantifire.db classifire.db
```

Then update the default connection string to:

```text
sqlite:///./data/classifire.db
```

Run:

```powershell
alembic current
python -m pytest -q
```

Do **not** recreate the production database merely because the product was renamed.

---

## Phase 6 — GitHub repository rename

Current repository:

```text
Slayde91/quantifire
```

Target:

```text
Slayde91/classifire
```

In GitHub:

1. Open the private repository.
2. Open **Settings**.
3. Under **General**, change **Repository name** from `quantifire` to `classifire`.
4. Confirm the rename.

Then update the local remote explicitly even if GitHub redirects the old URL:

```powershell
git remote set-url origin https://github.com/Slayde91/classifire.git
git remote -v
git fetch origin
```

Update Mission Control and any deployment scripts that refer to the old repository URL.

Do not rename the repository until all required external integrations are ready to receive the new URL.

---

## Phase 7 — Branding and output files

Rename active branding assets only after an approved CLASSIFIRE logo exists.

Target examples:

```text
assets/brand/classifire-logo-master.png
src/classifire/static/brand/classifire-logo-master.png
```

Generated output filenames should become:

```text
CLASSIFIRE_<estimate>_Technical_Estimate.xlsx
CLASSIFIRE_<estimate>_Proposal.xlsx
CLASSIFIRE_<estimate>_Technical_Estimate.pdf
CLASSIFIRE_<estimate>_Proposal.pdf
```

Workbook/PDF titles and metadata should identify CLASSIFIRE.

Historical QUANTIFIRE output files must not be renamed in place if they are retained audit evidence. New CLASSIFIRE outputs should be regenerated from valid CLASSIFIRE snapshots.

---

## Phase 8 — OpenClaw and Mission Control

Current development agent identifiers may use the `qf-` prefix. The recommended CLASSIFIRE equivalents are:

```text
cf-orchestrator
cf-intake-evidence
cf-physical-model
cf-technical-system
cf-commercial-engine
cf-validator
cf-output
cf-library-governance
cf-platform-governance
```

Recommended root:

```text
C:\CLASSIFIRE-OpenClaw
```

Mission Control should be updated to:

- product/workspace name: CLASSIFIRE
- repository: `Slayde91/classifire`
- agent names: `cf-*`
- task/workflow names: CLASSIFIRE terminology

Do not overwrite historical Mission Control task/event records solely to make them display CLASSIFIRE. Retain old QUANTIFIRE records as historical records.

---

## Phase 9 — Internal protocol/schema identifiers

Do not blindly rename existing values such as:

```text
QUANTIFIRE-PhysicalModelLock-v2.13
QUANTIFIRE-RepairStrategyLock-v2.13
QUANTIFIRE-QUANTITY-ENGINE-v1.0
QUANTIFIRE-COMMERCIAL-ENGINE-v1.0
QUANTIFIRE-ESTIMATE-SNAPSHOT-v2.13
```

Those identifiers may already be inside content hashes, retained locks, snapshots, gate evidence, tests or certificates.

Preferred migration strategy:

- preserve old identifiers as the **legacy QUANTIFIRE v2.13 protocol**;
- introduce new CLASSIFIRE protocol identifiers in a controlled new release;
- provide explicit backwards-reading compatibility;
- never rewrite an old signed/hashed payload merely to change its name.

Example future identifier:

```text
CLASSIFIRE-ESTIMATE-SNAPSHOT-v1.0
```

with lineage metadata such as:

```json
{
  "product": "CLASSIFIRE",
  "baseline_lineage": "QUANTIFIRE v2.13"
}
```

---

## Files/data that must remain historically unchanged

Unless a separate migration proves otherwise, retain QUANTIFIRE wording inside:

- controlled v2.13 source packages
- Package 13 source routing evidence tied to source hashes
- source inventory/hash registers
- schema acceptance receipts that describe the QUANTIFIRE v2.13 intake
- historical audit events
- already-created lock payloads and content hashes
- historical GateEvidence records
- historical EstimateCertificate records
- historical snapshot payloads
- migration revision identifiers already applied to databases
- source filenames referenced by immutable manifests
- archived proposals/workbooks/PDFs that are retained evidence

The new CLASSIFIRE product may reference these as its legacy QUANTIFIRE v2.13 baseline.

---

## Database migrations

Do not rename existing Alembic revision IDs such as `0003` or `0004`.

If the CLASSIFIRE cutover later requires schema changes, add a **new migration**. Never edit already-applied migration history just to remove the old product name.

---

## Recommended implementation order

1. Complete and pass the current QUANTIFIRE feature branch regression suite.
2. Tag or record the final pre-rename QUANTIFIRE baseline commit.
3. Create a dedicated `feature/classifire-rename` branch from that commit.
4. Rename runtime branding/constants and tests.
5. Rename Python package/distribution/CLI.
6. Rename env prefix and default DB filename with compatibility handling.
7. Add CLASSIFIRE branding assets.
8. Rename OpenClaw/Mission Control active configuration.
9. Run full tests and an end-to-end estimate regression.
10. Rename GitHub repository.
11. Rename local workspace and recreate `.venv`.
12. Update deployment/install commands and integration URLs.
13. Preserve the old QUANTIFIRE release as an immutable lineage reference.
14. Only then merge/cut the first CLASSIFIRE release.

---

## Acceptance checks

The rename is complete only when all of the following pass:

```text
[ ] no active UI says QUANTIFIRE
[ ] current generated filenames say CLASSIFIRE
[ ] Python import is classifire
[ ] CLI command is classifire
[ ] package/distribution is classifire
[ ] active env variables use CLASSIFIRE_
[ ] default SQLite filename is classifire.db
[ ] GitHub repository is Slayde91/classifire
[ ] local workspace is C:\CLASSIFIRE
[ ] active OpenClaw/Mission Control identity uses CLASSIFIRE
[ ] current README/operator docs use CLASSIFIRE
[ ] approved CLASSIFIRE logo is used
[ ] historical QUANTIFIRE v2.13 hashes still verify
[ ] old database migrations remain valid
[ ] historical snapshots/certificates still verify
[ ] full regression suite passes
[ ] end-to-end CLASSIFIRE output passes independent validation
```

## Cutover principle

The rename is a new product identity over a controlled legacy baseline, not a rewriting of history.
