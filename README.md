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

## Technical report intake

> **Feature-branch status (28 August 2026):** the implementation was pushed at
> commit `d76562e54a7f208c2cab8ea1e9f598065f8e5151` on
> `origin/gpt/technical-intake-draft-boundary-20260827`. It remains a
> pre-production branch candidate, not merged, deployed, migrated into an
> environment, used to ingest a supplied report, approved, or released. See
> [the current project state](docs/PROJECT_STATE.md) for validation results and
> the remaining operational UAT.

Authorised users can upload multiple technical reports from the Technical Library UI.
Each upload is malware-screened, retained as immutable hashed evidence and registered as
a separate Draft source. Optional typed links record revisions, assessments, amendments,
replacements and retirement notices without overwriting either report.

Exact clean duplicate bytes share one verified StoredFile while each
TechnicalDocument keeps its own identity and audit history. If any later
scanner-bound upload or replay detects malware for those exact bytes,
CLASSIFIRE quarantines that shared file identity,
moves every previously accepted linked intake item and affected batch to
`needs_attention`, and blocks every referencing document from clean-file
workflows. It does not erase the retained evidence or silently trust a second
copy.

From a retained source page, a user with technical write permission can start or
resume an owner-bound **field-level intake Draft**. The workspace saves raw and
normalised values, uncertainty, limitations, exact source locators, and
many-to-many evidence roles against the immutable source identity. Saving or
resuming this Draft creates no TechnicalVariant, Approval, release, or runtime
authority. See the
[Technical Intake Draft v1 contract](docs/TECHNICAL_INTAKE_DRAFT_V1.md).

The ordinary UI no longer offers the legacy coarse **Create Draft
configuration** path. That direct compatibility route remains for historical
records, but variants created through its UI intake policy cannot be submitted
for review. Reviewer-owned configuration-family materialisation remains future
work.

In development and controlled test environments, immutable PDF sources can optionally be
reviewed page by page as bounded, re-encoded PNG images by setting
`CLASSIFIRE_TECHNICAL_PDF_PREVIEW_ENABLED=true`.
Each request rechecks the clean retained file, exact size and SHA-256, then passes the
same verified descriptor to a fixed parser subprocess. The browser never embeds the raw
PDF, and previewing cannot change source status, approve extracted data or publish
runtime authority. The original remains an attachment-only download.

The controlled preview worker has a wall-time limit, hard-bounded parent output,
page/pixel/output caps, a per-process concurrency cap and a filtered environment; POSIX
workers also apply available process resource limits. Production preview is forcibly
disabled because this subprocess is not an operating-system security sandbox. Before
production enablement, arbitrary-report rendering must move behind an enforced
low-privilege OS/container boundary with hard memory/CPU limits, no application secrets,
no database authority and no outbound network. This is particularly important on Windows,
where Python does not provide POSIX resource limits.

A Draft or Rejected source must be submitted for review. A different authorised person,
who is also not the report uploader, must approve the exact file and outgoing lineage
snapshot. The request reason, decision reason, identities and snapshot hash remain in the
review history. An independent reviewer can instead request changes, returning the source
to Draft without granting authority so missing lineage can be added before resubmission.
Source approval does not approve extracted variants or make anything runtime-active.
New technical reviews and publications use the v3 Technical Authority Registry policy,
which binds the exact independent source-review receipt and typed outgoing lineage.
Previously published v2 manifests, hashes and estimate pins remain unchanged. A v3
release may carry an exact v2 record forward only from its explicit predecessor; new or
altered records must be reviewed under v3. Pre-governance manifests are historical
evidence only and cannot provide runtime selection or estimate-pinning authority.

An active technical record can only be withdrawn through a governed retirement request.
The requester, independent decision-maker and release publisher must be separate people.
Requesting or approving retirement does not change runtime search; the record remains
active until the exact receipt is published in the next Technical Authority Registry
release. That transaction retires the record and replaces the registry atomically. If the
last member is withdrawn, the signed successor is an explicit empty registry. Historical
release details remain auditable, while estimates pinned to a now-withdrawn member fail
closed rather than silently using withdrawn authority.

## Source-library import

Confidential Package 14, Package 15 and calculator source files are not required to be published with the application repository. Place authorised sources in a controlled local path and import them with:

```bash
classifire import-pricing /path/to/QUANTIFIRE_14_Pricing_Library_v2.13.csv --version 2.13
classifire import-technical /path/to/QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl --version 2.13
```

Technical import is an intake step, not approval. Every imported variant and its
source batch remain Draft and excluded from normal technical search. Source
status, eligibility and effective-date fields are retained as provenance only.
An authorised review and a separately published technical release are required
before runtime use.

Run a readiness check:

```bash
classifire doctor
```

## Mission Control

Mission Control is the architecture and operations control plane. QUANTIFIRE remains the canonical system for evidence, estimates, pricing, technical records, calculations, snapshots and outputs.

After configuring `CLASSIFIRE_MISSION_CONTROL_URL` and `CLASSIFIRE_MISSION_CONTROL_API_KEY`:

```bash
classifire mission-control-bootstrap --repo-url https://github.com/Slayde91/classifire
```

The adapter must be contract-tested against the exact installed Mission Control version before production use.

## Security

- Keep the repository private.
- Do not commit `.env`, API keys, database credentials, customer data, supplier prices, proprietary technical reports or production evidence.
- Use PostgreSQL, TLS, secure secrets management, malware scanning and tested backups for production.
- Install the production database and scanner drivers with
  `pip install "classifire[postgres,malware]"`. Configure `CLASSIFIRE_CLAMAV_HOST`,
  `CLASSIFIRE_CLAMAV_PORT`, `CLASSIFIRE_CLAMAV_STREAM_MAX_MB` and the upload limits
  before accepting evidence uploads. Uploads fail closed if the scanner is missing,
  unavailable, times out or returns anything except an exact clean result bound to the
  uploaded bytes.
- `CLASSIFIRE_MAX_UPLOAD_MB` controls new upload admission.
  `CLASSIFIRE_UPLOAD_INGRESS_CEILING_MB` is the bounded outer request ceiling used to
  keep files from earlier batch manifests uploadable after the admission limit is
  lowered. If it is omitted, it equals `CLASSIFIRE_MAX_UPLOAD_MB`. Never lower it below
  the largest declared size retained in any technical-intake batch; production readiness
  checks every persisted item, including terminal items, and refuses startup if an
  admitted manifest would be stranded.
- Keep the ClamAV TCP endpoint on loopback or a trusted private sidecar network. Its
  protocol is not encrypted or authenticated. Its real `StreamMaxLength` and the
  declared `CLASSIFIRE_CLAMAV_STREAM_MAX_MB` must both be at least
  the effective `CLASSIFIRE_UPLOAD_INGRESS_CEILING_MB`.
- Set the reverse proxy request-body cap to at least the effective ingress ceiling plus
  1 MiB for bounded multipart framing. The proxy ceiling is only a transport allowance;
  CLASSIFIRE's authenticated route checks still decide whether a particular request may
  use the historical capacity.
- Technical records extracted by AI remain draft until authorised review and approval.
- A cost allowance is not technical approval.

### Production startup gate

Production startup is fail closed. CLASSIFIRE does not create tables, run migrations,
seed defaults or create an administrator when the web process starts. Before starting a
production process, operators must:

1. install `classifire[postgres,malware]`, provide a PostgreSQL database and an absolute,
   pre-created storage root;
2. configure a strong secret, secure session cookies, explicit trusted hosts, exact HTTPS
   browser origins, a 1-1024 MB new-admission limit, a 1-1024 MB ingress ceiling that
   covers every persisted batch manifest, and a non-default administration password;
3. configure a reachable ClamAV service and reverse proxy whose limits cover that ingress
   ceiling plus the proxy's multipart allowance;
4. run `classifire migrate` to apply the migration graph shipped in the installed build;
5. create the first account explicitly with `classifire create-admin`; and
6. run `classifire doctor`, then `classifire start` only after every readiness code passes.

`classifire init` is local-development bootstrap only and is refused in production.
Production import and administrator commands never call SQLAlchemy table creation; the
database must already be at the exact shipped Alembic head.

`GET /healthz` is a dependency-free liveness check: HTTP 200 means only that the process
can answer. `GET /readyz` checks configuration, database connectivity and the full model
schema at the exact migration head, the ingress ceiling against every persisted technical
batch manifest, an active administrator, the real staging/hash-folder storage and hard-link
path, live ClamAV `PONG`, and an exact clean verdict for a fixed harmless stream. It
returns HTTP 200 only when ready, otherwise HTTP 503 with stable codes and no database URL,
storage path, scanner host, secret, admitted file size or raw exception text. HTTP clients
are told not to cache the response; the server coalesces concurrent deep probes for at most
five seconds to protect the database, scanner and storage. Restrict `/readyz` at the proxy
or network layer to trusted deployment-health infrastructure.

`GET /api/v1/health` remains temporarily available as the deprecated legacy diagnostic
contract for existing monitors. It is not a deployment-readiness signal; new monitoring
must use `/healthz` and `/readyz`.

## Branding

The only approved product logo is `assets/brand/quantifire-logo-master.png`. Do not redraw, recolour, distort or replace it through ordinary content-management functions.

## Licence

Proprietary. See [PROPRIETARY.md](PROPRIETARY.md). No open-source licence is granted.
