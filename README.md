# CLASSIFIRE

<img src="src/classifire/static/brand/classifire-logo.png" alt="CLASSIFIRE estimating system" width="320">

**Passive-fire estimating and technical decision-support system**

CLASSIFIRE is an estimating system produced and developed by Ceasefire PFP.

> **Release status:** pre-production integration build. This repository contains the working application foundation, editable pricing and technical-library services, deterministic calculation and rule engines, branded output renderers, and Mission Control integration scaffolding. It must not be represented as production-authorised until the published release gates and source-parity tests pass.

## Approved direction and next milestone

The current product name is **CLASSIFIRE**; legacy package/asset names remain
where needed for compatibility. Accepted [ADR 0001](docs/ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md)
and [ADR 0002](docs/ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md) define
a shared deterministic core with optional AI and four independent capabilities:
scope analysis, system matching, estimating and reporting.

The working **manual Draft Scope workspace** supports create, edit, validate,
save, reopen and exact JSON download. It now also imports a saved Draft Scope
file through a full preview and explicit replacement confirmation. Imports create
new local revisions, preserve previous revisions and retain unverified source
history; subsequent manual edits and re-imports keep that history visible.
Synthetic browser demonstrations verified both workflows and persistence after
restarting the application. Follow the [local demo guide](docs/DRAFT_SCOPE_DEMO.md)
to try them without using an existing project database or customer evidence.

P0 editing, P1a saved JSON exchange, scope-only PDF/XLSX reporting and saved
technical-candidate review are merged. Retrieval is not technical applicability.
The new **manual Draft Estimate UI** supports explicit AUD unit sell rates,
unknown quantities/rates, preserved originals and reasoned overrides, omit/restore,
partial subtotals and exact historical JSON downloads. Its synthetic browser and
restart checks passed; P3a is merged in PR #192.
The sign-in screen and sidebar now use the owner's supplied CLASSIFIRE logo.

The **estimate-only Draft PDF/XLSX report** increment is merged in PR #193.
The first **PDF evidence review UI** is merged in PR #194, and partial measured-limit
review in PR #195. PDF/workbook intake uses PostgreSQL and a trusted ClamD endpoint;
manual editing still works without scanning or AI. The **pricing XLSX UI**, merged in PR #196,
uploads, scans, maps source columns and explicitly selects a rate for a Draft line,
preserving original/override history and source cells in JSON/PDF/XLSX. Its synthetic
Chrome/restart checks passed; see [the contract](docs/DRAFT_PRICING_XLSX.md) and
PROJECT_STATE.md/current Git for publication and limits. It never approves a technical
system or activates a pricing library. The supplied logo is verified byte-for-byte.

Full Scope analysis, actual applicability, governed pricing and complete
ProjectPackage/ChatGPT access remain unfinished. The current independent
[scope-and-system report screen](docs/DRAFT_SYSTEM_REPORT_CONTRACT.md) captures a
saved review and its embedded Scope without requiring an Estimate. Both outputs
preserve partial/unapproved status and exact historical bytes. It is merged in PR #197. The current
[service-size review](docs/DRAFT_SERVICE_SIZE_REVIEW.md) records measured ranges and
explicit dimension meanings against pinned limits, without implying compatibility.
After publication, next is the complete Draft report profile using saved artifacts.
See the [product goal](GOAL.md), [roadmap](docs/CLASSIFIRE_ROADMAP.md),
[verified state](docs/PROJECT_STATE.md) and [next-session handoff](docs/SESSION_HANDOFF.md).
Complete visible slices before broad refinement; preserve existing authority and
security protections. Agent contributors should read [AGENTS.md](AGENTS.md).

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
- Current CLASSIFIRE UI logo and retained legacy output assets

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
classifire start
```

```bash
# macOS/Linux
source .venv/bin/activate
classifire start
```

Open `http://127.0.0.1:8787`.

Create an administrator account before operational use:

```bash
classifire create-admin
```

## Source-library import

Confidential Package 14, Package 15 and calculator source files are not required to be published with the application repository. Place authorised sources in a controlled local path and import them with:

```bash
classifire import-pricing /path/to/QUANTIFIRE_14_Pricing_Library_v2.13.csv --version 2.13
classifire import-technical /path/to/QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl --version 2.13
```

Run a readiness check:

```bash
classifire doctor
```

## Mission Control

Mission Control is a transitional orchestration/visibility integration. CLASSIFIRE
retains canonical project state and authority. It is not required for the
manual Draft Scope prototype; operational OpenClaw retirement remains parity-gated.

After configuring `CLASSIFIRE_MISSION_CONTROL_URL` and `CLASSIFIRE_MISSION_CONTROL_API_KEY`:

```bash
classifire mission-control-bootstrap --repo-url https://github.com/Slayde91/classifire
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


The Draft candidate screen also supports explicit substrate/gap measured-limit
review with immutable history. See the [synthetic demo and contract](docs/DRAFT_CONSTRAINT_REVIEW.md).
These are partial, unapproved checks; other technical conditions remain unresolved.
