# CLASSIFIRE Project State

**Verified:** 2026-08-22 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Checked-out branch:** `gpt/phase8-linked-original-images`

**Committed branch tip before this reconciliation:** `1b4b327d8f06e8fb1552a32f64262928f991990f`

**Shared GitHub `main`:** `82d91400f9400da1649e071892d43f2cb465057b`

This state record is based on the current source tree, tests, migration graph,
read-only database checks, retained receipts, and refreshed GitHub references.
It distinguishes committed shared code from newer local-only work. A feature is
not marked operational merely because its service or tests exist.

## 1. Repository position

The checked-out branch and `origin/gpt/phase8-linked-original-images` were both
at `1b4b327` before this documentation commit. The branch had no configured
upstream and was 375 commits ahead of and 54 commits behind `origin/main` from
merge base `fea9549`; the committed branch-to-main comparison contained 346
changed files. It is therefore a divergent development line, not a safe
deployment candidate for shared `main`.

The working tree also contains extensive pre-existing tracked and untracked
Phase 8 work. The current local admission implementation, migrations, plugin
build and v6 preflight receipt are not all represented by the branch tip. They
must not be described as published merely because they are present locally.
Unrelated dirty work, including `agent-definitions/` and `classifire logo.png`,
must be preserved and explicitly excluded from documentation-only commits.

Shared `main` contains newer admission-writer reconciliation, the read-only
Gate A candidate auditor, and the offline Android admission signer. The Android
signer is not present in the checked-out branch tree. Conversely, the local
checkout contains a built plugin artifact and a separate `canonical_models`
admission implementation that must not be merged wholesale into `main`.

## 2. Latest verified implementation state

### Completed implementation foundations

- A FastAPI application, server-rendered administration UI, Typer CLI,
  SQLAlchemy persistence layer and Alembic migration system exist.
- The local migration graph has one current head:
  `0007_reconcile_adjudicated_admission_lineages`.
- Canonical concepts exist for Projects, estimates, evidence, Defects,
  Openings, Services, Opening-Service links, physical and repair locks,
  technical requirements, quantities, labour, commercial recovery, validation,
  snapshots, certificates, audit events and release approvals.
- Guarded services and APIs exist for physical-model locking, Opening-specific
  technical search, repair-strategy selection/locking, component derivation,
  quantity/labour, commercial recovery, independent validation, immutable
  snapshots, PDF/XLSX rendering and human-only release.
- A deterministic reference fixture exercises the technical-to-snapshot chain.
  These services are implementation foundations; they do not mean the current
  real-report estimate has passed their upstream gates.
- Role-scoped agent authentication, controlled-write endpoints, OpenClaw tool
  policies and a Mission Control client/task bootstrap exist.
- The evidence/UAT tooling retains pages and images, resolves verified linked
  originals, preserves distinct visual variants and provenance, and uses an
  independent proposal-only visual topology gate.
- A component-level protected-state fingerprint, adjudicated proposal records,
  P-256 admission verification, immutable admission registration,
  same-transaction state rechecks, idempotent initial submission receipts and a
  no-lock initial canonicalisation boundary are implemented in the current
  local worktree. Shared `main` contains a reconciled but differently organised
  admission lineage.
- Shared `main` contains an offline Android signer that imports and exports
  local documents, has no Internet permission, requires strong biometric
  approval, uses a hardware-backed P-256 Android Keystore key, verifies low-S
  ECDSA locally, and cannot register, submit or lock CLASSIFIRE data.

### In progress

- Repository and migration consolidation between the divergent current branch
  and shared `main`.
- Production enforcement of scope-aware blank-opening completeness throughout
  every workflow adapter and mutation path.
- Governed technical/commercial source publication, registry-neutral technical
  provenance and multi-library estimate pinning.
- Clean-machine OpenClaw plugin build/deployment proof and live least-privilege
  runtime verification.
- Generalisation of linked-original/evidence-family handling beyond the current
  report and approved hosts.
- Phase 8 corrected real-report Physical UAT and the later signed lock-admission
  design.
- Production hardening, security, recovery, rendered-output QA, performance
  benchmarks and operational observability.

### Planned

- The Phase 8C accuracy programme: governed benchmark corpus, measurement
  harness, exception workflow, prospective shadow evaluation and optional
  fine-tuning only after its admission gates pass.
- Additive structural-steel and complete fire-rated-duct domains (Phase 16).

### Blocked for the current real-report estimate

Phases 9-14 are implemented to varying degrees in code, but the current
estimate cannot validly use them. Technical selection, quantities/labour,
commercial recovery, independent validation/snapshot, outputs and Human
Release remain blocked until Phase 8 produces a semantically accepted
canonical Physical Model and a replacement active Physical Model Lock.

### Deprecated or superseded

- Whole-database-file hashing as proposal integrity proof is superseded by the
  protected-state component fingerprint.
- Count-only physical comparison is superseded by semantic Opening-Service
  graph comparison and explicit uncertainty.
- The old v3 signed admission package is expired and unusable. A fresh preflight
  and signature would be required after an approved deployment.
- Generic Physical Model Lock creation is retired while admission-bound initial
  submission is enabled; the APIs return `410` until a separate signed
  lock-admission boundary exists.
- Treating Package 15 as a universal technical database is superseded by the
  CLASSIFIRE Technical Authority Registry with FIREFLY Package 15/17 as one
  governed library.
- `QUANTIFIRE` and `PFEOS` names are historical compatibility identifiers, not
  the current product name. They remain in some code and persisted contracts
  until migration impact is resolved.

## 3. Current Phase 8 evidence

The retained no-write receipt is:

`data/real-uat/20260822-phase8-postmerge-preflight-147042-v6/24-adjudicated-canonicalisation-preflight.json`

Verified receipt values:

| Item | Value |
| --- | --- |
| Schema | `CLASSIFIRE-ADJUDICATED-CANONICALISATION-PREFLIGHT-v3` |
| Status | `PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED` |
| Generated | `2026-08-22T05:24:50Z` |
| Proposed topology | 17 Openings, 24 Services, 24 links |
| Submission eligible | `false` |
| Lock eligible | `false` |
| Database/canonical/Gateway writes | all `false` |
| Payload SHA-256 | `85B3D16F92E32AA6BF05B5CD8C0192F9719C2FB45D081C26D1159733E65B8FB3` |
| Protected-state fingerprint | `18768A9E368C7D0692A950303FCAC9401AFBE7C3632BE6A063FCB67B9671F8F1` |
| Receipt SHA-256 | `1BF735B2D441B214967672072323C37B587C4E8659EF8F8BDC9D0D3A120D43F2` |

An immutable read-only query of `data/classifire.db` confirmed that this target
estimate is still `draft` with 10 Defects and 128 EvidenceSources, and has:

- 0 canonical Openings, Services and Opening-Service links;
- 0 admissions and submission receipts;
- 0 active Physical Model Locks;
- 0 RepairStrategies and required components;
- 0 validation gates and no validated snapshot; and
- 0 Human Release approvals.

The database as a whole contains older/sample estimates and historical locks;
aggregate database counts must not be mistaken for the target estimate's
state. No canonical or live runtime operation was performed during this review.

## 4. Shared-main deployment gate

The clean detached shared-main worktree at `82d9140` passed the repository
cleanliness check but the read-only Gate A auditor returned exit code 2 with:

`LOCAL_CANDIDATE_REQUIRED_ARTIFACT_MISSING`

The missing required artifact is:

`openclaw-plugin-classifire-controlled-write/dist/index.js`

The audit explicitly reported `deployment_authorised=false` and
`live_change_performed=false`. The current dirty checkout has a local compiled
artifact, but it belongs to the divergent local implementation and is not a
substitute for a reproducible build from shared `main`.

## 5. Architectural divergences and unresolved issues

1. The current application registers guarded phase-specific routers before an
   overlapping legacy v1 router. Route order reduces bypass risk, but duplicate
   public operations remain architectural debt and need explicit retirement or
   compatibility tests.
2. Persistence is split across `models.py`, `canonical_models.py` and
   `commercial_models.py`; shared `main` organises the admission writer around
   `physical_models.py`. One reviewed model and migration lineage is required.
3. `services/physical_scope.py` correctly permits blank Openings with zero
   Services, but `services/workflow_db.py` still computes completeness using
   `all_openings_have_services`. The generic adapter can therefore disagree
   with the governed physical lock service.
4. Legacy `package15_release_id`, singular technical-release pinning and the
   Service quantity default of 1 remain compatibility/schema debt.
5. The governed private knowledge source pack is absent from this checkout.
   Its manifests are present, but the K1 publication gate is not complete.
6. Approved productivity coverage is incomplete for the 38 FIREFLY labour
   activities; quantity/labour must fail closed when a required source is
   missing.
7. PDF/XLSX renderers and controlled export routes exist, but the current UAT
   has not reached a snapshot and no representative rendered artifact was
   inspected in this reconciliation.
8. Clean deployment, backup/restore, rollback, adversarial security, 10/100/1000
   defect performance and production monitoring evidence remain incomplete.

## 6. Verification performed for this reconciliation

- Refreshed `origin` and compared the checked-out branch, its remote branch and
  `origin/main`.
- Confirmed Alembic reports one head at
  `0007_reconcile_adjudicated_admission_lineages`.
- Ran 152 focused tests covering project alignment, fresh migrations, the
  reference technical-to-snapshot lifecycle, technical registry,
  repair-strategy selection, quantities/labour, productivity, commercial
  recovery, validation/release, Human Release, Mission Control, evidence image
  resolution, visual correction policy and the local admission boundary: all
  152 passed.
- Ran the project/knowledge alignment audit: 0 hard errors and 4 warnings
  (missing private source pack, legacy Package-15 field, singular technical
  pinning and Service quantity default).
- Ran the clean shared-main Gate A auditor: blocked only by the missing compiled
  plugin artifact; no live action occurred.
- Queried only aggregate workflow facts from the local SQLite database using
  immutable read-only mode.

This was not a full test-suite run, Android rebuild, Gateway/runtime check,
deployment test, or visual inspection of rendered client outputs.

## 7. Next valid task

Create a clean candidate from current shared `main`, rebuild the controlled-write
plugin artifact in an approved reproducible environment, rerun the Gate A audit
and focused main-line tests, and review the exact candidate diff. Do not source
the artifact from this divergent dirty checkout. Deployment, runtime restart,
admission signing/registration/submission and Physical Model Lock creation are
separate later operations with their own gates.
