# CLASSIFIRE Project State

**Verified snapshot:** 2026-08-27 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Shared `main` verified:** `1b3d7c976dd726a663c105e99d0b38ab22460d66`

**Documentation publication branch before this update:**
`docs/reconcile-project-state-20260825` at
`9823c6c9c483f03878c19f186074a759da2497f5`, equal to its remote and one
documentation-only commit above shared main

**Open evidence candidate:** PR #74 at
`9f5dacacadfab02d6c9aaf8ac0add43c5eedfff8`; open, unmerged, and exactly seven
files

**Open desk-quote candidate:** PR #75 at
`ef4425422a5d80387626697c1d8d99dcdd9e6bdc`; open and unmerged. It contains
PR #74's older `5874dadeac2bca97fdbf366967590e1539c148df` prerequisite, not the
current `9f5daca` correction.

This record distinguishes shared-main implementation, open pull requests,
pushed candidate branches, clean local integration evidence, uncommitted local
work, the protected mixed root checkout, and retained operational evidence.
Current source, tests, Git, and execution evidence outrank older documentation.

Nothing in this document authorises inference, customer-evidence use,
deployment, admission signing or registration, canonical submission, Physical
Model Lock creation, merge, or release.

## 1. Repository and Git position

| Scope | Verified state |
| --- | --- |
| Shared GitHub `main` | `1b3d7c9`; unchanged since PR #73 merged |
| Documentation branch | `9823c6c`; clean, pushed, no pull request before this update |
| PR #74 | `9f5daca`; two commits above main, seven files, open, GitHub reports mergeable/clean but has no status-check rollup |
| PR #75 | `ef44254`; three commits above main, 13 files, open, carries the old PR #74 commit and not its tightening correction |
| Legacy root | `gpt/phase8-linked-original-images` at `de0cc5a`, equal to its upstream, 129 main-only and 378 branch-only commits |
| Root operation state | Interrupted cherry-pick of `c3e4c810`; staged additions, unrelated tracked modifications, four unresolved `DU` paths, and more than 67,000 enumerated untracked paths |

The root checkout is not a safe staging, commit, merge, database-write, or
deployment source. Its four unresolved paths are:

- `src/classifire/services/phase8_linked_visual_run.py`;
- `src/classifire/services/phase8_visual_evidence.py`;
- `tests/test_phase8_linked_visual_run.py`; and
- `tests/test_phase8_visual_evidence.py`.

Do not resolve, abort, clean, reset, bulk-stage, or commit that checkout as part
of current-main work. Any still-useful root change requires path-level review or
reconstruction against a clean current-main worktree.

GitHub remains the canonical shared repository. Draft legacy-stack PRs #9-#13
remain open and must not be merged wholesale. Issues #42 and #43 remain open.

## 2. Completed on shared `main`

Shared main at `1b3d7c9` contains these completed foundations for their stated
boundaries:

- FastAPI, CLI, SQLAlchemy, Alembic, storage, audit, UI, import,
  release-pinning, calculation, snapshot, PDF/XLSX, and Mission Control
  foundations;
- canonical Defect, EvidenceSource, Opening, Service, Opening-Service link,
  Physical Model Lock, admission, submission-receipt, and visual-validation
  receipt records;
- migration head `0009_visual_validation_receipts`, following
  `0008_retire_legacy_initial_submissions`;
- protected-state fingerprinting, admission-bound one-shot initial
  canonicalisation, P-256 verification, immutable registration, idempotent
  receipts, and an explicit no-lock submission boundary;
- bounded visual correction, proposal-blind inventory, mandatory
  reconciliation, strict proposal receipts, retained-evidence adaptation,
  no-tool transport/runtime identities, and post-inference comparison;
- guarded linked-original discovery, verification, retention, and the bounded
  linked-original-to-proposal runner;
- the representative rollback-only package, content-safe review request, and
  offline recovery tooling;
- reviewed evidence-family and human-review validators; and
- the offline Android admission signer and recorded deployment/runbook
  foundations.

These are pre-production and controlled-UAT capabilities. Shared main does not
include the August 26 security stack described below.

Basic technical search, release records, estimating rules, line calculation,
snapshot locking, and output rendering also exist on main. They do not satisfy
the complete Phase 9-14 architecture: Repair Strategy Locks, system-derived
components, full approved productivity coverage, one-time commercial recovery,
independent full-estimate validation certificates, snapshot-backed output QA,
and explicit Human Release remain incomplete.

## 3. Current candidate work

### 3.1 PR #74 and PR #75

PR #74 adds strict `site_observation` intake at the existing evidence
registration boundary. Its current correction removes transient draft wording
and keeps the contract controlled, non-canonical, and non-authorising. It
requires an immutable admissible retained file, one bound Defect, capture and
governance provenance, per-fact locators, explicit uncertainty, and an audit
payload digest. It creates no Opening, Service, link, canonical model,
admission, or lock.

The current PR #74 branch documentation records a complete 380-test suite for
that exact head. GitHub exposes no CI status-check rollup; the fresh independent
evidence in this reconciliation is the 14-test focused boundary run described
below.

Its exact cumulative seven-file scope is:

- `docs/CLASSIFIRE_ARCHITECTURE.md`;
- `docs/CLASSIFIRE_ROADMAP.md`;
- `docs/PHASE8_SITE_OBSERVATION_EVIDENCE_CONTRACT.md`;
- `docs/PROJECT_STATE.md`;
- `docs/SESSION_HANDOFF.md`;
- `src/classifire/api/physical_model.py`; and
- `tests/test_physical_evidence_file_boundary.py`.

PR #75 adds an assumption-led desk quote. It is a qualified commercial proposal
only, not physical approval, technical selection, canonical estimating,
certification, admission, lock, or release. Because it contains PR #74's older
prerequisite commit rather than `9f5daca`, its effective evidence contract must
be recalculated and reviewed before it can be treated as the current dependent
candidate. The retained 5/6/6 desk quote remains nontechnical and must not be
used to approve that physical topology.

### 3.2 Pushed August 26 production-hardening candidate stack

The following linear stack is committed and pushed on topic branches but has no
pull request and is not shared-main implementation:

| Commit | Candidate boundary |
| --- | --- |
| `21585cabe50593426cc69527c6d6bd3cd49f6978` | Require active users for UI sessions |
| `5d347f9dd378dc8c200c036d52b52e3318a71ff0` | Server-side human-session revocation and migration `0010_human_sessions` |
| `2dc1687f960b01d7a05501868cd394c743323b5a` | Fail-closed production configuration and explicit bootstrap |
| `206390a523c355a1ee1c44138d4dae60c5e437e1` | Complete deployment-schema readiness checks |
| `38ed0e51a479bfed06db22de8706279b7373dcdc` | Malware quarantine for retained evidence |
| `cf219a20de471736c525c83427e23bd1757ff86f` | Durable malware-scan attestations and migration `0011_malware_scan_attestations` |
| `b81287018d5148488efaaeabb7b1ed7bfc7c68d6` | Bind visual inference receipts to current scan evidence |
| `8974963115b444d14002cf50ac1fabdce965ec00` | Validate every declared package photo row before retrieval |

The remote photo-inventory branch tip is `8974963`. Its tip commit changes six
files, but the branch is an eight-commit, 77-file cumulative stack above main;
it must not be described as a six-file branch.

A sibling pushed candidate at
`4c18cb25cdd01afdef94ce16644d73b6ff33bbf3` hardens deployment-lineage checks
for migration `0011`. The clean committed integration baseline on branch
`gpt/photo-inventory-deployment-integration-20260826` at
`e9b759e53a2d2e9c51bcc1d467ad33fcf24a4faf` combines the photo stack with that
sibling. It has no remote or pull request. Its Alembic graph reports one head,
`0011_malware_scan_attestations`.

These candidates add meaningful Phase 15 protection, but they have not been
reviewed or merged as one production architecture and have not been deployed.
Their linear dependency and large cumulative review surface require bounded,
ordered pull requests rather than treating the tip branch as one atomic fix.

### 3.3 Uncommitted isolated candidates

A separate worktree on branch
`gpt/xlsx-output-injection-integration-20260826`, based at `e9b759e`, contains a
reviewed two-file XLSX hardening candidate. It writes snapshot text literally,
disables automatic formula and URL conversion, and preserves numeric, boolean,
and blank cell types. It is unstaged, uncommitted, and unpushed. The committed
photo/deployment integration worktree remains clean.

Other isolated uncommitted work remains separate and not publication-ready:

- a four-file existing-database bootstrap-adoption candidate;
- an 18-file malware/provenance/recovery follow-on;
- an alternate deployment-lineage worktree with an untracked regression test;
- a 28-file CLASSIFIRE runtime-branding conversion;
- a seven-path PR #75 output/cache hardening candidate; and
- duplicate or superseded local experiments and empty topic worktrees.

The divergent root's staged, modified, conflicted, and untracked material is a
separate unsafe category. None of these implementation paths belongs in this
documentation commit.

### 3.4 Known linked-image byte-identity gap

Current linked-image processing does not yet guarantee that scanning, image
decoding, dimensions, and receipt hashes all derive from one bounded immutable
byte buffer. Several paths decode or scan one file read and later reopen the
same mutable path for hashing or dimensions. The
`preferred_verified_linked_path` path also performs an unbounded read before
the later image limit check. A path substitution or oversized padded image can
therefore cross boundaries that the architecture intends to bind exactly.

This is an implementation defect to correct with one bounded read and one
verified byte identity across the complete operation. It does not invalidate
the retained historical run evidence for its exact artifacts, but it prevents
claiming that the general linked-image boundary already provides immutable
single-buffer assurance.

## 4. Phase 8 physical evidence

The retained v17 representative run remains the latest real execution evidence:

| Evidence | Verified retained result |
| --- | --- |
| Required linked originals | 31 of 31 resolved across 41 report photo occurrences |
| Target-defect evidence supplied to inference | 4 retained originals |
| Controller stages | 4, with separate Physical and Validator roles |
| Visual result | `VISUAL_PROPOSAL_BLOCKED` |
| Review handoff | 7 review items and 4 unresolved blind observations |
| Protected state after rollback | Unchanged: 10 Defects, 128 EvidenceSources, 0 Openings, 0 Services, 0 links, 0 active locks |
| Canonical submission | Not performed |
| Physical Model Lock | Not created |

The later human-review-v2 record accounts for all seven review items and four
unresolved observations. A separate local no-write validator passes a
proposal-only record of one Defect, five Openings, six Services, and six links.
Neither result independently establishes physical truth. No site,
remote-supervised, or documentary follow-up evidence is currently available.
Dimensions, depth and obscured boundaries, exact substrate composition,
service labels and material proof, and opposite-face continuity remain
unresolved.

The historical 17-Opening/24-Service/24-link preflight is a different whole-
estimate, no-write artifact. It is not accepted topology, reusable admission
authority, or evidence for the selected-Defect 5/6/6 proposal.

## 5. Roadmap state

| Phase | Current state |
| --- | --- |
| 0-2 | In progress: repository consolidation, governance, and source-library release controls remain incomplete |
| 3 | In progress: shared controlled-writer/no-tool foundations exist; scan-bound transport is an unmerged candidate and changed deployment sources require revalidation |
| 4 | In progress: Mission Control remains a control plane, not canonical estimate state |
| 5 | In progress: one retained report path is proven; corrected PR #74 and photo-inventory hardening remain unmerged candidates; the linked-image single-buffer identity gap and multi-report/host proof remain |
| 6 | In progress and evidence-limited: the local 5/6/6 proposal remains non-canonical and site-dependent facts remain unresolved |
| 7 | In progress: rollback/safe-abstention and durable receipt foundations exist; scan-bound inference and signed lock enforcement remain unmerged/incomplete |
| 8 | Blocked on unresolved physical evidence, semantic acceptance, and separate canonical/lock authority |
| 8C | Planned; only governed preparation is permitted before its admission gates |
| 9-14 | Blocked by the missing accepted and locked Physical Model; basic main and richer legacy foundations are not phase completion |
| 15 | In progress: substantial security, session, configuration, schema, malware, deployment, photo-input, and XLSX candidates exist, but none of the August 26 stack is merged or deployed |
| 16 | Deferred: structural steel and complete fire-rated duct runs require separate design and evidence |

## 6. Current test and verification evidence

- Exact shared-main/PR #73 retained evidence: 345 full tests and 55 focused
  durable-receipt/migration/lock/admission-boundary tests passed, with static,
  security, Alembic, and diff checks recorded.
- Exact current PR #74 head: its branch documentation records 380 full-suite
  tests, and a fresh 14-test focused evidence-file-boundary run passed; Ruff,
  focused Mypy, and `git diff --check` passed. GitHub has no status-check
  rollup, so its `CLEAN` merge state is not a CI result.
- The exact committed `e9b759e` integration baseline, before the current XLSX
  edits, passed 858 full-suite tests, reported one Alembic head at
  `0011_malware_scan_attestations`, and had a clean Git diff.
- The separate `e9b759e`-based worktree with the uncommitted XLSX candidate
  completed the full local suite: 861 tests passed with exit code 0. Pytest
  then emitted a Windows temporary-directory cleanup warning; it did not
  change the successful test exit.
- The XLSX candidate separately passed 3 focused security tests, Ruff,
  formatting, focused Mypy, Bandit, and diff checks. Independent read-only
  review found no blocking defect after the merged-number correction.

These results apply to different exact source scopes. They do not make an
unmerged branch shared-main implementation or prove production deployment,
backup/recovery, monitoring, performance, scanner infrastructure, or live
database readiness.

## 7. Commit classification for this reconciliation

### Category 1 - created by this review and intended for commit

- `docs/PROJECT_STATE.md`
- `docs/CLASSIFIRE_ARCHITECTURE.md`
- `docs/CLASSIFIRE_ROADMAP.md`
- `docs/SESSION_HANDOFF.md`

### Category 2 - pre-existing implementation suitable for this documentation commit

None. Complete or promising implementation remains on its own committed branch
or isolated worktree and requires its own review history.

### Category 3 - deliberately excluded

- every staged, modified, conflicted, and untracked root-checkout path;
- all pushed August 26 implementation branches;
- the local integration and uncommitted XLSX candidate;
- the other uncommitted isolated candidates listed above;
- PR #74 and PR #75 source branches;
- customer reports, images, databases, receipts, session history, keys, tokens,
  signed URLs, SDK/build/cache artifacts, generated reports, editor files,
  agent definitions, and branding assets; and
- `AGENTS.md` and `docs/GOAL.md`, which remain root-local working guidance and
  are not part of the requested four-document scope.

## 8. Blockers and next valid tasks

1. Review PR #74 at its corrected `9f5daca` head and keep its exact seven-file,
   evidence-only boundary.
2. Recalculate PR #75 against the corrected PR #74 contract before reviewing
   the desk-quote functionality; do not use it to approve the 5/6/6 topology.
3. Review the August 26 hardening stack in dependency order through bounded
   pull requests. Keep migration `0010`, migration `0011`, deployment-lineage,
   scan-bound transport, photo-inventory, and XLSX changes traceable to their
   exact commits and tests.
4. Correct the linked-image exact-byte gap so scan, decode, dimensions, hash,
   and transport all use one bounded immutable byte buffer, with regression
   tests for path substitution and oversized padded images.
5. Keep the remaining physical facts unresolved until governed additional
   evidence or a site visit exists. Do not rerun unchanged inference.

Canonical preflight, external signing, admission registration, canonical
submission, Physical Model Lock creation, deployment, merge, and release remain
later operations with separate authority.
