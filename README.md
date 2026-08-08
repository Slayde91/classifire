# QUANTIFIRE

![QUANTIFIRE estimating system](assets/brand/generated/quantifire-logo-medium.png)

**Passive-fire estimating and technical decision-support system**

QUANTIFIRE is an estimating system produced and developed by Ceasefire PFP.

> **Release status:** pre-production integration build. This repository contains the working application foundation, editable pricing and technical-library services, deterministic calculation and rule engines, branded output renderers, and Mission Control integration scaffolding. It must not be represented as production-authorised until the published release gates and source-parity tests pass.

## What is included

- FastAPI application and server-rendered estimator/admin UI
- Decimal-safe calculation service
- Versioned estimating-rule engine
- Editable product, material, labour and pricing records
- Package 14 pricing importer
- Package 15 technical-variant importer
- Technical-document preservation and draft extraction foundations
- Estimate snapshots and audit records
- Branded PDF and Excel output renderers
- Mission Control integration client and bootstrap command
- Proprietary QUANTIFIRE branding assets

## Local installation

### Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

### macOS or Linux

```bash
chmod +x install.sh
./install.sh
```

The installer creates a virtual environment, installs QUANTIFIRE, copies `.env.example` to `.env` when required, and initialises the local database.

Start the application:

```powershell
# Windows
.\.venv\Scripts\Activate.ps1
quantifire start
```

```bash
# macOS/Linux
source .venv/bin/activate
quantifire start
```

Open `http://127.0.0.1:8787`.

Create an administrator account before operational use:

```bash
quantifire create-admin
```

## Source-library import

Confidential Package 14, Package 15 and calculator source files are not required to be published with the application repository. Place authorised sources in a controlled local path and import them with:

```bash
quantifire import-pricing /path/to/CLASSIFIRE_14_Pricing_Library_v2.13.csv --version 2.13
quantifire import-technical /path/to/CLASSIFIRE_17_Technical_System_Variants_v2.13.jsonl --version 2.13
```

Run a readiness check:

```bash
quantifire doctor
```

## Mission Control

Mission Control is the architecture and operations control plane. QUANTIFIRE remains the canonical system for evidence, estimates, pricing, technical records, calculations, snapshots and outputs.

After configuring `CLASSIFIRE_MISSION_CONTROL_URL` and `CLASSIFIRE_MISSION_CONTROL_API_KEY`:

```bash
quantifire mission-control-bootstrap --repo-url https://github.com/Slayde91/classifire
```

The adapter must be contract-tested against the exact installed Mission Control version before production use.

## Security

- Keep the repository private.
- Do not commit `.env`, API keys, database credentials, customer data, supplier prices, proprietary technical reports or production evidence.
- Use PostgreSQL, TLS, secure secrets management, malware scanning and tested backups for production.
- Technical records extracted by AI remain draft until authorised review and approval.
- A cost allowance is not technical approval.

## Branding

The only approved product logo is `assets/brand/quantifire-logo-master.png`. Do not redraw, recolour, distort or replace it through ordinary content-management functions.

## Licence

Proprietary. See [PROPRIETARY.md](PROPRIETARY.md). No open-source licence is granted.
