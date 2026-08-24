# CLASSIFIRE Project State

**Verified:** 2026-08-24 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Checked-out branch:** `gpt/phase8-linked-original-images`

**Branch tip before this reconciliation:** `79f82a6fc2894fd7c049d44535780014706e69da`

**Configured upstream before this reconciliation:**
`origin/gpt/phase8-linked-original-images` at the same commit

**Shared GitHub `main`:** `78016368457748975c331bedab796cd03ee832e6`

This record is based on committed source, every visible local change, tests,
migration metadata, retained execution and human-review receipts, and refreshed
local and GitHub references. It distinguishes shared implementation, the
checked legacy branch, the separately pushed representative package, the
uncommitted exact-main candidate worktree, and operational evidence.

The canonical repository documents are this file,
[`CLASSIFIRE_ARCHITECTURE.md`](./CLASSIFIRE_ARCHITECTURE.md), and
[`CLASSIFIRE_ROADMAP.md`](./CLASSIFIRE_ROADMAP.md). No root-level architecture
or roadmap files exist. The local root `AGENTS.md` is useful working guidance
but is untracked and is not yet a shared repository authority.

## 1. Repository position

The checked-out branch is synchronized with its configured upstream and has no
unpushed commits. It is nevertheless a
legacy stacked development line, not a branch based on current shared `main`:

| Item | Verified value |
| --- | --- |
| Branch and upstream tip | `79f82a6` |
| Shared `origin/main` | `7801636` |
| Merge base | `fea9549` |
| Commits unique to shared main | 116 |
| Commits unique to this branch | 377 |
| Committed branch-to-main changed paths | 347 |
| GitHub review surface | Open stacked draft PR #13 |

Pushing this branch updates draft PR #13; it does not update shared `main`.
The branch must not be merged wholesale. Current-main changes and any useful
legacy behaviour require bounded review from a clean branch based on current
`main`.

Two newer scopes are separate from this root checkout:

- pushed commit `b422240` on
  `gpt/phase8-representative-run-package` adds the coherent representative
  package and offline recovery on top of `7801636`; it has no pull request and
  is not merged into main; and
- the isolated branch
  `gpt/phase8-human-adjudicated-proposal-validation-20260824` is based on
  `7801636`, has no upstream, and contains 41 modified plus 34 untracked
  candidate paths. Those 75 paths are uncommitted work in progress.

### 1.1 Working tree before this documentation review

The primary checkout had no staged or deleted files. It contained:

- 46 modified tracked files (`+1,668/-894`);
- at least 45,403 enumerated untracked files; and
- additional unreadable pytest cache contents that Git reported as permission
  denied.

The dirty tree includes local admission experiments, legacy UAT runners, tests,
generated receipts and databases, Android/JDK/SDK/Gradle tooling, temporary
worktrees, PDFs, editor settings, `agent-definitions/`, and
`classifire logo.png`. These files have been preserved.

Five modified plugin paths and five untracked migration paths are
byte-for-byte copies of work already published on shared `main`; recommitting
them would duplicate completed work. Other admission and runner changes use a
legacy model/API/migration lineage that current `main` has superseded. The
tracked implementation diff also has 290 Ruff findings and 24 files that Ruff
would reformat. No pre-existing implementation file is complete and suitable
for this documentation commit.

The isolated current-main worktree contains local visual-receipt, evidence-
family, human-review-v2, provenance, evidence-rights, dependency-lock, signed-
lock-design, technical-compatibility, and source-release-contract candidates.
Its retained evidence records 362 full tests and focused Ruff checks passing,
but that does not make the uncommitted bundle shared or publication-ready.

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
  fail-closed correction are merged. The representative execution has now run
  from this source baseline through separately pushed/local tooling; its blocked
  result is execution evidence, not a merged-main feature or accepted model.
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

### 2.2 Completed but not merged: representative package

Commit `b422240` adds the coherent rollback-only representative package,
content-safe human-review request, and offline recovery. Retained verification
records 332 full tests and 145 focused tests passing, changed-path Ruff and
mypy passing, no medium/high Bandit findings, and one Alembic head at `0008`.
The commit is pushed but has no pull request and is not in shared main.

### 2.3 Implemented on the divergent branch

This branch contains broad, guarded foundations for technical search and repair
strategy, quantities and labour, commercial recovery, independent validation,
immutable snapshots, output rendering, and human-only release. Reference tests
exercise much of that chain locally.

Shared main has lower-level technical search, release, calculation, snapshot,
output, and Mission Control foundations, but not this branch's complete guarded
chain. Neither line meets the Phase 9-14 exit architecture. The richer legacy
stack is branch-local evidence and cannot be revived by copying its dirty
admission composition.

### 2.4 In progress

- Consolidating active work on clean branches based on current shared `main`
  and resolving or closing the stacked legacy PRs.
- Review and current-main publication of the pushed representative package;
  issue #42 remains open and its pending-run wording is now stale.
- Production persistence/enforcement of a hash-bound visual-validation receipt;
  an uncommitted current-main candidate exists, but no real approved receipt.
- Evidence-family taxonomy, rights controls, and multi-report generalisation;
  local candidate contracts are not yet published.
- Durable human-review/provenance governance for the v2 response and adjudicated
  proposal.
- Scope-aware blank-opening completeness across every adapter and mutation path.
- Governed technical/commercial source publication, registry-neutral
  provenance, and multi-library estimate pinning.
- Mission Control integration without making it canonical estimate state.
- Product-name compatibility work: CLASSIFIRE is canonical, but extensive
  `QUANTIFIRE` identifiers and user-facing text remain on shared `main`.
- Production security, recovery, observability, performance, clean deployment,
  and rendered-output quality assurance.

### 2.5 Planned

- Phase 8C execution: a local charter, rights template, and validator are
  preparatory drafts; benchmark, shadow, and optional training work remains
  blocked until its programme admission gates pass.
- Additive structural-steel and complete fire-rated-duct domains in Phase 16.

### 2.6 Blocked

- A real Phase 8 canonical submission remains blocked pending a fresh exact-main
  preflight, a matching external signature, immutable registration, and
  separate current authority for the exact submission.
- A replacement Physical Model Lock remains blocked. A local signed-lock design
  draft exists, but it is unreviewed, unapproved, unimplemented, unverified,
  and grants no authority.
- Defect `147042` still requires governed additional evidence or a site visit
  for dimensions, obscured boundaries, exact substrate/material proof, labels,
  and opposite-face continuity.
- Phases 9-14 remain blocked for the current real-report estimate because it has
  no canonical Physical Model or active replacement lock.
- Private-source publication and complete approved productivity coverage remain
  incomplete; technical and labour decisions must fail closed where authority
  is missing.

### 2.7 Deprecated or superseded

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

### 3.1 Representative v17 execution

The retained package
`phase8-rollback-147042-full-report-v17-20260823` executed from source revision
`7801636`. It resolved all 31 required linked originals across 41 report photo
occurrences, supplied four target-defect originals to four proposal-only
inference stages, and stopped at `VISUAL_PROPOSAL_BLOCKED`.

The stop was correct safe abstention, not a runtime failure. It produced seven
human-review items and four unresolved blind observations. The caller-owned
transaction was rolled back and the protected state remained 10 Defects, 128
EvidenceSources, and zero canonical Openings, Services, links, or active locks.
No canonical submission or Physical Model Lock occurred.

Offline recovery v6 reports
`RECOVERED_HASH_VERIFIED_LOCAL_TRANSCRIPTS`. It verified package, receipt,
session-key, transcript-payload, and final-domain bindings without rereading
the report/images and without retrieval, inference, canonical writes, or a
lock. Local session history remains mutable, and Gateway authentication, tool
attestation, response identity, and external transport were not replayed.

### 3.2 Human review v2

The retained hash-bound local response records Slayde Tana's 24 August
contextual review with no site visit. Its exact item-coverage validation
accounts for all seven review items and four unresolved observations once.
Hash, schema, binding, and item-coverage validation passes for a proposal-only
artifact containing five Openings, six Services, and six Opening-Service links
for defect `147042`; it does not independently prove physical truth.

The review confirms the separate O-01/O-03 relationship, the same-location
photo relationship, two separate flexible-duct wall openings, the O-02 shared
service group, the O-03 cable bundle, and two flexible ducts. It remains
`ADJUDICATED_PROPOSAL_ONLY_WITH_LIMITATIONS`: dimensions, depth and obscured
boundaries, exact substrate composition, service labels, documentary material
proof, and opposite-face continuity remain unresolved.

Creating and validating the v2 record performed no report/image retrieval,
runtime inference, database read/write, Gateway call, canonical submission, or
lock. The records are retained under:

- `data/real-uat/20260823-phase8-rollback-representative-147042-full-report-v17/human-review-response-v2/`; and
- `data/real-uat/20260823-phase8-rollback-representative-147042-full-report-v17/human-adjudicated-proposal-v2/`.

### 3.3 Historical whole-estimate preflight

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

The 24-Service count is the normalized canonical row count. It is a historical
whole-estimate proposal, not the selected-defect v2 5/6/6 result. Any historical
22-service-group description is a different pre-normalisation grouping measure
and must not be presented as the same count. The v6 preflight is not accepted
physical truth or reusable admission authority.

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
4. The representative v17 run completed and safely blocked with protected state
   unchanged. Issue #42 remains open and its pending-run wording is stale; the
   pushed `b422240` package still requires current-main review.
5. Current-main expiry validation may lack the dirty branch's explicit 900-second
   maximum admission lifetime. This is a candidate security hardening task to
   verify and, if needed, forward-port with dedicated tests from clean `main`.
6. Shared-main lock completeness rejects a blank Opening with a Service link,
   but its initial-submission schema and the checked legacy
   `physical_scope.py` lack the same early contradiction guard.
7. Legacy Package-15 naming, singular technical-release pinning, and a Service
   quantity default of 1 remain compatibility/schema debt in branch-local code.
8. The governed private knowledge source pack is unavailable in this checkout,
   and approved productivity coverage is incomplete for all FIREFLY activities.
9. Output renderers exist, but the current estimate has no eligible snapshot and
   no representative current-estimate PDF/XLSX output was inspected.
10. OpenClaw issue #43 tracks development-dependency advisories; shipped plugin
    dependencies were separately reported clean. Recovery, adversarial security,
    scale, and production monitoring evidence remain incomplete.
11. Observation, Interpretation, SubstratePlane, and EngineeringRequirement are
    workflow concepts rather than all being first-class persisted entities.
12. The Technical Authority Registry is a typed/static FIREFLY foundation, not
    a completed persistent multi-manufacturer production registry.
13. The signed lock-admission document, visual receipt, evidence-family,
    technical-compatibility, and source-release-contract work remain
    uncommitted current-main candidates rather than approved architecture.

## 6. Verification performed for this reconciliation

- Refreshed Git/GitHub references and inspected branch, upstream, open PR/issue,
  divergence, staged, unstaged, and untracked state.
- Classified all 46 tracked modifications and the substantive untracked files;
  no pre-existing implementation file qualified for this commit.
- Ran the full current dirty-tree test collection with isolated temporary paths
  and plugin autoload disabled: 494 tests across 63 collected groups passed.
- A retained earlier run of 125 tests directly affected by the pre-existing
  tracked implementation diff passed; the fresh full run subsumes that set.
- Ran the project/knowledge alignment audit: 0 hard errors and 4 warnings
  (missing private source pack, legacy Package-15 field, singular technical
  pinning, and Service quantity default).
- A retained `classifire doctor` run completed and its database connectivity/
  read check passed; it did not establish migration compatibility. Private
  Package 14/15 and raw-calculator checks remained unavailable because their
  governed source artifacts are absent.
- Confirmed the local source graph has one Alembic head at `0007`. The immutable
  read-only database query recorded on 2026-08-23 found the target database at
  `0008` with the estimate unchanged; this checkout remains barred from writes
  or migrations.
- Retained exact-main evidence records 292 full tests, 107 related tests, and 42
  focused linked-retrieval/runner tests passing for the current-main work.
- The pushed `b422240` branch records 332 full and 145 focused tests passing,
  changed-path Ruff/mypy passing, and no medium/high Bandit findings.
- The separate uncommitted current-main worktree passed a fresh 362-test full
  run across 52 collected groups; retained focused Ruff results also pass. This
  is a different source scope.
- Retained v17 receipt validators pass. A fresh human-review-v2
  hash/schema/binding/item-coverage validation passed against the retained
  inputs, and its no-write fields were inspected directly.
- Fresh `git diff --check` passed. Retained Ruff inspection of the pre-existing
  tracked diff reported 290 findings and 24 files needing formatting.

No canonical data, admission, registration, submission, lock, deployment, or
release operation was performed during this documentation review.

## 7. Local-change commit classification

### Category 1 - created by this review and intended for commit

- `docs/PROJECT_STATE.md`
- `docs/CLASSIFIRE_ARCHITECTURE.md`
- `docs/CLASSIFIRE_ROADMAP.md`
- `docs/SESSION_HANDOFF.md`

### Category 2 - pre-existing, relevant, complete, and suitable for this commit

None.

### Category 3 - deliberately left untouched

- All 46 pre-existing tracked implementation modifications.
- Untracked legacy/divergent admission services, scripts, migrations, and tests.
- Byte-identical copies of files already published on shared `main`.
- The complete 75-path separate current-main worktree.
- `AGENTS.md`, `docs/GOAL.md`, unrequested local runbooks, generated PDFs,
  editor files, `agent-definitions/`, and the logo asset.
- Temporary worktrees/caches, SDK/JDK/Gradle/tool bundles, APK/build artifacts,
  database copies, WAL/SHM files, UAT receipts, and customer/private evidence.

## 8. Next valid task

Do not rerun unchanged inference and do not canonicalise the limited proposal.

The next repository action is a focused review/pull request for the already-
pushed `b422240` representative package onto current main, followed by an
issue #42 update. Then split the 75-path current-main worktree into bounded
review slices, beginning with durable human-review/provenance and visual-
receipt governance before downstream technical or source-library work.

The physical case still requires governed additional evidence or a site visit
for dimensions, obscured boundaries, exact substrate/material proof, labels,
and opposite-face continuity. Only a semantically accepted model may proceed
to a fresh preflight. External signing, registration, canonical submission,
and any signed lock remain later, separately authorised operations.
