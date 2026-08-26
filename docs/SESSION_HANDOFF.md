# CLASSIFIRE Session Handoff

**Verified:** 2026-08-27 (AEST)

**Status:** Pre-production implementation and controlled Phase 8 UAT

This handoff records current evidence. It does not authorise inference, retrieval, admission signing or registration, canonical submission, Physical Model Lock creation, deployment, release, commit, or push.

## 1. Current shared-main position

- Shared `main` and `origin/main`:
  `20cb72a14dd3b217cfac7670f047fdc385081990` (PR #74 merge).
- Merged Phase 8 work: representative rollback package and recovery,
  evidence-family and human-review validators, direct legacy-route test
  isolation, the durable visual-validation receipt registry/verifier, and the
  controlled `site_observation` evidence-intake contract.
- Reviewed PR #74 head `9f5dacacadfab02d6c9aaf8ac0add43c5eedfff8`
  and the merge commit have identical tree hash
  `6182cf5e3b3d577c9cc0622bf472b42b9e320b1f`.
- The merged `site_observation` contract binds each fact to a locator and writes
  the canonical payload digest into the existing audit event. It has no database
  migration, new writer, or live evidence.
- PR #75 remains open and is stacked on superseded site-observation commit
  `5874dade`, not the corrected and reviewed PR #74 head. GitHub reporting it as
  mergeable does not make it safe to merge; it requires a fresh review.

The primary checkout remains on `gpt/phase8-linked-original-images` at
`de0cc5a` with a divergent mixed working tree. It is a legacy evidence and
development source only. Do not bulk-stage, merge, clean, reset, or use it as a
publication base; its contents were not touched by this reconciliation.

## 2. Merged Phase 8 capability

Shared main includes the representative-run and recovery capability:

- an explicit rollback-only representative package bound to report, Git revision, executable source tree, snapshot, runtime identities, and no-write flags;
- verify-only package and snapshot checks plus a non-session-creating local Gateway readiness probe;
- full-report linked-original resolution with inference allowlisted to current retentions and explicitly mapped ready parents for the selected defect;
- report-derived parent-evidence checks for report hash, page, photo identity, native dimensions, and crop bounds;
- exclusion of nonvisual evidence from visual inference packets;
- a disposable SQLite transaction that always rolls back and rechecks protected-state fingerprints and counts;
- stricter proposal, blind-inventory, reconciliation, correction-authority, and blocked-receipt validation;
- content-safe human evidence-review requests; and
- fully offline recovery from hash-matched retained receipts and local OpenClaw transcripts without rerunning inference.

The merged representative package excludes unlisted same-Defect visual evidence,
requires a literal numeric loopback Gateway address before token-capable fallback
is constructed, rejects symbolic links and Windows junctions from the
fingerprinted source set on Python 3.11+, pins the relevant raw-byte inputs to
LF line endings, and reports the completion receipt's exact UTF-8/LF file-byte
hash. The original representative publication used an explicitly reviewed
28-file slice; later bounded PRs added provenance and durable-receipt work.

The package approval fields remain trusted human/governance metadata. They are not cryptographic, expiring, single-use production authority. This is controlled UAT tooling, not an untrusted production-ingestion or canonical-write path.

## 3. Retained v17 execution evidence

The authorised v17 full-report run completed linked-original retrieval and four proposal-only inference stages.

| Evidence | Verified result |
| --- | --- |
| Required linked originals | 31 of 31 resolved across 41 report photo occurrences |
| Target-defect visual evidence | 4 retained originals |
| Controller stages | 4 across separate Physical and Validator roles |
| Result | `VISUAL_PROPOSAL_BLOCKED` |
| Human-reference comparison | Correctly skipped because the proposal was not approved |
| Human review handoff | 7 review items and 4 unresolved blind observations |
| Protected state | Unchanged after rollback |
| Canonical submission | Not performed |
| Physical Model Lock | Not created |

The protected state before and after rollback was identical:

- fingerprint: `18768A9E368C7D0692A950303FCAC9401AFBE7C3632BE6A063FCB67B9671F8F1`;
- 10 Defects and 128 EvidenceSources; and
- 0 Openings, 0 Services, 0 Opening-Service links, and 0 active locks.

The Validator block is a genuine evidence limitation, not a runtime failure. A later human review resolved the visible service groupings and quantities, flexible-duct count, opening relationships, and close/wide photo relationship. Dimensions, depth and obscured boundaries, exact substrate composition, service labels and documentary material proof, and opposite-face continuity remain unresolved.

The v17 live run used source-tree fingerprint `5B00545F5A2A7F3F36930B008B3E0802AFB1EBA5D735A7B9123218B5E972CDE1`. Later recovery, review, provenance, and receipt hardening changed the source tree. V17 is therefore historical runtime proof for that exact run source, not a live execution proof for the later merged source.

## 4. Later human review v2 evidence

The retained v2 response accounts for all seven review items and four unresolved-observation items exactly once across six consolidated decisions. A separate local no-write validator returned `PASS` for a limited proposal-only record of one Defect, five Openings, six Services, and six links.

The review confirmed two questioned openings as separate openings in the same wall, the close and wide duct photographs as the same location, two flexible ducts through separate wall openings, one shared opening with a metal pipe/two PVC conduits/a cable bundle, and another opening with a visible three-cable bundle.

This remains human visual adjudication without a site visit. It is not an approved canonical model, and it does not settle dimensions, depth/boundaries, exact substrate, service labels/material proof, or opposite-face continuity. The v2 review and evidence-family validators are on shared main; the retained response remains local evidence, not canonical state or publication authority. Its recording and validation performed no report/image retrieval, runtime inference, canonical database read or write, Gateway call, admission, canonical submission, or lock.

## 5. Final-source offline recovery proof

The retained offline recovery was rerun as v8 after the completion-file hash correction and mechanical formatting:

- source-tree fingerprint: `EDBA8858B385BD521D43AB15FAE41C5291356985E47B1792ADC40A0ADD6A8D6F`;
- evidence-review request file SHA-256: `58200866211E15E49087986BC1E893DE5D377E1067E57B242B537A42E22B34E1`;
- recovery receipt file SHA-256: `D41A424A7D5500E596B73E340E713BC008D2C11830BEC979D1E164B268134BAF`;
- recovery script SHA-256: `69A926B057900D35F5A509874244A503A0C0CA062F39B72B6C22E4FA6A45B0E2`;
- output: exactly `evidence-review-request.json` and `recovery-receipt.json`; and
- retained-report/linked-original file reads, retrieval, inference requests, canonical submission, lock creation, and human-reference exposure: all false; bound local session transcripts were read.

Recovery proved the retained package/no-write receipt lineage, controller and proposal content bindings, deterministic session-key bindings, every successful transcript payload hash, and final blind/proposal/Validator domain validity. The historical v17 representative, controller, and proposal files predate raw-byte writer hardening, so recovery records their `LF_RENDERED_JSON_SHA256` bindings separately from their retained Windows file hashes.

Recovery did not make local OpenClaw history immutable and did not replay Gateway authentication, runtime tool attestation/audit, OpenResponses response identity, or external inference transport. It is hash-correspondence evidence, not cryptographic authentication of mutable local history.

No real report was rerun after final-source hardening.

## 6. Verification

Current validation evidence for the exact merged source tree:

- reviewed PR #74 head `9f5dacacadfab02d6c9aaf8ac0add43c5eedfff8`
  and merge commit `20cb72a14dd3b217cfac7670f047fdc385081990`
  have identical tree hash `6182cf5e3b3d577c9cc0622bf472b42b9e320b1f`;
- complete repository suite: **380 passed** with Python 3.12.10 and Pytest 8.4.2;
- focused evidence-file boundary suite: **14 passed**;
- Ruff on the changed API and test, Mypy on the changed API, Alembic one-head
  check (`0009_visual_validation_receipts`), and `git diff --check` passed;
- GitHub reported no status-check rollup for PR #74, so no CI result is claimed;
  and
- whole-repository Ruff and Mypy were not rerun for PR #74. Previously recorded
  inherited findings outside the changed paths have not been revalidated on
  current main.

The recovery v8 result remains successful historical hash-binding evidence for
its own source. The PR #74 site-observation contract is now on shared main.
Merging it did not create live evidence or authority, and no real report was
rerun after the later source hardening.

## 7. Exact next valid task

Do not repeat the completed 7+4 review. The next physical-evidence task for
the selected Defect is a site visit or equivalent newly governed evidence for
the remaining dimensions, depth/boundaries, substrate, labels/material proof,
and opposite-face continuity. Once retained as an immutable admissible
technical-evidence file, a suitably authorised user can register it against the
relevant Defect through the shared-main `site_observation` contract in an
authorised environment; this is evidence intake only.

Do not rerun unchanged inference or canonicalise the limited 5/6/6 proposal.
The durable visual-validation receipt registry and exact no-write verifier are
now shared-main safeguards; semantic acceptance and a signed lock-admission
boundary remain separate, unresolved architecture work. Only after the remaining
evidence is governed, the proposal is semantically accepted, and the applicable
boundaries are approved may a fresh preflight be considered. External signing,
admission registration, canonical submission, and lock creation remain later
operations requiring separate authority.

## 8. Authority boundaries and exclusions

This handoff records the merged shared-main position. Git history is authoritative for publication results. No deployment, admission, canonical write, Physical Model Lock, or release was performed.

Intentionally excluded from this work and any publication staging:

- every tracked or untracked change in the mixed primary checkout;
- files already present on `origin/main` or preserved on other remote candidate branches;
- root-only unreconciled or unsafe admission/UAT variants;
- `.env`, credentials, keys, tokens, signed URLs, and private signing material;
- customer reports, images, real-UAT packages, receipts, SQLite/WAL/SHM data, and OpenClaw session history;
- Android, Gradle, JDK, SDK, dependency, build, and test-cache artefacts;
- generated reports, editor/workspace files, `agent-definitions/`, and logo assets.

Any later repository change must begin in a clean exact-main worktree and use
explicit reviewed paths. Commit, push, pull-request, and merge authority remain
separate; never use bulk staging.
