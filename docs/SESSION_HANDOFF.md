# CLASSIFIRE Session Handoff

**Verified:** 2026-08-28 (AEST)

**Status:** Pre-production implementation; validated technical-intake candidate
pushed to its Git feature branch, with external pull-request review and
operational UAT still outstanding

This handoff records the pushed implementation candidate and its final
validation evidence. Implementation commit
`d76562e54a7f208c2cab8ea1e9f598065f8e5151` was pushed. This documentation
record cannot embed the hash of the commit that contains it; the final Git
commit/push report and read-only branch ref record that hash. This handoff does
not authorise use of private reports, environment migration, inference,
approval, registry publication, admission signing or registration, canonical
submission, Physical Model Lock creation, pull-request creation, merge,
deployment, or release.

Read this with [PROJECT_STATE.md](./PROJECT_STATE.md),
[CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md),
[CLASSIFIRE_ROADMAP.md](./CLASSIFIRE_ROADMAP.md), and the
[Technical Intake Draft v1 contract](./TECHNICAL_INTAKE_DRAFT_V1.md).

## 1. Repository position

- Verified shared-main baseline:
  `01925237f953275244f2b63e54564533bee81910` (PR #78 merge).
- PR #78 includes the earlier Phase 8 foundations and runtime revocation of
  authenticated authority when a human account becomes inactive.
- Current isolated branch:
  `gpt/technical-intake-draft-boundary-20260827`, based exactly on that
  shared-main commit.
- There were no prior unpushed commits: the branch was exactly at
  `01925237f953275244f2b63e54564533bee81910` before implementation commit
  `d76562e54a7f208c2cab8ea1e9f598065f8e5151`
  (`feat: add governed technical intake and shared malware containment`).
- That implementation commit was pushed successfully to
  `origin/gpt/technical-intake-draft-boundary-20260827`; local and upstream
  refs were equal at the implementation point. This record intentionally does
  not name its own containing commit; use the final Git commit/push report and
  read-only branch ref for the final tip.
- The primary checkout at `C:\CLASSIFIRE` remains a divergent mixed legacy
  source and must not be cleaned, reset, bulk-staged, merged, or used as the
  publication base.
- PR #75 and issues #42/#43 remain separate open work. A reported mergeable
  state is not a safety review.

## 2. Pushed Git feature-branch candidate boundary

The current-main candidate is one integrated foundation:

- production configuration, readiness, packaged Alembic migration, upload,
  storage, malware-screening, and retained-file binding controls;
- an additive candidate migration lineage through head
  `0018_shared_malware_containment`;
- technical-source metadata, typed relationships, independent source review,
  Draft-only import, retirement, separately published registry releases, and
  pinned-release search;
- owner-bound multi-report batch intake with exact manifests, per-file
  isolation, replay receipts, retry, restore, and reconciliation;
- durable extraction runs, pages, artifacts, reservations, terminal receipts,
  and startup reconciliation;
- a default-off, test-only Linux-rootless OCI controller and dedicated worker
  boundary; and
- a versioned owner-bound TechnicalIntakeDraft UI that saves fields, locators,
  and evidence roles against one exact immutable PDF, supports stale-save
  recovery, and has no approval or publication controls.

Source-document review, TechnicalVariant review, and registry publication are
separate audited authority boundaries. Extraction, import, and Draft save/resume
cannot make data runtime-eligible. The ordinary coarse configuration link was
removed; its retained compatibility route cannot submit UI-policy variants for
review.

### Shared duplicate-byte containment

Exact duplicate clean bytes share one verified StoredFile, while each
TechnicalDocument retains its own identifier, metadata, relationship context,
and upload audit. If a later exact scanner-bound upload or replay detects
malware, CLASSIFIRE quarantines that shared StoredFile and moves every
previously accepted linked
item across every affected batch to `needs_attention`. Item-, batch-, and
file-level audits bind the transition. Every document referencing those bytes
then fails clean-file download, review, preview, extraction, and Draft checks.
The history is retained, and no second copy is silently promoted as trusted.

## 3. Representative technical-report evidence

The first controlled template must cover eight explicitly reviewed document
families:

1. Full Fire Test Report.
2. Regulatory Information Report.
3. Fire Assessment Report.
4. Extended Application Report.
5. Field of Application Report.
6. Fire Engineering Report or Performance Solution.
7. Certificate or Summary of Assessment.
8. Test Certificate.

Do not infer a family from a filename.

Two separate structural evidence sets inform the current schema:

- an earlier set of eight supplied files, comprising three
  regulatory-information reports and five assessment or assessment-bundle
  reports, totalling 1,673 pages; and
- an additional attached set of ten Promat reports totalling 281 pages, every
  page of which was text-bearing in the structural inventory.

Neither set was ingested into the CLASSIFIRE database. The structural inventory
created no Draft, TechnicalVariant, Approval, or LibraryRelease.

References to NCC 2022, AS 1530.4:2014, and AS 4072.1:2005 in the additional set
are declaration-only reviewer-attention flags. Exact-reference presence is not
a decision that a document complies, is current, applies to a configuration, or
supports a technical conclusion. That requires retained source bytes, exact
field-level locators, competent governed review, and the later publication
gates.

The representative set remains incomplete because it has no retained
scanned/image-only source. A retained primary Full Fire Test Report is also
required before the template can be frozen.

## 4. Verification evidence

The exact implementation candidate has this final validation record:

- complete suite: **1,545 passed, 15 skipped, and 140 warnings in 3,181.77
  seconds**;
- focused catalogue/UI suite: **141 passed**;
- focused lock/review/containment suite: **154 passed**, with four new
  regression cases recorded;
- JavaScript harnesses: all success; and
- Alembic: one head, `0018_shared_malware_containment`.

Focused core Ruff passed, focused Mypy checked 26 files cleanly, and focused
Bandit reported no issues. Whole-tree checks are not clean and must not be
described as passes:

- Ruff: **207 findings**; verified baseline: **329**;
- Mypy: **47 errors in 9 files**; verified baseline: **101 errors in 11
  files**; and
- Bandit: **7 low, 0 medium/high**; verified baseline: **8 low, 0
  medium/high**.

The candidate's whole-tree numeric counts are lower than the baseline, but that
does not make the checks clean or prove the absence of semantic regressions.
The remaining findings are still technical debt.

A disposable local authenticated HTTP UAT used synthetic metadata and isolated
SQLite/storage. Health, login, the technical catalogue, and both synthetic
document details returned HTTP 200. The live HTML confirmed all eight current
upload families, kept three legacy types out of ordinary selection while
retaining a readable legacy record, and showed the current-minimum standards
warnings without inferring compliance. No supplied PDF was opened, copied, or
ingested.

Actual rendered-browser UAT is still unproven. Browser startup was blocked by
`windows sandbox failed: helper_unknown_error: setup refresh had errors`.
Authenticated HTTP inspection and successful JavaScript harnesses are useful
fallback evidence, not a rendered visual/interactions pass.

The structural inventories are not ingestion UAT. No real supplied report
entered the database and no governed locator-backed compliance decision was
recorded. Live PostgreSQL two-session concurrency, a stateful scanner
clean-to-FOUND transition, an eligible rootless parser, and rendered-browser UAT
remain outstanding.

## 5. Remaining technical-intake work

Before this candidate can be treated as operational:

1. Run two-session live PostgreSQL UAT across shared-byte upload, download,
   Draft, and review operations, including a stateful scanner transition from
   clean to FOUND for the same digest.
2. Exercise the default-off parser and startup reconciliation with an admitted
   image on an eligible rootless Linux host.
3. Retry authenticated rendered-browser Draft UAT in a browser runtime that can
   start successfully.
4. Add reviewer-owned intake revisions, configuration-family authoring,
   governed locator-backed decisions, and controlled candidate materialisation.
5. Complete the representative set with primary-test and scanned/image-only
   evidence, then freeze the versioned template and its mapping/exception
   package.
6. Prove that an approved candidate remains runtime-ineligible until a separate
   authorised publisher includes it in a release and an estimate pins that
   release.

Production preview still requires an approved renderer licence/security
decision and an enforced low-privilege sandbox. No admitted parser/OCR image or
production worker loop exists.

## 6. Phase 8 boundary remains unchanged

The completed 7+4 human review for the representative Defect must not be
repeated. It records a limited non-canonical 5/6/6 topology but leaves
dimensions, depth and obscured boundaries, exact substrate, service
labels/material proof, and opposite-face continuity unresolved.

The next Phase 8 evidence action remains a site visit or equivalent newly
governed evidence for those facts. Do not rerun unchanged inference or convert
the limited proposal into canonical truth.

The visual-validation receipt registry and exact no-write verifier are
shared-main safeguards, not semantic acceptance, signed lock admission,
canonical submission, or lock authority. External signing, admission
registration, canonical submission, Physical Model Lock creation, and every
downstream release remain separate operations requiring separate authority.

## 7. Start Here / Next Session

### First task

Run the first non-production operational UAT for shared duplicate-byte
containment. Use two independent sessions against disposable live PostgreSQL,
isolated storage, and a stateful ClamAV-compatible test service. Exercise the
same digest through concurrent upload/replay, download, Draft, and source-review
eligibility, then change its scanner-bound verdict from clean to FOUND. Prove
that containment is atomic, audited, and creates no technical, release,
canonical, or lock authority.

Do not create a pull request, merge, migrate a shared or production environment,
deploy, ingest a real report, approve technical data, publish a Technical
Authority Registry release, or create canonical/lock state without separate
authority.

### Prerequisites

- Work only in the isolated current-main worktree; preserve the mixed primary
  checkout.
- Start from the final pushed branch tip containing this documentation record.
  Verify that it contains implementation commit
  `d76562e54a7f208c2cab8ea1e9f598065f8e5151` and that the exact upstream ref
  matches before UAT.
- Confirm migration head `0018_shared_malware_containment` and one Alembic
  head.
- Use a disposable PostgreSQL database, disposable storage, and an isolated
  stateful scanner test service. Keep their credentials and paths out of
  retained documentation.
- Use repository-generated synthetic input only. Do not copy, open, or ingest a
  supplied report.
- Record initial and final TechnicalVariant, Approval, LibraryRelease, canonical
  model, admission, and Physical Model Lock counts.
- Keep parser execution default-off/test-only and preview production-disabled.

### Relevant files

- Status and sequencing:
  `docs/PROJECT_STATE.md`, `docs/CLASSIFIRE_ARCHITECTURE.md`,
  `docs/CLASSIFIRE_ROADMAP.md`, and this handoff.
- Draft contract:
  `docs/TECHNICAL_INTAKE_DRAFT_V1.md`.
- Intake and containment:
  `src/classifire/services/technical_intake.py`,
  `src/classifire/services/technical_intake_batch.py`,
  `src/classifire/services/technical_intake_draft.py`, and
  `src/classifire/services/malware_scanning.py`.
- Eligibility and review:
  `src/classifire/services/technical_document_review.py`,
  `src/classifire/services/technical_governance.py`,
  `src/classifire/technical_admin.py`, and
  `tests/test_technical_document_download.py`.
- Extraction safety:
  `src/classifire/services/technical_extraction.py`,
  `src/classifire/services/technical_extraction_executor.py`,
  `src/classifire/services/technical_parser_oci.py`, and
  `src/classifire/services/technical_parser_reconciliation.py`.
- UI:
  `src/classifire/templates/technical_intake_draft.html`,
  `src/classifire/static/js/technical-intake-draft.js`, and
  `src/classifire/static/js/technical-preview.js`.
- Persistence:
  `src/classifire/migrations/versions/0017_technical_intake_drafts.py`,
  `src/classifire/migrations/versions/0018_shared_malware_containment.py`,
  `src/classifire/models.py`, and
  `src/classifire/services/deployment_lineage.py`.

### Suggested validation commands

Run the read-only branch preflight from the isolated worktree:

```powershell
git status --short --branch --untracked-files=all
git rev-parse HEAD
git rev-parse '@{upstream}'
git merge-base --is-ancestor d76562e54a7f208c2cab8ea1e9f598065f8e5151 HEAD
git diff --check
git diff --stat origin/main...HEAD

$env:PYTHONPATH = (Join-Path $PWD 'src')
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Before operational UAT, run the focused containment preflight with a unique
temporary directory:

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp C:\CLASSIFIRE\.tmp\pytest-containment-uat-preflight tests/test_technical_upload.py tests/test_technical_intake_batch_service.py tests/test_technical_document_download.py tests/test_technical_intake_draft_service.py tests/test_malware_scanning.py
```

The 53-minute full suite and whole-tree static tools already have exact results
above. Rerun them only if source changes or the operational environment exposes
a defect that requires a code change; documentation-only changes do not
needlessly rerun them. If the worktree does not contain its own virtual
environment, use the verified repository environment explicitly while keeping
`PYTHONPATH` bound to this worktree's `src`.

Configure `classifire migrate`, `classifire doctor`, and `classifire start`
only against the disposable PostgreSQL/storage/scanner environment. Capture
redacted two-session request ordering, database outcomes, audit rows, authority
counts, and teardown. Never run the UAT migration against a shared or production
database.

### Blockers

- Pull-request creation, merge, environment migration, and deployment remain
  separate actions requiring separate authority.
- Live PostgreSQL two-session behaviour and the stateful clean-to-FOUND scanner
  path are unproven.
- There is no rendered-browser UAT, eligible rootless-parser UAT, or admitted
  parser/OCR image.
- No supplied report has been ingested and no governed locator-backed compliance
  decision exists.
- The representative set still lacks a retained primary Full Fire Test Report
  and a scanned/image-only source.
- Reviewer-owned intake revision, configuration-family materialisation, and
  Technical Authority Registry publication/pinned-runtime UAT remain unfinished.
- Whole-tree Ruff, Mypy, and low-severity Bandit debt remains; the exact counts
  are recorded in section 4 and must not be described as clean passes.

### Definition of Done

The first operational UAT is complete only when:

1. a disposable environment reaches the single migration head
   `0018_shared_malware_containment` and passes readiness with its isolated
   PostgreSQL/storage/scanner dependencies;
2. two independent database sessions exercise the required duplicate-byte
   upload/replay, download, Draft, and review interleavings without split trust
   or lost updates;
3. a later exact scanner-bound FOUND result quarantines the shared StoredFile,
   moves every linked accepted item and affected batch to attention, blocks
   every referencing document from clean-file workflows, and retains complete
   audit history;
4. initial/final counts prove zero unintended TechnicalVariant, Approval,
   LibraryRelease, admission, canonical-model, or Physical Model Lock writes;
5. redacted digest, transaction, scanner, audit, and teardown evidence is
   retained without secrets, local capability paths, or customer material; and
6. failures remain fail-closed and any discovered defect returns to the normal
   code-review and verification loop before UAT is repeated.

Implementation commit `d76562e54a7f208c2cab8ea1e9f598065f8e5151`
was already pushed before this documentation reconciliation. This record does
not embed its own containing commit hash; the final Git commit/push report and
read-only branch ref provide the final branch tip. A later pull request requires
separate authority and external review.

## 8. Exclusions

Do not publish customer reports, filenames, references, extracted report
content, images, databases, receipts, OpenClaw history, local paths,
credentials, keys, tokens, signed URLs, supplier pricing, generated packages,
test caches, editor files, or unrelated legacy-root changes.
