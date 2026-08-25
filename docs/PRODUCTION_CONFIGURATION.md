# CLASSIFIRE Production Configuration and Bootstrap

**Status:** Phase 15 branch candidate; not deployed or production-authorised

This runbook defines the minimum application-configuration and initial
administrator boundary. It does not replace environment-specific security,
database, backup, monitoring, recovery, or release approval.

## Do not use the development example in production

`.env.example` is a loopback SQLite configuration for local development. Its
secret and network values are public placeholders. Copying that file does not
create a production configuration.

Production must provide all of the following through the approved secret and
configuration system:

- `CLASSIFIRE_ENV=production`;
- `CLASSIFIRE_DATABASE_URL` for the governed PostgreSQL database using the
  declared `postgresql+psycopg://` driver, with its credential kept outside
  source control and operator output;
- a strong, unique `CLASSIFIRE_SECRET_KEY` generated and retained by the
  approved secret manager, never copied from documentation or another
  environment;
- `CLASSIFIRE_SESSION_HTTPS_ONLY=true` behind end-to-end reviewed HTTPS;
- `CLASSIFIRE_TRUSTED_HOSTS` containing only the exact host names that may serve
  CLASSIFIRE; and
- `CLASSIFIRE_ALLOWED_ORIGINS` containing only the exact HTTPS origins that may
  make browser cross-origin requests.

Install the declared production database driver in the application environment:

```bash
python -m pip install --no-build-isolation -e ".[postgres]"
```

Trusted hosts must be host names or IPv4 addresses, not URLs. Do not include `*`, wildcard host
patterns, schemes, ports, paths, queries, or fragments. Browser origins must
use lowercase `https://` and lowercase host names. Omit the default `:443`;
only a non-default explicit port is accepted. Origins must not include
wildcards, credentials, paths, queries, or fragments. Each origin host must
also be an allowed trusted host. IPv6 trusted hosts are not supported by this
runtime boundary.

`CLASSIFIRE_HOST` controls the server bind address; it does not grant browser or
Host-header trust. A public bind address is therefore not a substitute for the
exact trusted-host and allowed-origin lists.

Production startup and database-writing commands must stop before changing the
database or storage when these requirements are not satisfied. Do not weaken a
check to force a deployment to continue.

## Initial administrator boundary

CLASSIFIRE has no default administrator email or password. The installer must
not seed one. The first account is an explicit, attributable operator action:

```bash
classifire create-admin --operator-reference "initial-admin-provisioning"
```

The command prompts for the email and password. Use a unique administrator
identity and a password delivered through the organisation's approved access
process. Do not place either value in `.env`, shell history, an installer,
source control, logs, tickets, or this runbook.

The operator reference must identify the approved provisioning action. It must
not contain a password, secret, token, or other credential.

## Reviewed bootstrap order

Before these commands, provision the governed PostgreSQL service, apply the
reviewed Alembic migrations to the exact required revision, configure TLS and
the mandatory settings above, and establish backup and recovery controls.

Run the application steps in this order:

```bash
classifire create-admin --email "admin@your-company.example" --operator-reference "initial-admin-provisioning"
classifire init --administrator-email "admin@your-company.example" --operator-reference "initial-database-bootstrap"
classifire doctor
classifire start
```

Replace the example email and use the same authorised identity for both
commands. The security boundary is `create-admin` before `init`, and `init`
before `start`. `init` seeds baseline application records using that explicitly
selected active administrator and retains the separate operator/change
reference as audit evidence; it must not invent or silently choose an account.
`doctor` is a read-only readiness check between initialisation and startup. A
failed command stops the sequence. Do not continue as if it succeeded.

The startup bootstrap check proves only that an active administrator exists and
that an explicit `init` audit marker was committed. It does not prove that
current technical, commercial, rule, rate, or library records are complete,
unchanged, approved, or suitable.

## Existing database rollout gate

A database initialized by an older build does not contain this branch's
explicit initialization audit marker. Production `doctor`, `start`, and
workers therefore remain blocked after an upgrade until that history is
governed.

Do not run the new `init` command merely to manufacture a marker over
historical rows. It refuses existing baseline artifacts with
`legacy_baseline_adoption_required`. A separately reviewed adoption/backfill
procedure must validate the retained baseline identities and lineage, preserve
the evidence of what was created versus reused, and receive current migration
and rollout authority. This branch does not implement or authorise that
adoption.

For an existing deployment, do not rerun `create-admin` casually: targeting an
existing email intentionally resets and reactivates that account and revokes
its prior human sessions. Use the reviewed migration and account-governance
procedure appropriate to that deployment.

## Evidence and authority

Retain secret-free evidence of the configuration review, exact application and
migration revisions, authorised operator reference, command outcomes, database
backup/recovery checks, and final readiness decision.

Passing application configuration checks proves only that this bounded set of
unsafe defaults is absent. It does not prove infrastructure security,
production readiness, technical approval, canonical-write authority, a
Physical Model Lock, deployment approval, or release approval.
