# CLASSIFIRE Project State and Development Handoff

**Verified snapshot:** 2026-08-22 (AEST)
**Repository:** `C:\CLASSIFIRE`
**Branch:** `gpt/phase8-linked-original-images`
**HEAD:** `1b4b327 refactor: consolidate shared file hashing helper`
**Purpose:** factual handoff for the next development session. This document is
not authority to commit, push, publish, migrate a live database, register an
admission, submit a canonical model, or create a Physical Model Lock.

## 1. Read first

This checkout is deliberately not clean. At this snapshot, `git status` showed
48 tracked modifications and 86 untracked paths. The tree contains active Phase
8/UAT, admission-bound writer, migration-lineage, deployment, and documentation
work. Preserve it and stage only explicit reviewed paths. In particular:

- never use `git add .`;
- do not reset, discard, or overwrite unrelated work;
- preserve untracked `agent-definitions/` and `classifire logo.png`;
- do not treat generated-looking UAT, migration, or runtime material as safe to
  delete without a separate evidence-based review.

The priority order for a new session is:

1. executable code, current database schema, focused tests, and retained
   receipts;
2. this handoff;
3. the roadmap, architecture, and operating runbooks;
4. older summaries and conversation context.

## 2. Current repository position

The five verified repository-cleanup commits are the current branch tip:

| Commit | Scope |
| --- | --- |
| `93487d4` | ignore local Python review caches |
| `8c93578` | clarify developer setup and historical rename guidance |
| `017799d` | remove unused `python-dateutil` dependency |
| `6a30626` | remove verified unused imports |
| `1b4b327` | consolidate the shared file-hashing helper |

They are followed in the working tree by uncommitted work. Do not imply that
the admission compatibility repair, the current roadmap/architecture updates,
or the UAT/runtime work has been committed, pushed, reviewed, or deployed.

Relevant uncommitted work includes:

- tracked modifications to the Phase 8 runners, controlled-write plugin,
  security/API/UI/configuration paths, roadmap, architecture, and related
  tests;
- untracked admission, preflight, canonical-submission, and protected-state
  services/tests;
- untracked migration definitions `0003` through `0007` and admission package
  scripts;
- retained UAT, rehearsal, change-window, report, and local tooling material.

## 3. Verified Phase 8 physical-model position

The current real-UAT proposal remains provisional and non-canonical. The
current implementation-bound no-write preflight receipt is:

`data/real-uat/20260822-phase8-admission-preflight-147042-v5/24-adjudicated-canonicalisation-preflight.json`

It was inspected in this snapshot and reports:

| Item | Verified value |
| --- | --- |
| Schema | `CLASSIFIRE-ADJUDICATED-CANONICALISATION-PREFLIGHT-v2` |
| Status | `PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED` |
| Candidate eligible | `true` |
| Canonical/database/gateway writes | all `false` |
| Openings in normalised payload | 17 |
| Services in normalised payload | 24 |
| Source run | `20260821-phase8-proposal-only-retry-7` |
| Adjudicated run | `20260821-phase8-proposal-only-retry-7-adjudicated-v1` |
| Protected-state fingerprint | `A1FFA7501C13481D01E3A7BE00ABC3CC940968DAD72037531D07A68DE70FAFD9` |

The earlier v3 preflight is no longer usable by the current writer because its
implementation hashes predate the admission-journal compatibility repair. It
fails closed with `PREFLIGHT_IMPLEMENTATION_MISMATCH`.

The 24-service model includes the adjudicated correction for defect `147042`:
five wall openings, two flex ducts, and a metal pipe in the conduit/cable
penetration. That correction exists in source-bound proposal/evidence material;
it has not been written as canonical physical-model data.

The proposal still has unresolved material and withheld-quantity evidence. It
is not a Physical Model Lock candidate. No replacement active Physical Model
Lock has been created by this work, so Phases 9 onward remain blocked.

## 4. P-256 signer and admission evidence

The Android Keystore signer produced a locally verified P-256 package at:

`data/real-uat/20260821-phase8-p256-admission-package-147042-v3/`

The retained `signature-verification.json` identifies admission
`9c3d848f-d891-4449-9172-7be2ea5705bd`, issuer
`classifire-governance`, and key ID `governance-p256-01`. The signed package
exists, but its expiry is `2026-08-21T11:41:15Z`; it must not be reused.

The prior registration attempt rolled back safely with
`ADMISSION_REGISTRATION_PERSISTENCE_FAILED`. Do not infer a live admission
record or canonical write from the signature verification. The Android private
key remains non-exportable in Android Keystore: never request, export, store,
or log it.

## 5. Admission-journal contract: verified repair and disposable rehearsal

### Current database and migration state

`python -m alembic current` was run in this snapshot and reports:

`0007_reconcile_adjudicated_admission_lineages (head) (mergepoint)`

The reviewed clean contract uses:

- `physical_model_admissions` with the immutable signed envelope, normalised
  payload JSON, `artifact_digests`, and `policy_versions`; and
- `physical_model_submission_receipts` for a successful controlled submission.

The superseded `physical_model_initial_submissions` table and legacy admission
fields such as `preflight_receipt_json`, `artifact_manifest_sha256`,
`implementation_manifest_sha256`, and claim-resolution fields are not part of
the clean `0007` contract.

### What has been repaired in the checkout

The uncommitted ORM, offline registration guard, controlled writer, and focused
tests were aligned to the clean `0007` table names and fields. The writer now
records the existing receipt contract and retains idempotency evidence inside
the signed-submission receipt. The registration guard requires the `0007`
lineage and the clean admissions/receipts tables.

The migration test now asserts that a fresh SQLite database reaches `0007` and
contains the clean fields while excluding the legacy table/fields. The local
database already reports `0007`, and adjudicated mode has one configured
public-key pin and one issuer mapping. This session did not change the live
schema or configuration, register a live admission, submit a canonical model,
or create a lock.

### Disposable-copy rehearsal

The current contract passed a disposable-copy rehearsal. The retained safe
receipt is:

`data/real-uat/20260822-phase8-existing-physical-rehearsal-147042-v1/adjudicated-canonicalisation-rehearsal.json`

It proves that `cf-physical-model` used its admission-only scope to consume a
synthetic short-lived admission on the copy, the exact
17-Opening/24-Service/24-link topology was written once, idempotent replay
returned the same submission, no lock or Gateway call occurred, and the source
database retained fingerprint
`A1FFA7501C13481D01E3A7BE00ABC3CC940968DAD72037531D07A68DE70FAFD9`
with zero canonical physical rows, admissions, and submission receipts. The
disposable database, synthetic manifest, token, and ephemeral private key were
not retained.

### Remaining gate

The local plugin now builds successfully from the current TypeScript source,
but that artifact has not been installed or runtime-verified. The existing
`cf-physical-model` database principal and token are active but still lack
`physical:adjudicated:submit`; synchronising that persisted scope without
rotating the token, plus plugin installation/restart, are live changes
requiring explicit approval. A
fresh external signature, live admission registration, canonical submission,
and any future lock remain separate later authorities.

The installed global plugin remains admission-only v0.4.0. The repository now
contains a v0.5.0 deployment candidate with an explicit, fail-closed
`phase8-admission-only` profile. Local runtime registration verification proves
that this profile exposes only `classifire_submit_initial_physical_model`, and
only to `cf-physical-model`. The pre-existing intake, technical, quantity, and
commercial tools remain in source and are registered only by the separately
selected `full-controlled-write` profile. The v0.5.0 candidate has not been
installed, enabled, or loaded by the live Gateway.

The source agent-fleet package now matches that profile. Its active Phase 8
matrix and role tool files expose only the admission submission from the
controlled-write plugin, preserve the broader tools as inactive source
inventory, and direct `cf-physical-model` to stop after the submission receipt.
Physical Model Lock remains a later Mission Control task with no active Phase 8
tool. These agent-definition changes are local and have not been copied into
live OpenClaw workspaces or Mission Control.

### Local Gate A candidate freeze

`scripts/audit_phase8_admission_deployment_candidate.py` now freezes the
reviewed admission boundary, migration lineage, plugin artifact, installer,
agent governance, governing documentation, and regression sources into one
self-bound hash manifest. It also revalidates the v5 implementation-bound
preflight and disposable rehearsal without reading credentials or contacting a
database, Gateway, signer, or live configuration.

The retained local receipt is:

`data/real-uat/20260822-phase8-admission-deployment-candidate-v1/candidate-audit.json`

Its clean-tree mode correctly reports
`LOCAL_CANDIDATE_FROZEN_REVIEW_REQUIRED` and exits `2` because this checkout is
still extensively dirty. This is a Gate A stop condition, not a deployment
failure and not authority to install the candidate.

## 6. Roadmap and architecture position

`docs/CLASSIFIRE_ROADMAP.md` and `docs/CLASSIFIRE_ARCHITECTURE.md` are modified
but uncommitted. They now describe the verified 17-opening/24-service Phase 8
proposal, the measured 12,000-character Windows-safe defect budget, the expired
v3 admission, and the admission-journal compatibility gate.

The architecture keeps these decisions in force:

- proposal-only inference and human adjudication do not overwrite canonical
  truth;
- protected-state fingerprinting, not whole SQLite-file hashes, protects the
  physical-model invariant;
- registration is immutable admission-journal evidence only, not canonical
  submission or locking;
- canonical submission requires a fresh, separate authority and a
  same-transaction protected-state recheck;
- a Physical Model Lock is a later, separately governed decision blocked by
  unresolved material/quantity evidence and the missing dedicated lock-admission
  boundary;
- CLASSIFIRE retains deterministic domain logic; OpenClaw remains a controlled
  execution boundary.

## 7. Checks actually performed in this snapshot

| Check | Result | What it proves |
| --- | --- | --- |
| `python -m alembic current` | passed | The local database reports the `0007` mergepoint as current head. |
| Full repository pytest suite | 494 passed | The existing-agent reconciliation, admission-only profile, agent-governance alignment, Gate A audit, and migration-retention protection did not regress the repository's collected automated test suite. |
| Focused admission/plugin/boundary pytest suite | 62 passed | Admission, submission, rehearsal, scoped credential sync, role-policy, plugin-manifest, agent-governance, Gate A audit, legacy-boundary, intake API, and migration-retention paths passed locally. |
| Focused Ruff check | passed | Reconciled Python policy, rehearsal, and test files meet the configured rules, excluding two unrelated pre-existing rules in `agent_security.py`. |
| Modified PowerShell parse check | passed | The installer and live boundary script are syntactically valid without executing them. |
| Installer `-PlanOnly` stale-scope gate | passed | The installer stopped before plan generation because the live `cf-physical-model` credential lacks `physical:adjudicated:submit`. |
| Controlled-write plugin build | passed | Current TypeScript source compiled to `dist/index.js`; it was not installed or restarted. |
| Phase 8 plugin runtime-profile verifier | passed | Admission-only registers exactly one tool, full-profile source preservation is proven, and invalid, wrong-role, and visual-session paths fail closed. |
| Agent-definition profile drift tests | 4 passed | Fleet grants, role tool instructions, Physical stop-before-lock behaviour, Mission Control sequencing, plugin source, and installer configuration agree on the Phase 8 boundary. |
| Gate A candidate auditor tests | 3 passed | The source/evidence freeze binds itself, rejects unsafe rehearsal evidence and refuses output outside the repository. |
| Gate A `--require-clean` execution | expected exit `2` | The real candidate and retained evidence validate, but the dirty checkout remains an explicit deployment-review blocker. |
| Legacy-journal reconciliation retention test | passed | A disposable non-empty legacy admission journal makes `0007` fail before it can drop or replace retained journal data. |
| `git diff --check` | passed | No whitespace errors were reported in the current working-tree diff. |
| v5 preflight and existing-agent rehearsal receipts | verified | Current code is bound to a no-write 17/24 preflight and the disposable 17/24/24 submission through `cf-physical-model` passed without changing the source database. |

Do not claim successful live registration, canonical submission, or deployment.
An expanded Ruff probe over older pending files still reports pre-existing
style/security-lint findings outside the reconciled files.

## 8. Recommended next-session sequence

1. Review the exact file and hash inventory in the retained Gate A candidate
   receipt, including the v0.5.0 profile, installer cleanup, agent governance,
   admission contract, migrations, tests, v5 preflight, and rehearsal.
2. Produce a reviewed clean candidate state without discarding unrelated user
   work. Commit, branch publication, or isolated-worktree publication still
   requires its own current authority.
3. Present the exact existing-principal scope synchronisation,
   plugin-installation, restart, recovery, and runtime-boundary impact for
   explicit approval. Do not perform those live changes under general
   development authority.
4. After an approved deployment passes negative boundary checks, recompute a
   fresh no-write preflight if any bound implementation or protected state has
   changed, then obtain a fresh phone signature. The expired v3 admission must
   not be reused.
5. Request separate current authority to register that fresh admission.
6. Treat canonical submission and Physical Model Lock creation as later,
   separate gates. The current unresolved material and quantity evidence still
   prevents a lock.

## 9. Authority reminders

General development authority does not include committing, pushing, opening or
merging a PR, changing live database schema/configuration, registering an
admission, submitting a canonical model, or creating a lock. Each requires
current explicit authority after the relevant evidence is available.
