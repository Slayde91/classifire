# CLASSIFIRE Session Handoff

**Verified:** 2026-08-30 (AEST)

**Status:** Pre-production prototype; shared main has controlled Phase 8 foundations, but no approved canonical Physical Model or active replacement Physical Model Lock.

This handoff is a factual audit record. It does not grant authority to run inference, retrieve report evidence, write canonical data, sign or register an admission, create a lock, deploy, release, merge, or open a pull request.

## 1. Verified shared state

- `origin/main` is `c8b06d17678b58f49f2ea816f3b12ba2e4af0095`
  (PR #79). The application baseline is `20cb72a`; `db404b3` later hardened
  human-session revocation; PR #79 adds only the reviewed root-recovery decision.
- Current shared-main Alembic state has one head: `0009_visual_validation_receipts` on `legacy_adjudicated_lineage`. The technical-intake candidate migration is not on main.
- A focused current-main suite covering human-session security, evidence-family review, human-adjudicated proposal, visual evidence, and linked visual runs passed: **48 tests**.
- Open GitHub work remains reviewable rather than automatically mergeable: PR #75 is open; PRs #9-#13 are retained draft stack work; issues #42 and #43 are open. Issue #42 still has stale site-visit-first wording.
- Current main has no GitHub workflow, recorded Actions run, or PR status-check rollup. Mergeability is not CI evidence.
- GitHub's branch-protection endpoint returned a plan-limited 403, so this audit
  does not claim that main is protected or unprotected.

## 2. What must not be used as a publication source

The primary checkout is on `gpt/phase8-linked-original-images` at `de0cc5a`. It is **not** a safe branch for staging, committing, or merging:

- it is 378 commits ahead and 141 commits behind `origin/main`;
- it has an active interrupted cherry-pick for `c3e4c810`;
- four files are unmerged: `phase8_linked_visual_run.py`, `phase8_visual_evidence.py`, and their two tests;
- it has 46 unstaged tracked modifications (+1,668/-894) and 14 staged added files (+3,183), plus generated/untracked artefacts.

PR #79 records the isolated decision to keep the accepted current-main versions
of the four conflict paths and not transplant the stale cherry-pick. It does not
resolve or clean the root itself. Do not run bulk staging, clean, reset, force
operations, or normal publication from that checkout. This audit deliberately
did not modify it.

## 3. Current work, classified honestly

| Workstream | State | Meaning |
| --- | --- | --- |
| Shared-main Phase 8 foundations | **Merged and focused-tested** | Controlled evidence, visual-proposal, review, and rollback safeguards exist for their stated scope. They do not authorise canonicalisation or release. |
| Root Phase 8 continuation | **Quarantined / superseded as a build path** | The recovery decision is complete in PR #79. The conflicted checkout remains evidence only and is no longer the next current-main blocker. |
| Report assessment | **Three overlapping local candidates** | Quote review adds `property_assessments`; field inference adds `field_assessments`; report context mixes a much larger storage/API/UI/package surface. Focused candidate tests passed, but no single contract is published. |
| Cable semantics | **Local candidate only** | Bundle quantity counts bundles, cable count is separate, an indefensible count is null/Unknown with a required small/medium/large bundle class, and cable trays remain trays with their own dimensions. |
| Report intake | **Broad local candidate / blocked on containment and ownership** | Stored reports are not project/estimate-bound, use a conflicting evidence purpose, and do not prove an atomic clean-byte read. Do not expose its generic readout/UI yet. |
| Governed technical intake | **Separate pushed candidate plus local continuation** | `d76562e` and `0edeaac` are not on shared main. Their worktree has proposed `0019` and substantial uncommitted follow-on material, so it is not a clean merge candidate. |
| Production hardening | **Local-only commit** | `a3de490` is unpushed, broad, one commit ahead and three behind main. Main remains pre-production with unconditional schema/seed startup and warning-only production findings. |
| Report review / UAT | **Proposal-only, authority-gated** | A report package can support cautious evidence assessment, but it cannot create technical compatibility truth, commercial truth, a canonical model, a lock, or a release. |

## 4. Start Here / Next Session

**Recommended first task:** reconcile one bounded proposal-only report assessment
contract on a clean branch from `c8b06d1`.

### Prerequisites

1. Create or reuse a clean current-main worktree. Do not use or modify the root.
2. Compare the quote-review, field-inference, and report-context candidates
   without copying any candidate wholesale.
3. Keep report ingestion, storage, API/UI, technical selection, pricing,
   canonical submission, and lock creation outside this first slice.

### Relevant files

- `src/classifire/services/phase8_property_assessments.py`
- `src/classifire/services/phase8_proposal_review.py`
- `src/classifire/services/phase8_visual_proposal.py`
- `src/classifire/services/phase8_visual_prompts.py`
- `src/classifire/services/visual_validation.py`
- the corresponding `tests/test_phase8_*.py` files

### Implementation order

1. Select one public assessment name and schema. Use the stronger
   physical-field binding from `property_assessments`, while preserving explicit
   credible alternatives and unit/range handling from `field_assessments`.
2. Enforce Confirmed, Approximate, Inferred, and Unknown states. Approximate and
   Inferred require confidence, reasoning, and evidence; Unknown is used only
   after defensible estimation is exhausted.
3. Make bundle quantity, individual cable count, bundle size class, and cable
   tray dimensions separate fields. Always assess cable count; use null plus
   Unknown when it cannot be defended, and then require small/medium/large.
4. Recompute and verify proposal/receipt hashes and reject every evidence
   reference outside the allowed manifest.
5. Choose an explicit proposal-policy version and prove how retained v1 receipts
   remain verifiable, or document and test their intentional retirement.
6. Render and inspect one per-defect review containing provenance, limitations,
   confidence, reasoning, credible alternatives, and unresolved facts.

### Suggested validation

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
& C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest tests/test_phase8_property_assessments.py tests/test_phase8_proposal_review.py tests/test_phase8_visual_proposal.py tests/test_phase8_human_adjudicated_proposal.py tests/test_phase8_human_reference_comparison.py tests/test_phase8_linked_visual_run.py tests/test_phase8_openresponses_transport.py tests/test_phase8_representative_run.py tests/test_phase8_visual_evidence.py tests/test_phase8_visual_runtime.py -q -p no:cacheprovider --basetemp C:\CLASSIFIRE\.tmp\pytest-assessment-contract
```

Also run Ruff on changed Python, `git diff --check`, tampered-hash and
out-of-manifest negative tests, historical-receipt fixtures, and bundle/tray edge
cases.

**Done means:** one small current-main diff, one schema and policy version,
fail-closed hash/manifest binding, the required evidence and cable semantics,
an inspected review record, passing affected tests, and no canonical or
downstream authority interface.

## 5. Then, in order

1. **Reconcile shared-byte containment.** Extract the narrow atomic-quarantine
   dependency from the technical-intake candidate. Prove clean-to-FOUND
   propagation and read/download/preview races in disposable two-session
   PostgreSQL tests.
2. **Extract project-owned report intake.** Use `project_evidence`, bind every
   stored file/package to a project or estimate, fail cross-project reads, and
   separate immutable storage/provenance from package preparation and inference.
3. **Continue Draft technical materialization separately.** Review proposed
   migration `0019` without silently activating a `TechnicalVariant`.
4. **Review `a3de490` on current main.** Make production startup migration-only
   and fail closed on unsafe configuration/admission defaults; package migrations
   for installed operation.
5. **Review or supersede PR #75 independently.** A mergeable label is not
   acceptance evidence.
6. **Add minimal secret-free PR validation.** Run the agreed Pytest policy, Ruff,
   and Alembic one-head check; prove both a deliberately failed check and a
   reproducible passing check.
7. **Only then consider a fresh controlled report-only review.** It needs
   separate run authority and a per-defect review with report/page/image
   provenance, limitations, evidence labels, confidence, alternatives, and
   unresolved technical compatibility.
8. **Keep canonical UAT, signed lock admission, downstream technical/commercial
   work, deterministic snapshots, deployment, and Human Release behind their
   documented prerequisites and separate authorities.**

## 6. Report-only evidence rule

For a proposal-only review, use the supplied report package first: report text, defect register, photographs, annotations, drawings, page context, visible scale clues, repeated items, and normal industry dimensions where they do not contradict evidence. Do not default a field to Unknown solely because it lacks an exact measurement.

Label each conclusion as **Confirmed**, **Approximate**, **Inferred**, or **Unknown**, and give a confidence level for Approximate or Inferred values. Ask for extra evidence only after these methods are exhausted, or where confirmation is essential to a later governed technical or commercial decision. A site visit is one possible confirmation route, not the immediate default.

## 7. Important architectural boundary

The required order remains:

**Evidence -> physical model proposal -> technical-system search -> compatibility validation -> commercial applicability -> quantities/labour -> reconciliation -> estimate/scope -> human release.**

A rate, a product, chat context, or a proposal-only visual inference cannot make a technical system compatible or turn uncertain physical facts into approved truth. Keep uncertain facts explicit and do not let transient inference overwrite approved data.

## 8. Audit verification performed

- fetched and reconciled the current remote branch and open pull requests;
- checked root branch divergence, interrupted cherry-pick, conflict paths, and working-tree classifications without changing them;
- checked the current-main migration head, production startup, upload/storage,
  technical approval, snapshot, and deployment/CI boundaries;
- inspected the separate report-assessment, report-context, technical-intake,
  production-hardening, and PR #75 candidate worktrees;
- ran the selected focused suites in the report-assessment, report-context, and
  technical-intake candidates successfully for their local candidate boundaries;
- ran 48 focused current-main tests successfully; and
- distinguished the historical PR #74 380-test result from the current 48-test
  focused audit result.

No canonical database, report package, model endpoint, OpenClaw token, external inference service, deployment, or root source file was changed by this audit.

## 9. Publication record

This handoff was prepared in the isolated
`docs/project-audit-20260830` worktree from current `origin/main`. The
publication scope is exactly:

- `docs/PROJECT_STATE.md`
- `docs/CLASSIFIRE_ARCHITECTURE.md`
- `docs/CLASSIFIRE_ROADMAP.md`
- `docs/SESSION_HANDOFF.md`

The conflicted root, all report-assessment/report-context candidates,
technical-intake continuation, `a3de490`, the dirty PR #75 continuation,
customer evidence, generated artefacts, and every other local worktree remain
excluded and untouched.
