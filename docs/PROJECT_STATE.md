# CLASSIFIRE Project State

**Verified:** 2026-08-23 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Checked-out branch:** `gpt/phase8-linked-original-images`

**Branch tip before this reconciliation:** `4efe1e538ccf3a1f914867df88a430185a21c9d7`

**Configured upstream before this reconciliation:**
`origin/gpt/phase8-linked-original-images` at the same commit

**Shared GitHub `main`:** `78016368457748975c331bedab796cd03ee832e6`

This record is based on the committed source, the complete local working tree,
tests, migration metadata, immutable read-only database inspection, retained
receipts, and refreshed local and GitHub references. It distinguishes shared
implementation, branch-local implementation, operational evidence, and work
that is present but unsuitable for publication.

The canonical repository documents are this file,
[`CLASSIFIRE_ARCHITECTURE.md`](./CLASSIFIRE_ARCHITECTURE.md), and
[`CLASSIFIRE_ROADMAP.md`](./CLASSIFIRE_ROADMAP.md). No root-level architecture
or roadmap files exist. The local root `AGENTS.md` is useful working guidance
but is untracked and is not yet a shared repository authority.

## 1. Repository position

The checked-out branch was synchronized with its configured upstream before
this documentation change and had no unpushed commits. It is nevertheless a
legacy stacked development line, not a branch based on current shared `main`:

| Item | Verified value |
| --- | --- |
| Branch and upstream tip | `4efe1e5` |
| Shared `origin/main` | `7801636` |
| Merge base | `fea9549` |
| Commits unique to shared main | 116 |
| Commits unique to this branch | 376 |
| Committed branch-to-main changed paths | 347 |
| GitHub review surface | Open stacked draft PR #13 |

Pushing this branch updates draft PR #13; it does not update shared `main`.
The branch must not be merged wholesale. Current-main changes and any useful
legacy behaviour require bounded review from a clean branch based on current
`main`.

### 1.1 Working tree before this documentation review

The primary checkout had no staged or deleted files. It contained:

- 46 modified tracked files (`+1,668/-894`);
- at least 37,149 enumerated untracked files; and
- additional unreadable pytest cache contents that Git reported as permission
  denied.

The dirty tree includes local admission experiments, legacy UAT runners, tests,
generated receipts and databases, Android/JDK/SDK/Gradle tooling, temporary
worktrees, PDFs, editor settings, `agent-definitions/`, and
`classifire logo.png`. These files have been preserved.

Four modified plugin files and six untracked migration/profile files are
byte-for-byte copies of work already published on shared `main`; recommitting
them would duplicate completed work. Other admission and runner changes use a
legacy model/API/migration lineage that current `main` has superseded. The
tracked implementation diff also has 290 Ruff findings and 24 files that Ruff
would reformat. No pre-existing implementation file is complete and suitable
for this documentation commit.

## 2. Latest verified implementation state

### 2.1 Completed on shared `main`

- FastAPI, CLI, persistence and Alembic foundations exist for the current
  physical/admission path.
- The shared migration lineage reaches
  `0008_retire_legacy_initial_submissions` and retires obsolete initial-write
  paths fail closed.
- The Phase 8 proposal path includes component-level protected-state
  fingerprinting, bounded Validator correction, semantic comparison, blind
  inventory/reconciliation, strict proposal control, retained-evidence
  adaptation, zero-tool transport/runtime identities, and synthetic live
  inference proof.
- Linked originals can be retrieved under bounded network/content controls,
  verified against report evidence, retained with provenance, and passed to the
  proposal-only runner without giving that runner a canonical-write or lock
  capability.
- The bounded linked-original-to-proposal runner and its required-low-resolution
  fail-closed correction are merged. The runner is synthetic-tested but has not
  yet completed the representative approved-report execution tracked by issue
  #42.
- The admission lineage supports immutable registration, exact state/payload
  binding, one-shot initial submission, idempotent receipts, and no lock in the
  same operation.
- The offline Android signer is separated from CLASSIFIRE transport and write
  authority. Release-APK verification and on-device governance-key evidence
  exist; no real Phase 8 admission has been signed or registered.
- The exact-main Gate A source/artifact candidate audit passes at `7801636`.
  Gates A-F have recorded validation for the configured local environment, but
  those receipts do not authorise a canonical submission or Physical Model
  Lock.

### 2.2 Implemented only on this divergent branch

This branch contains broad, guarded foundations for technical search and repair
strategy, quantities and labour, commercial recovery, independent validation,
immutable snapshots, output rendering, and human-only release. Reference tests
exercise much of that chain locally.

Those foundations are absent or materially different on current shared `main`.
They are therefore evidence of implemented branch-local capability, not
published main-line product completion. They require deliberate reconciliation
and cannot be revived by copying the dirty legacy admission stack.

### 2.3 In progress

- Consolidating active work on clean branches based on current shared `main`
  and resolving or closing the stacked legacy PRs.
- The representative, rollback-only linked-original proposal run tracked by
  issue #42.
- Production persistence/enforcement of a hash-bound visual-validation receipt.
- Evidence-family taxonomy and multi-report generalisation.
- Scope-aware blank-opening completeness across every adapter and mutation path.
- Governed technical/commercial source publication, registry-neutral
  provenance, and multi-library estimate pinning.
- Mission Control integration without making it canonical estimate state.
- Product-name compatibility work: CLASSIFIRE is canonical, but extensive
  `QUANTIFIRE` identifiers and user-facing text remain on shared `main`.
- Production security, recovery, observability, performance, clean deployment,
  and rendered-output quality assurance.

### 2.4 Planned

- Phase 8C: a governed benchmark corpus, measurement harness, exception
  workflow, prospective shadow evaluation, and optional model training only
  after its admission gates pass.
- Additive structural-steel and complete fire-rated-duct domains in Phase 16.

### 2.5 Blocked

- A real Phase 8 canonical submission remains blocked pending a fresh exact-main
  preflight, a matching external signature, immutable registration, and
  separate current authority for the exact submission.
- A replacement Physical Model Lock remains blocked until a separate signed
  lock-admission boundary is designed, reviewed, and authorised.
- Phases 9-14 remain blocked for the current real-report estimate because it has
  no canonical Physical Model or active replacement lock.
- Private-source publication and complete approved productivity coverage remain
  incomplete; technical and labour decisions must fail closed where authority
  is missing.

### 2.6 Deprecated or superseded

- Wholesale merge of this legacy branch and its old admission/model lineage.
- Obsolete real-UAT launchers and raw submit/lock paths replaced by the bounded
  current-main proposal controller and runner.
- Whole-database-file hashing as proposal-integrity evidence.
- Count-only physical acceptance without semantic topology comparison.
- The expired v3 admission package, the Ed25519 production-signer path, retired
  debug-app keys/certificate, and generic lock creation in admission-only mode.
- Treating Package 15 as a universal technical database; FIREFLY Package 15/17
  is one governed member of the Technical Authority Registry.
- Treating domain/source package lineage `v2.13` as the running application
  version. Shared-main Python package metadata currently reports `0.1.0`.

## 3. Current Phase 8 evidence

The retained no-write v6 preflight is:

`data/real-uat/20260822-phase8-postmerge-preflight-147042-v6/24-adjudicated-canonicalisation-preflight.json`

| Item | Verified value |
| --- | --- |
| Schema | `CLASSIFIRE-ADJUDICATED-CANONICALISATION-PREFLIGHT-v3` |
| Status | `PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED` |
| Generated | `2026-08-22T05:24:50Z` |
| Proposed topology | 17 Openings, 24 normalized Services, 24 links |
| Submission eligible | `false` |
| Lock eligible | `false` |
| Database/canonical/Gateway writes | all `false` |
| Payload SHA-256 | `85B3D16F92E32AA6BF05B5CD8C0192F9719C2FB45D081C26D1159733E65B8FB3` |
| Protected-state fingerprint | `18768A9E368C7D0692A950303FCAC9401AFBE7C3632BE6A063FCB67B9671F8F1` |
| Receipt SHA-256 | `1BF735B2D441B214967672072323C37B587C4E8659EF8F8BDC9D0D3A120D43F2` |

The 24-Service count is the normalized canonical row count. Any historical
22-service-group description is a different pre-normalisation grouping measure
and must not be presented as the same count.

An immutable read-only query on 2026-08-23 confirmed that the target estimate
`e333e8de-a3b8-40ce-8997-1a1204a573da` remains `draft`, with 10 Defects and 128
EvidenceSources, and has:

- 0 canonical Openings, Services, and Opening-Service links;
- 0 admissions and submission receipts;
- 0 active Physical Model Locks;
- 0 RepairStrategies and required components;
- 0 validation gates or validated snapshots; and
- 0 Human Release approvals.

The local database records migration
`0008_retire_legacy_initial_submissions`, but this branch's local source graph
resolves only through `0007_reconcile_adjudicated_admission_lineages`. The
checkout must not operate on that database as a deployment source. Aggregate
database counts include unrelated historical/sample estimates and do not alter
the target estimate facts above.

## 4. Exact-main Gate A and operational boundary

The final exact-main candidate at `7801636` passed the read-only Gate A
source/artifact checks with:

| Evidence | Value |
| --- | --- |
| Plugin artifact SHA-256 | `38812E99DC138A198EE58BF6E00E9B34E081502CB43C39089418BC53E3C2AEE4` |
| Candidate fingerprint | `CB52D91823EFC06EB76E443D3E8D4CF3D9C901DFEBB262842E1EADAE94B26E15` |
| Candidate worktree | clean |
| Missing required paths | none |
| Deployment authorised by Gate A | `false` |
| Live change performed by Gate A | `false` |

This supersedes the earlier `LOCAL_CANDIDATE_REQUIRED_ARTIFACT_MISSING`
blocker at `82d9140`. It proves the exact source/artifact candidate, not a real
admission, canonical submission, lock, estimate release, or production
readiness.

## 5. Architectural divergences and unresolved issues

1. Shared `main` is the current Phase 8 source of truth, while this branch
   retains broad later-phase foundations and a superseded physical/admission
   composition. One reviewed main-line architecture is still required.
2. The local database is at migration `0008`, which this checkout cannot
   reproduce. This branch must not be used for database writes or deployment.
3. Shared `main` still contains substantial `QUANTIFIRE` naming and does not
   track this branch's architecture document or the local root `AGENTS.md`.
4. The representative approved-report linked-original run is pending under
   issue #42. Synthetic tests do not prove report-specific performance.
5. Current-main expiry validation may lack the dirty branch's explicit 900-second
   maximum admission lifetime. This is a candidate security hardening task to
   verify and, if needed, forward-port with dedicated tests from clean `main`.
6. Scope-aware blank-opening completeness is not yet proven across every
   current-main workflow adapter and mutation path.
7. Legacy Package-15 naming, singular technical-release pinning, and a Service
   quantity default of 1 remain compatibility/schema debt in branch-local code.
8. The governed private knowledge source pack is unavailable in this checkout,
   and approved productivity coverage is incomplete for all FIREFLY activities.
9. Output renderers exist, but the current estimate has no eligible snapshot and
   no representative current-estimate PDF/XLSX output was inspected.
10. OpenClaw issue #43 tracks development-dependency advisories; shipped plugin
    dependencies were separately reported clean. Recovery, adversarial security,
    scale, and production monitoring evidence remain incomplete.

## 6. Verification performed for this reconciliation

- Refreshed Git/GitHub references and inspected branch, upstream, open PR/issue,
  divergence, staged, unstaged, and untracked state.
- Classified all 46 tracked modifications and the substantive untracked files;
  no pre-existing implementation file qualified for this commit.
- Ran the full dirty-tree test collection with isolated temporary paths and
  plugin autoload disabled: 494 tests across 63 collected file groups passed.
- Ran 125 tests directly affected by the tracked implementation diff: passed.
- Ran the project/knowledge alignment audit: 0 hard errors and 4 warnings
  (missing private source pack, legacy Package-15 field, singular technical
  pinning, and Service quantity default).
- Ran `classifire doctor`: the command completed, the database check passed, and
  private Package 14/15 and raw-calculator checks remained unavailable because
  their governed source artifacts are absent.
- Confirmed the local source graph has one Alembic head at `0007`, then queried
  the target database only through immutable read-only mode and found it at
  `0008` with the target estimate still unchanged.
- Retained exact-main evidence records 292 full tests, 107 related tests, and 42
  focused linked-retrieval/runner tests passing for the current-main work.
- Reviewed lint state for the pre-existing tracked diff: `git diff --check`
  passed, while Ruff reported 290 findings and 24 files needing formatting.

No canonical data, admission, registration, submission, lock, deployment, or
release operation was performed during this documentation review.

## 7. Local-change commit classification

### Category 1 - created by this review and intended for commit

- `docs/PROJECT_STATE.md`
- `docs/CLASSIFIRE_ARCHITECTURE.md`
- `docs/CLASSIFIRE_ROADMAP.md`

### Category 2 - pre-existing, relevant, complete, and suitable for this commit

None.

### Category 3 - deliberately left untouched

- All 46 pre-existing tracked implementation modifications.
- Untracked legacy/divergent admission services, scripts, migrations, and tests.
- Byte-identical copies of files already published on shared `main`.
- `AGENTS.md`, local handoffs/runbooks, `docs/GOAL.md`, generated PDFs, editor
  files, `agent-definitions/`, and the logo asset.
- Temporary worktrees/caches, SDK/JDK/Gradle/tool bundles, APK/build artifacts,
  database copies, WAL/SHM files, UAT receipts, and customer/private evidence.

## 8. Next valid task

Use a clean branch from current shared `main` and complete the explicitly
approved, rollback-only representative linked-original proposal run tracked by
issue #42. Review its evidence manifest, retained originals, proposal receipt,
Validator receipt, protected-state receipt, and rollback proof.

That run is proposal-only. It grants no authority to sign or register an
admission, submit canonical data, create a Physical Model Lock, or release an
estimate. The maximum-admission-lifetime hardening should be assessed afterward
as a separate clean-main security correction, not extracted from this dirty
branch during the run.
