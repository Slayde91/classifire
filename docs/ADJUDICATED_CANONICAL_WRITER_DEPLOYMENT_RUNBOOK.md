# Admission-Bound Canonical Writer Deployment Runbook

**Status:** Draft, local planning document only
**Applies to:** the controlled initial Physical Model writer introduced for the
adjudicated Phase 8 proposal
**Does not authorise:** database migration, configuration change, key creation,
plugin installation, service restart, admission registration, canonical model
submission, or Physical Model Lock creation

## 1. Purpose

This runbook defines the required deployment and verification gates for the
admission-bound canonical writer. Its purpose is to ensure that a signed,
human-governed admission is the only agent route capable of creating an
initial canonical Opening-Service model.

The deployment boundary is deliberately narrower than the Phase 8 workflow:

- deployment may make the writer available;
- deployment must not submit the current adjudicated proposal;
- deployment must not create a Physical Model Lock;
- a fresh preflight, external signing action, offline admission registration,
  and separate explicit authority remain required before any model write.

## 2. Current verified position

At the time this runbook was prepared:

- the writer, verifier, admission journal schema, and offline registration
  command exist locally with focused local test evidence; stored-payload
  integrity, durable receipt scope, failure-path, and full-regression closure
  remain required before deployment readiness;
- no target production database has been approved or migrated for this feature;
  Gate B must confirm the actual target, its current revision, and the reviewed
  clean-stack migration path before any operational change;
- the plugin source restricts initial submission to
  `cf-adjudicated-physical-writer`, but `package.json` loads a stale
  `dist/index.js` artifact that has not been rebuilt, installed, or verified;
- no pinned public-key configuration, signing action, live admission
  registration, model submission, lock creation, or Gateway operation was
  performed for this work.

The generic agent and human Physical Model Lock routes are intentionally
unavailable while adjudicated mode is enabled. This is a safety control, not a
deployment defect: a signed lock-admission boundary has not yet been designed.

These statements are deployment prerequisites, not evidence that a future
environment has the same state.

## 3. Architecture being deployed

```text
Fresh no-write preflight
        |
        v
External human-governed signer
        |
        v
Signed admission manifest
        |
        v
Offline CLASSIFIRE admission registration
        |
        v
One dedicated agent scope may submit by admission ID
        |
        v
Separate later authority for any Physical Model Lock
```

The signer holds its private key outside CLASSIFIRE. CLASSIFIRE receives only
the signed manifest and deployment-time public-key material.

The required governance process is defined in the
[external signer operating model](./ADJUDICATED_ADMISSION_EXTERNAL_SIGNER_OPERATING_MODEL.md).

## 4. Non-negotiable safety rules

1. Do not start the application against a database requiring migration before
   Alembic has completed successfully. Application startup currently contains
   development convenience table creation, which is not a replacement for
   migration history.
   `classifire init` is not an upgrade procedure for an existing deployment.
2. Do not put a private signing key, signed URL, agent token, database password,
   or `.env` value in the repository, this runbook, a ticket, a terminal
   transcript, or a test fixture.
3. Do not use the generic `physical:write` or `physical:lock` agent scopes for
   the adjudicated initial submission.
4. Do not treat TypeScript source verification as plugin deployment. The
   configured plugin entry point is the compiled `dist/index.js` artifact.
   Do not reuse the legacy `install_classifire_openclaw_plugin.ps1` installer:
   it targets the older read-oriented plugin and `cf-physical-model` role.
5. Do not register or submit a real admission while validating deployment.
   Use synthetic, expired, or deliberately invalid fixtures for negative tests.
6. Do not create a Physical Model Lock in this deployment. A separate signed
   lock-admission design and explicit authority are required.
7. Never use the current report's human adjudication as hidden runtime input to
   a new inference run.

## 5. Required authorities and evidence

| Gate | Required authority | Required evidence | Stop condition |
| --- | --- | --- | --- |
| Deployment planning | Product/security change approval | Reviewed source, test results, backup and recovery plan | Any unresolved source or recovery issue |
| Database migration | Explicit change-window approval | Backup success, migration plan, maintenance/rollback plan | No tested backup or migration result |
| Public-key configuration | Explicit security/configuration approval | Key identifier, issuer-to-key mapping, public key provenance | Any private-key handling inside CLASSIFIRE |
| Plugin installation/restart | Explicit runtime-deployment approval | Built artifact review and plugin boundary checks | Source and `dist` mismatch or stale scopes |
| Real admission registration | Human governance approval | Fresh preflight and external signed manifest | Expired, unbound, or unverifiable manifest |
| Canonical submission | Separate current explicit approval | Registered admission and same-transaction state recheck | Any preflight/fingerprint/state mismatch |
| Physical Model Lock | Separate future explicit approval | Dedicated lock-admission design and technical completeness | Any unresolved material/quantity or lock blocker |

## 6. Controlled deployment sequence

### Gate A - freeze and review the deployment candidate

Before any environment change, record the exact reviewed source revision and
the hashes of the writer, verifier, preflight policy, schema, and plugin
artifact. Confirm that the local test suite covers:

Use the current-main local-only auditor before treating a source tree as a
candidate:

```powershell
python scripts/audit_phase8_admission_deployment_candidate.py --repository-root . --require-clean
```

It reads source files and Git metadata only. It never reads configuration,
contacts a runtime, opens a database, or performs a deployment action. Exit
`2` means a required artifact is missing or the source tree is dirty; in
either case, stop and review the candidate. A zero exit does not authorise a
deployment, admission registration, canonical submission, or lock.

- signature, expiry, issuer-to-key, payload, preflight, fingerprint, and
  implementation-pin rejection;
- generic first-opening and raw agent-write denial when adjudicated mode is
  enabled;
- no model, Service, link, or lock creation during admission registration;
- stale plugin/tool and legacy scope rejection;
- migration installation on a clean temporary database.

Stop if the source tree has unreviewed changes or the intended artifact cannot
be reproduced from the reviewed source.

### Gate B - protect and migrate the database

During an explicitly approved maintenance window:

1. Create and independently verify a recoverable database backup.
2. Confirm the database's current Alembic revision and its target revision.
3. Apply the reviewed Alembic path through the clean-stack lineage-reconciliation
   merge migration (`0007_reconcile_adjudicated_admission_lineages`) and the
   fail-closed empty-legacy-table retirement
   (`0008_retire_legacy_initial_submissions`). The merge migration may
   transition only an empty legacy adjudication journal and must never use
   manual Alembic stamping. Confirm the actual target revision rather than
   assuming this identifier for another deployment.
4. Verify both current admission journal tables, their uniqueness constraints,
   the absence of `physical_model_initial_submissions`, and the recorded Alembic
   revision.
5. Confirm that no admission, initial-submission, Opening, Service, link, or
   Physical Model Lock was created by the migration.

If migration verification fails, stop the change window. Do not use a
destructive downgrade after a journal contains evidence; disable the feature,
restore the approved backup if required, and investigate from preserved logs.

### Gate C - configure the security boundary

With separate approval for security configuration:

1. Enable adjudicated initial submission only after migration verification.
2. Configure a canonical P-256 public key under a stable key identifier.
3. Configure an explicit issuer-to-allowed-key mapping.
4. Confirm that the configuration contains no private key and that the signing
   service is operationally separate from CLASSIFIRE.
5. Provision only `cf-adjudicated-physical-writer` with
   `physical:adjudicated:submit`.
6. Confirm `cf-physical-model` has no physical mutation scope and the writer
   has neither `physical:write` nor `physical:lock`.

The reviewed configuration inputs are JSON objects. Keep the feature disabled
until both maps are present and the real public-key provenance is approved:

```text
CLASSIFIRE_ADJUDICATED_ADMISSION_PUBLIC_KEYS={"governance-p256-01":"<base64url-DER-SPKI-P256-public-key>"}
CLASSIFIRE_ADJUDICATED_ADMISSION_ISSUER_KEY_IDS={"classifire-governance":["governance-p256-01"]}
```

The first map contains only P-256 public keys. The second independently binds
each permitted issuer to its allowed key IDs. CLASSIFIRE rejects an admission
unless both maps explicitly resolve its issuer and key ID.

Stop if the public-key provenance, issuer/key mapping, or least-privilege
scope evidence is incomplete.

### Gate D - build and install the plugin

The plugin must be rebuilt from the reviewed source in an approved deployment
environment. A TypeScript no-emit check is insufficient because OpenClaw loads
the compiled artifact.

Before install or restart, verify that the resulting `dist/index.js`:

- allows `classifire_submit_initial_physical_model` only for
  `cf-adjudicated-physical-writer`;
- accepts only `admission_id` and `idempotency_key` for that tool;
- exposes no agent physical-model-lock tool;
- does not accept Opening or Service payloads;
- matches the reviewed package version and source build output.

After installation, run the controlled-write boundary checks against the
actual loaded plugin. Stop if any legacy agent can see or invoke a physical
mutation tool.

### Gate E - start and test without a real admission

Start the application only after Gates B through D pass. Verify:

- the admission-registration command fails closed when migration, feature,
  public-key mapping, confirmation, or manifest verification is missing;
- invalid, expired, wrong-project, wrong-payload, and wrong-issuer manifests
  create no canonical rows and no lock;
- the generic agent submission route rejects a raw Opening-Service payload;
- the generic human first-Opening route rejects a fresh empty estimate while
  adjudicated mode is enabled;
- the generic Physical Model Lock route is unavailable while adjudicated mode
  is enabled;
- a synthetic valid admission can be registered in a non-production test
  estimate without invoking the writer.

Record request identifiers, safe status codes, journal IDs, and artifact hashes
only. Never record tokens, manifests, signatures, or key material in public
logs.

### Gate F - close deployment without submitting the UAT model

The deployment is ready for the next governance decision only when the above
checks pass and the following remain true for the real UAT estimate:

- zero canonical Openings, Services, links, and active Physical Model Locks;
- no real admission record has been registered;
- no model provider/Gateway request was made for deployment validation;
- all deployment changes, tests, and rollback evidence are retained.

At this point, stop. A fresh preflight and external signing action are separate
operational events, not part of deployment.

## 7. Later operational sequence - not part of deployment

Only after a separately authorised future decision:

1. Produce a fresh, no-write adjudicated canonicalisation preflight against the
   live protected state.
2. Have the independent human-governed signer issue a short-lived manifest
   bound to that exact preflight and payload.
3. Use the offline registration command with an operator/change reference.
4. Obtain a new explicit authorization for the controlled writer to submit by
   registered admission ID.
5. Re-read and independently reconcile the canonical result.

Do not create a Physical Model Lock as part of this sequence.

## 8. Required deployment record

The change record must contain, without secrets:

- deployment source and plugin artifact identifiers;
- Alembic before/after revision and backup/recovery confirmation;
- enabled feature identifier, public key identifier, and issuer-to-key mapping
  identifiers, but never key values;
- agent-role and scope verification result;
- negative boundary-test result summary;
- confirmation that no real UAT admission, model, or lock was created;
- the named approver and approved scope for each stage.

## 9. Completion definition

Deployment is complete only when the runtime uses the reviewed plugin artifact,
the database migration is correctly recorded, all unsafe mutation routes are
blocked in adjudicated mode, and deployment validation leaves the real UAT
estimate unchanged.

Deployment completion does **not** mean Phase 8 is complete, a model has been
submitted, a Physical Model Lock exists, or CLASSIFIRE is production-authorised.
