# CLASSIFIRE Master Roadmap

**Document status:** Active working roadmap

**Roadmap version:** 2026-08-23 r7

**Product status:** Pre-production prototype and controlled UAT build

**Supersedes:** The 18 August 2026 r2 Master Roadmap as the current working plan. The supplied PDF and earlier roadmap revisions remain immutable reference and decision-history records.

**Scope:** Passive-fire evidence intake, physical-model automation, technical selection, quantities, commercial recovery, validation, output, release, and production hardening.

## 1. How to read this roadmap

This roadmap separates approved direction from observed implementation state.

| Label | Meaning |
| --- | --- |
| **Verified complete** | Supported by current implementation, test, or execution evidence. |
| **In progress** | Approved work with material implementation or evidence, but incomplete exit criteria. |
| **Planned** | Approved direction that has not yet started. |
| **Blocked** | Cannot proceed without an upstream condition, evidence, or explicit authority. |
| **Needs evidence** | A claim, metric, or operational state not yet independently proven. |

The current code, test results, receipts, and live-state checks take precedence over older roadmap wording for factual status. The roadmap still controls sequencing, architecture, and acceptance criteria.

Nothing in a report, fixture, receipt, or attached reference document grants authority to make canonical writes, train a model, publish data, or release an estimate. Those actions require their own explicit approval and gates.

## 2. Executive status

### 2.1 Current product position

CLASSIFIRE has a controlled evidence-to-physical-model prototype. Retained legacy-branch execution evidence shows report retention, image reconciliation, proposal-only Opening-Service modelling, an independent visual challenge, and protected-state checks. Current shared main contains the canonical runtime, admission-bound writer, bounded visual correction guard, proposal-blind inventory, mandatory blind-reconciliation rules, and a deterministic proposal-only controller/receipt boundary. It does not yet contain the production inference transport, retained-evidence adapter, validation-only comparator, and linked-original resolver required to reproduce the complete historical proposal-only inference workflow.

The prototype is not production-authorised. It does not yet have a corrected active Physical Model Lock for the current real-report UAT, and all technical, quantity, commercial, snapshot, output, and release work remains downstream-blocked by that missing lock.

### 2.2 Verified recent advances

| Area | Verified current position |
| --- | --- |
| Evidence integrity | Proposal-only runs protect the canonical estimate with a component-level protected-state fingerprint rather than relying on a whole-database file hash. |
| Image quality | The report pipeline can discover report-provided linked originals, validate that they correspond to the displayed image, prefer verified full-resolution detail, and retain lower-resolution page context. |
| Image provenance | Duplicate, crop, annotation, and page-context relationships are retained rather than silently collapsed when their visual information differs. |
| Visual safety | Current main enforces bounded correction semantics, fail-closed strict-schema visual receipts, proposal-blind inventory structure, mandatory reconciliation, ordered role separation, and protected-state checks after every inference exchange. Live current-main execution remains pending a real transport and retained-evidence adapter. |
| Proposal-only safety | The controller has no database, canonical-write, admission, signing, registration, lock, device, or deployment capability; its inference requests expose no tools. Gateway preflight separately remains fail-closed. |
| Reconciliation | The human-reference comparator binds proposal/final-state inputs by path and hash and detects topology/substrate swaps rather than matching disconnected multisets. |
| Human adjudication | A provenance-bound, offline adjudicated proposal revision exists for the current UAT. It records human decisions separately from runtime inference and leaves canonical state unchanged. |
| Controlled-writer Gate A | Latest code-bearing shared-main baseline `82ab568` has a reproducible admission-only plugin artifact and clean candidate fingerprint `73A73C21...41EE5`. The audit itself remains review-only. |
| Gates B-F deployment | Migration `0008`, public-key policy, least-privilege scope reconciliation, plugin `0.5.0` upgrade/restart, and synthetic fail-closed validation are complete locally. The real UAT estimate remains unchanged and has no admission, submission receipt, canonical model, or active lock. |
| Android admission signer | The non-debuggable `0.2.1-local` release APK is installed under the approved APK certificate. `governance-p256-02` exists as a hardware-backed, non-exportable P-256 key; only its independently verified public proof is configured in CLASSIFIRE. No admission has been signed. |

### 2.3 Current Phase 8 evidence position

The full-resolution proposal-only UAT produced a visual-validated proposal. The subsequent offline adjudicated revision contains **17 Openings and 22 Service groups**. It is not a canonical physical model.

The adjudicated proposal comparison passes against the versioned adjudication record. The historical human-reference comparison remains a diagnostic with three explained differences:

1. Defect 147038 retains an unknown material for a separate pipe rather than inventing PVC.
2. Defect 147039 follows the clarified wall penetration instead of the older fixture's concrete-slab classification.
3. Defect 147042 preserves the clarified five-opening topology and explicit uncertainty rather than forcing the older fixture's service grouping or substrate assumption.

These differences must remain explicit. Passing a count comparison alone is never sufficient for a Physical Model Lock.

### 2.4 Immediate governing constraints

- The canonical estimate must remain unchanged until a controlled canonical preflight passes and a separately authorised submission occurs.
- The historical human fixture and any adjudication for a report are validation-only; they must not be exposed to that report's runtime inference or used as hidden prompt answers.
- Full-resolution originals are preferred when verified. Lower-resolution thumbnails, crops, labels, and page renders remain contextual evidence when they preserve information not present in the original.
- Human adjudication is an exception mechanism for genuine conflict or ambiguity. It is not the intended routine input for every estimate.
- Routine live reports and their verified outcomes are intended to improve CLASSIFIRE through a governed continual-learning pipeline. They must not directly self-modify the model during the same live case.
- A trained or improved model never bypasses protected-state checks, independent validation, Physical Model Lock rules, or human-only final release.

### 2.5 20 August 2026 implementation reconciliation

The current report UAT remains **proposal-only**. The adjudicated revision has 17 Openings and 22 Service groups, but no real admission has been registered, no canonical Opening-Service-Link model has been written, and no replacement active Physical Model Lock has been created. Technical selection, quantities, commercial recovery, snapshot, output, and release therefore remain correctly blocked.

The original Phase 8 branch contained valuable UAT work but mixed physical, commercial, agent, plugin, and deployment concerns. The implementation is being rebuilt as a clean foundation stack rather than published wholesale from the dirty legacy worktree:

| Foundation workstream | Roadmap phases supported | Recorded factual status | Remaining evidence before completion |
| --- | --- | --- | --- |
| Layer 1 - runtime foundation | 0, 15 | **Merged** through PR #16 and present on shared main. | Broader CI and production-hardening evidence. |
| Layer 2 - physical foundation | 1, 6, 8 | **Merged** through PR #17 and present on shared main. | Complete Phase 8 canonicalisation and the separately governed lock boundary. |
| Layer 3 - least-privilege agents | 3, 15 | **Merged and locally deployment-validated** through PRs #18, #20, #25, and Gates D-E. | Revalidate in each different deployment environment. |
| Layer 4 - P-256 admission/writer | 1, 3, 6, 8, 15 | **Deployment validated through Gate F**; writer, reconciled journal, key policy, and runtime boundary are active locally. | Fresh preflight, external signature, offline registration, and separate one-time write authority. |
| Controlled plugin rebuild | 3, 15 | **Verified complete for the local deployment.** Exact-main `0.5.0` is installed under `phase8-admission-only`, restarted, and boundary-tested. | Revalidate for any different environment or source revision. |
| Controlled canonicalisation | 8 | Blocked at the intended governance boundary. | Fresh preflight, external signature, admission registration, and separate write authority. |
| Signed lock-admission | 1, 6, 8 | Not designed as a completed boundary. | Separate signed lock design and authority. |
| Automated Physical-Model Accuracy Programme | 8C | Planned - not started. | Working prototype and the programme admission gate. |

The former clean foundation stack is now merged through Layer 4. The dirty `gpt/phase8-linked-original-images` worktree remains an evidence/development source, not a safe bulk staging source. PRs #45-#49 reconciled the pure visual validation, bounded correction, blind inventory, blind reconciliation, malformed-input handling, and proposal-only controller/receipt onto shared main. The production inference transport, retained-evidence adapter, validation-only comparator, and linked-original resolver remain tracked in [GitHub issue #42](https://github.com/Slayde91/classifire/issues/42). Legacy stacked PRs #9-#13 must not be merged directly; each remaining valid change needs review against current abstractions, focused transplantation, and current-main tests.

The controlled-write plugin's shipped dependency set currently has zero npm audit findings. Ten findings remain in the latest available OpenClaw development dependency, with no safe upstream OpenClaw release yet available. [GitHub issue #43](https://github.com/Slayde91/classifire/issues/43) tracks the update; forced dependency downgrades or overrides are not an accepted remedy.

### 2.6 Controlled canonicalisation and signer direction

The first canonical write must be admission-bound. A signed admission binds one estimate, one normalized Opening-Service-Link payload, one protected-state fingerprint, source/adjudicated artefact hashes, policy and implementation hashes, issuer/key identity, purpose, and expiry. The writer consumes that admission once, rechecks the current state in the write transaction, writes only the sealed physical facts, and **does not create a Physical Model Lock**.

P-256 is the approved production admission protocol. The Samsung Galaxy S25 Ultra now holds `governance-p256-02` as a hardware-backed, non-exportable Android Keystore key. Its public proof was recovered read-only and independently verified before CLASSIFIRE was configured to trust that key only for issuer `classifire-governance`. The prior debug-app keys were retired with the debug app. No admission has been signed or registered, and the private key has not left the handset. The prior Ed25519 path remains superseded because it was unavailable from the tested Android Keystore provider.

### 2.7 Immediate major sequence

Repository development and live governance remain separate. The next source
step is the no-tool inference transport and retained-evidence adapter in issue
#42. The operational sequence below remains gated and does not become
authorised merely because the source work advances.

1. **Completed:** publish and merge the fail-closed `0008` legacy-table retirement after proving it against a disposable copy of the configured database.
2. **Completed:** create and restore-verify a recoverable backup, migrate the configured database to `0008`, and confirm protected rows and both empty current journals are unchanged.
3. **Completed:** provision and approve `governance-p256-02`, independently verify its public proof, and configure the explicit `classifire-governance` issuer binding without placing a private key in CLASSIFIRE.
4. **Completed:** back up and upgrade the controlled-write plugin from `0.4.0` to exact-main `0.5.0`, select `phase8-admission-only`, restart the gateway, and pass live/synthetic no-write boundary checks without touching the real UAT estimate.
5. **Next separate governance decision:** create a fresh proposal-only preflight; obtain a short-lived external P-256 signature; register an admission offline; then obtain separate current authority for the one-time initial canonical write.
6. **Blocked pending separate design and approval:** create a signed Physical Model Lock admission boundary before technical, quantity, commercial, snapshot, output, or release phases are allowed to advance.

## 3. Master roadmap at a glance

| Phase | Status | Primary exit condition |
| --- | --- | --- |
| 0. Product and repository baseline | In progress | Auditable private-repository lineage, controlled changes, and reproducible source state. |
| 1. Domain and workflow governance | In progress | Governed amendments, blank-opening semantics, visual approval, and no destructive scope replacement. |
| 2. Governed source libraries | In progress | Immutable, published, auditable technical and commercial releases. |
| 3. OpenClaw and controlled-write architecture | In progress - Gates A-F locally complete | Revalidate the deployment boundary for other environments; later phases still require their own controlled profiles and approvals. |
| 4. Mission Control integration | In progress | Visibility/control-plane integration without owning estimate truth. |
| 5. Evidence intake and evidence resolution | In progress | Every downstream claim traces to retained report, page, image, and verified higher-detail source evidence. |
| 6. Physical Model engine | In progress | Defensible Barrier-Opening-Service model or explicit limitation for every known defect. |
| 7. Independent visual topology gate | Verified complete for UAT | Independent non-mutating visual challenge and fail-closed receipt. |
| 8. Corrected real Physical UAT | In progress | Semantically approved corrected physical model and replacement active Physical Model Lock. |
| 8C. Automated Physical-Model Accuracy Programme | Planned | Measured, leakage-safe reduction of human exception review; optional governed model training only after prototype evidence. |
| 9. Technical system selection | Blocked by Phase 8 | One current, defensible Repair Strategy Lock per supported Opening. |
| 10. Quantity and labour | Blocked by Phase 9 | Deterministic, authorised, complete quantities and labour. |
| 11. Commercial recovery | Blocked by Phases 9-10 | Every required component recovered once with traceable commercial basis. |
| 12. Independent validation and snapshot | Blocked by Phases 8-11 | No unresolved validation blockers and an immutable reproducible snapshot. |
| 13. Output and proposal generation | Blocked by Phase 12 | Snapshot-backed, reconciled technical and client-facing outputs. |
| 14. Human Release | Blocked by Phase 13 | Human acceptance of the exact validated snapshot and production checklist. |
| 15. Production hardening | In progress | Secure, observable, recoverable, reproducible production operation and qualified automation. |
| 16. Deferred structural steel and ductwork | Deferred | Separate approved design, source authority, calculations, and acceptance evidence. |

## 4. Phase 0 - Product, repository, and change-control baseline

**Status:** In progress

**Objective:** Keep the working product, repository, evidence, and publication history auditable while development continues.

### Required controls

- Use feature branches and draft pull requests for coherent changes.
- Never commit secrets, customer evidence, signed image URLs, supplier data, or `.env` files.
- Preserve user-owned local files and unrelated changes; stage explicit paths only.
- Bind generated operational receipts to the code, policy, prompt, input, and output versions that produced them.
- Keep the private GitHub repository as the shared source of approved code and controlled documentation, while recognising that unpushed local evidence may be newer.

### Exit condition

The active branch, reviewed diff, test evidence, and GitHub draft PR accurately describe every proposed change. No default-branch merge occurs without explicit user authority.

## 5. Phase 1 - Domain and workflow governance

**Status:** In progress

**Objective:** Make the physical-model lifecycle safe, explicit, and correct for passive-fire scope.

### Verified foundations

- Opening, Service, and ServiceOpeningLink are separate governed records.
- Blank openings and empty/redundant core holes can legitimately have zero Services.
- Physical-model change after a lock uses controlled invalidation/amendment, not silent replacement.
- A protected-state fingerprint tracks the canonical estimate, workflow, defects, evidence sources, physical records, and historical locks relevant to proposal-only integrity.

### Remaining work

1. Promote the UAT visual-validation result into a canonical, persisted, hash-bound receipt that lock eligibility enforces.
2. Finish production-service enforcement for the bounded Validator-to-Physical correction policy.
3. Verify controlled amendment behaviour across all blank-opening, mixed-service, and all-blank estimate cases.
4. Complete clean-environment dependency and migration reproducibility evidence.

### Exit condition

Physical records, corrections, lock eligibility, and later amendments are service-governed, reversible where appropriate, audited, and cannot be changed by an unauthorised role.

## 6. Phase 2 - Governed technical and commercial libraries

**Status:** In progress

**Objective:** Maintain authoritative technical and commercial sources as immutable, versioned, traceable runtime releases.

### Current scope

- FIREFLY Package 15/17 technical lineage and Package 14 commercial lineage remain controlled sources.
- Technical Authority Registry abstractions must continue to distinguish source identity, release identity, and runtime eligibility.
- Private source preservation must not leak into public documents, model prompts, or output assets.

### Remaining work

1. Complete registry-neutral contract migration while keeping needed legacy aliases compatible.
2. Resolve source-version/count anomalies through governed amendments, never rewrite source evidence.
3. Validate clean-machine import, hash, release-pin, and rollback procedures.
4. Extend source governance to future manufacturers without repurposing FIREFLY identifiers.

### Exit condition

Every technical or commercial decision cites a versioned, authorised, reproducible source release and the source cannot be silently changed after use.

## 7. Phase 3 - OpenClaw and controlled-write architecture

**Status:** In progress

**Objective:** Provide role-limited model access and controlled canonical writes without granting a generic agent database authority.

### Verified foundations

- Role-specific grants and controlled-write tool boundaries exist.
- Visual sessions are isolated and non-mutating during proposal-only UAT.
- Proposal-only Gateway preflight fails closed rather than restarting the managed Gateway.
- Image transport has explicit content-type, path, byte-hash, and manifest checks before model upload.

### Remaining work

1. Prove clean-machine installation and controlled-write plugin deployment.
2. Complete operation, restart, recovery, timeout, and credential-handling runbooks.
3. Maintain provider/model/configuration receipts without logging tokens, signed URLs, or private report content.
4. Validate policy propagation from UAT runner code into production services.

### Exit condition

Every live role has minimum required authority, every write is attributable and validated, and a clean installation reproduces the governed boundary.

## 8. Phase 4 - Mission Control integration

**Status:** In progress

**Objective:** Use Mission Control as an operational visibility and task-control plane without making it the source of truth for estimate data.

### Requirements

- Mirror run, gate, test, review, and release evidence as links or summaries.
- Keep source data, physical models, technical records, calculations, and snapshots canonical in CLASSIFIRE.
- Treat Mission Control task text as non-authoritative operational context.

### Exit condition

Run and approval visibility is useful and traceable without creating a second mutable estimate database.

## 9. Phase 5 - Evidence intake and evidence resolution

**Status:** In progress - original intake complete; higher-detail evidence resolution added

**Objective:** Ensure every downstream physical claim is traceable to retained source evidence at the highest usable detail.

### Verified foundations

- The current UAT report has retained page, image, layout, and defect-text evidence.
- Linked full-resolution images can be discovered from report annotations and materialised under a strict allowlist, DNS, TLS, size, MIME, pixel, and thumbnail-binding policy.
- A verified original is selected as primary detail only after binding it to the report thumbnail; lower-resolution page/crop/annotation variants remain mandatory context when they carry distinct information.
- Stale low-resolution conclusions are not allowed to suppress high-detail re-review.
- Model-visible attachments are rehashed immediately before transport to prevent path or byte substitution after earlier validation.

### Remaining work

1. Generalise the linked-original workflow across multiple report formats and approved source hosts.
2. Build a governed evidence-family taxonomy for exact duplicates, re-encodes, crops, annotations, alternate angles, and genuinely distinct images.
3. Add multi-report evidence-quality metrics and adversarial retrieval tests.
4. Define a production evidence-retention, redaction, deletion, and data-rights policy.

### Exit condition

Each physical claim has a durable source trail to the relevant report text, page, image occurrence, and verified higher-detail equivalent where one exists. Ambiguous relations are retained rather than force-collapsed.

## 10. Phase 6 - Physical Model engine

**Status:** In progress

**Objective:** Convert retained evidence into a defensible Barrier-Opening-Service graph before technical or commercial work begins.

### Required physical-model rules

- A defect may contain multiple physical openings.
- A nonblank service penetration must have one or more actual Services and explicit Opening-Service links.
- A blank opening or blank core hole must have zero Services; no placeholder service may be invented to satisfy a schema.
- Barrier substrate, plane, orientation, FRL/assumption, service type, material, quantity, and link evidence must remain independently represented.
- Unknown, contested, or occluded facts must be withheld or marked provisional rather than inferred from image count alone.
- Exact opening/service counts do not prove topology correctness.

### Remaining work

1. Complete Phase 8 with a semantically approved model and replacement Physical Model Lock.
2. Strengthen runtime completeness checks with current visual receipt and evidence-family provenance.
3. Expand accuracy and regression coverage to multiple independent reports through Phase 8C.

### Exit condition

Every known defect has a defensible physical model or an explicit evidence limitation, no unexplained duplicate/merged/missed topology remains, and a valid replacement Physical Model Lock exists.

## 11. Phase 7 - Independent visual topology gate

**Status:** Verified complete for controlled UAT; production canonicalisation remains pending

**Objective:** Independently challenge a Physical proposal against the same retained evidence before canonical submission.

### Verified behaviour

- Historical controlled-UAT evidence shows Physical and Validator roles inspecting independently scoped visual evidence. Current main now enforces that ordering through a dependency-injected controller and strict deterministic receipt.
- Current main gives Validator corrections bounded authority and fails closed on malformed receipts, proposals, correction inputs, and ambiguous size-or-quantity authority.
- Current main validates a proposal-blind Opening/Service inventory and requires each blind observation to receive one evidence-backed reconciliation disposition.
- A non-supported or incomplete correction fails closed with limitations.
- Evidence manifests, implementation revision, models, prompts, runtime policy, sessions, transports, stage requests, stage results, and protected-state fingerprints are receipt-bound.
- Proposal-only operation prevents visual agents from submitting or locking the canonical model.

### Remaining work

1. Implement a real no-tool inference transport and retained-evidence manifest adapter against the current controller.
2. Reconcile the validation-only human comparator and linked-original resolver without exposing reference answers to inference.
3. Persist and enforce a canonical VisualValidationReceipt in lock eligibility.
4. Broaden adversarial visual-gate tests beyond the current report.

### Exit condition

An independently validated, durable visual receipt is required for every canonical Physical Model Lock candidate.

## 12. Phase 8 - Corrected real Physical UAT

**Status:** In progress

**Objective:** Replace the known-wrong retained physical state with a visual-validated, defect-level defensible Physical Model.

### Current verified milestones

1. The old incorrect unlocked physical state was removed through controlled reopen while preserving evidence, defects, and historical lock records.
2. Proposal-only safety, protected-state integrity, bounded correction policy, blind reconciliation, and deterministic controller/receipt orchestration were implemented and tested on current main. Comparator hardening remains historical until its current-main transplant is complete.
3. Linked high-resolution originals were verified and made available to visual analysis.
4. A full-resolution proposal-only UAT completed without canonical writes.
5. A provenance-bound human-adjudication record and offline revised proposal were created for the exceptional source conflicts and withheld details.

### Current gate

The next canonical action is not another inference run. It is deployment and verification of the admission-bound writer, followed only if current state is still safe and separately authorised by a fresh preflight, externally signed admission, and initial Physical Model submission. Physical Model Lock creation remains a later separate gate; it is intentionally unavailable until a signed lock-admission boundary is designed and approved.

### Required preflight

Before any canonical write:

1. Recompute the protected canonical-state fingerprint and verify the expected baseline.
2. Confirm zero current canonical Openings, Services, links, and active Physical Model Locks for the estimate.
3. Confirm that the adjudicated proposal, final-state receipt, diff, and comparison receipts bind by current hashes.
4. Confirm controlled-write Gateway health and exact write-tool scope.
5. Confirm no downstream technical, quantity, commercial, snapshot, or output records would be invalidated by the new model.

### Required canonical operation

If preflight passes and the authorised approver directs it:

1. Deploy and verify the admission-bound writer through the [controlled-writer deployment runbook](./ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md).
2. Produce a fresh no-write preflight and obtain a separately governed, externally signed admission manifest bound to that exact payload and protected-state fingerprint.
3. Register the admission offline, then obtain separate current authority to submit the exact adjudicated Opening-Service proposal by admission ID.
4. Re-read the canonical state and reconcile codes, quantities, materials, links, and defect associations exactly.
5. Do not create a Physical Model Lock in this operation. A separate signed lock-admission boundary and explicit authority remain required.
6. Stop and retain a limitation if any condition fails. Do not partly repair the canonical model in place.

### Phase 8 exit condition

- Every known defect is defensibly represented or explicitly withheld with reason.
- Every historical/reference mismatch is explained, adjudicated, or retained as unresolved uncertainty.
- The canonical model is semantically approved, receipt-bound, and independently checked.
- A replacement active Physical Model Lock supersedes invalid historical state.
- Protected-state evidence proves the canonical change was limited to the intended physical-model components.

## 13. Phase 8C - Automated Physical-Model Accuracy Programme

**Status:** Planned - not started

**Position:** This is a dedicated post-prototype programme. It reduces routine human intervention through measurable automation and governed continual learning from routine reports, but does not replace existing Phase 8 safety or Phase 14 human release authority.

### 13.1 Purpose and non-goals

**Purpose:** Improve CLASSIFIRE's automated ability to identify barriers, openings, services, service quantities, materials, and Opening-Service links from report evidence while correctly withholding uncertainty.

**Non-goals:**

- Do not let unreviewed live reports or human corrections directly self-modify a model, become an answer key for the same case, or cross a customer/tenant boundary.
- Do not use a report's human fixture, adjudication, or sealed expected answer during that report's runtime inference.
- Do not claim accuracy from count equality alone.
- Do not eliminate final human release authority.
- Do not grant a trained model direct canonical-write, lock, technical-approval, commercial-approval, or release authority.

### 13.2 Four separate improvement lanes

| Lane | Purpose | Prohibited shortcut |
| --- | --- | --- |
| Evaluation | Measure a fixed candidate against independent ground truth. | Expose labels to runtime inference or tune on sealed results. |
| System and prompt improvement | Improve evidence selection, multi-view reconciliation, schema constraints, prompts, confidence, and Validator behaviour. | Treat a case-specific answer key as runtime instruction. |
| Model training or fine-tuning | Change model weights or create an approved provider-hosted/custom model from an approved corpus. | Start automatically, use unapproved data, or bypass the same independent evaluation. |
| Governed continual learning | Capture routine report evidence and verified outcomes into a versioned learning pipeline, then periodically release evaluated improvements. | Per-report weight updates, self-label training, cross-tenant leakage, or silent provider-side learning. |

### 13.3 Programme admission gate - working prototype

Only preparation may begin before the following are all true:

1. Phase 8 has produced a defensible replacement active Physical Model Lock.
2. The graph schema, blank-opening semantics, evidence receipts, and protected-state safeguards are stable and versioned.
3. Higher-detail source selection, duplicate grouping, and image provenance are reproducible.
4. Proposal-only evaluation and independent visual validation remain proven.
5. Every dataset source has an approved data-use basis for benchmarking and, separately, any possible training use.
6. An end-to-end prototype has produced snapshot-backed outputs through Phase 13 before a training/fine-tuning decision is made.

Until then, this programme may create the charter, taxonomy, and rights inventory. It must not train a model or tune against the current UAT outcome.

### 13.4 8C.0 - Programme charter and physical-truth contract

**Objective:** Define the target task and how accuracy, safety, uncertainty, and human-efficiency improvements will be measured.

**Deliverables:**

- Barrier, substrate, plane, opening, blank-opening, service, material, quantity, and link taxonomy.
- Severity model for critical errors such as a missed opening, invented service, false blank classification, or unsupported high-confidence material claim.
- Explicit valid uncertainty outcomes: `withheld`, `insufficient evidence`, `source conflict`, and `requires review`.
- Candidate-version contract covering model/provider, prompt/configuration, image-processing, evidence-pack, Validator, and output-schema versions.
- Approval matrix spanning product owner, technical authority, privacy/data owner, security/change control, and release owner.

**Exit condition:** A governed measurement and data-use charter exists before any benchmark label is used for development.

### 13.5 8C.1 - Governed evidence and benchmark corpus

**Objective:** Build a rights-cleared, leakage-resistant multi-report corpus.

**Required controls:**

- Preserve immutable source packets with report/page references, hashes, image provenance, verified originals, and redaction status.
- Group thumbnails, linked originals, crops, duplicates, re-encodes, annotations, alternate angles, and processed derivatives into evidence families.
- Split by report, site, customer, and project - never by individual image alone - so the same physical opening cannot leak across partitions.
- Stratify across barrier types, blank openings, mixed services, quantities, image quality, occlusion, multiple views, source conflict, and withheld cases.
- Record data rights, consent/contractual basis, retention, provider-use permission, redaction requirements, and deletion obligations.
- Keep contested facts as uncertainty examples. Never force a false gold label merely to enlarge the dataset.

**Ground-truth hierarchy:**

1. Verified as-built or independently verified physical evidence.
2. Evidence-backed expert adjudication with rationale and provenance.
3. Canonical records only after independent verification; an old lock alone is not automatically ground truth.
4. Unresolved cases as abstention/uncertainty examples rather than forced answers.

**Required partitions:**

- Approved training set, only if a later fine-tuning decision is authorised.
- Development set for system/prompt/model selection.
- Sealed holdout unavailable to developers and candidates until final scoring.
- Prospective shadow set from new reports after candidate selection.
- Regression archive, including this adjudicated UAT, held out from initial training and routine prompt tuning.

**Exit condition:** Dataset card, rights register, split manifest, evidence-family map, label guide, and label-quality review are versioned and complete.

### 13.6 8C.2 - Blind automated baseline and measurement harness

**Objective:** Establish a reproducible automated baseline before changing the system.

| Area | Required measures |
| --- | --- |
| Opening topology | Per-defect exact graph match, opening precision/recall, count error, duplicate/merged/missed-opening rate. |
| Services | Service-type, material, and quantity correctness; mixed-service identification; service precision/recall. |
| Links and blanks | Opening-Service link accuracy, blank-opening precision/recall, false-blank rate, invented-service rate. |
| Evidence quality | Correct verified-original selection, duplicate handling, and evidence-to-claim provenance completeness. |
| Uncertainty | Correct abstention rate, unsupported-claim rate, and confidence calibration against observed accuracy. |
| Safety | Critical-error rate, false high-confidence claim rate, unauthorised-write attempts, and missing-receipt rate. |
| Human efficiency | Review rate, field-level escalation rate, reviewer time, disagreement rate, and avoidable evidence-quality review rate. |
| Generalisation | Results by report, site, image quality, service mix, and rare scenario, not only aggregate averages. |

Acceptance thresholds must be set before sealed-holdout results are revealed. A candidate cannot pass by improving average accuracy while increasing critical safety errors or hiding uncertainty.

**Exit condition:** A proposal-only benchmark runner, baseline scorecard, error taxonomy, and locked acceptance thresholds exist.

### 13.7 8C.3 - Non-training system improvements

**Objective:** Remove avoidable causes of human review before deciding that model training is necessary.

**Priority work:**

1. Higher-detail source discovery, verified retrieval, and evidence-family selection.
2. Duplicate, alternate-angle, crop, and annotation reconciliation.
3. Barrier-first structured extraction and multi-view Opening-Service graph reconciliation.
4. Explicit blank-opening semantics and schema-constrained output.
5. Field-level evidence citations, confidence calibration, and selective abstention.
6. Validator checks that target material topology errors rather than superficial count agreement.

Every candidate configuration must be versioned, selected on development data, run proposal-only, and independently scored on the sealed holdout once. Prompt/configuration changes are candidate releases, not informal trial-and-error against known answers.

**Exit condition:** Measurable independent improvement is demonstrated, or a documented plateau justifies considering a controlled fine-tuning experiment.

### 13.8 8C.4 - Governed continual learning from live reports

**Objective:** Turn routine report inputs and verified outcomes into a controlled learning loop that improves future automation without allowing an untrusted report to self-modify the system.

**What enters the learning pipeline:**

1. A routine live run records a hash-bound evidence manifest, model/prompt/configuration version, structured proposal, field-level confidence, Validator result, exception reasons, and any later verified outcome.
2. A live report becomes a **learning candidate**, not an immediate training example. Its evidence remains private and tenant-scoped until data rights, retention, redaction, and quality gates pass.
3. A label may be created only from an independent outcome: an approved physical/technical result, a governed adjudication, verified as-built evidence, or another approved source. A model's own output is never sufficient ground truth.
4. Approved learning candidates are periodically assembled into a versioned dataset. Candidate configurations, retrieval indexes, calibration changes, or trained models are then evaluated and released through the same development, sealed-holdout, shadow, and rollback gates.

**Runtime learning rules:**

- The current report may use its own retained evidence during its run; that is evidence reasoning, not training.
- The current report's outcome must not change the model, prompt, or retrieval corpus used to decide that same report.
- Tenant-scoped retrieval of previously approved, permissioned patterns may assist future proposals, but it may not reveal another customer's evidence or replace the current report's evidence basis.
- Live inputs are screened for privacy, malicious content, source integrity, prompt injection, and data-rights eligibility before entering any learning store.
- A learning release is versioned, reproducible, proposal-only qualified, independently evaluated, and rollback-capable. There are no direct per-report model-weight updates in production.

**Required measurements:**

- Eligible-report coverage, outcome-feedback coverage, data-quality rejection rate, and time from verified outcome to approved dataset version.
- Accuracy, calibration, abstention, critical-error, and exception-rate change by live-report cohort.
- Cross-tenant isolation, provenance completeness, label disagreement, drift, and rollback effectiveness.

**Exit condition:** A permissioned learning ledger, outcome-ingestion path, data-quality gate, versioned dataset release process, and independent candidate-release controls are proven in shadow operation.

### 13.9 8C.5 - Minimal human exception workflow

**Objective:** Make human input targeted, auditable, and progressively smaller.

**Normal path:** CLASSIFIRE produces an evidence-bound automated Physical Model proposal.

**Permitted human-review triggers:**

- Material source conflict.
- Critical low-confidence or unsupported field.
- Novel or out-of-distribution barrier/opening/service condition.
- Risk-based random audit sample.
- Customer, technical authority, or post-release dispute.

**Review design:**

- Route a specific uncertain opening, service, or field rather than every report.
- Use blind independent review where feasible before showing the model proposal, reducing anchoring bias.
- Record source basis, uncertainty, and rationale, not only a replacement answer.
- Preserve disagreement as withheld rather than force agreement.
- Do not automatically turn an adjudication into training data; it requires rights confirmation, quality review, dataset-version approval, and a future governed release decision.

**Exit condition:** Exception queue, reviewer guidance, sampling policy, decision receipt, disagreement register, and review-rate dashboard are operational.

### 13.10 8C.6 - Fine-tuning readiness and controlled experiments

**Objective:** Decide whether actual model training is justified and, only if it is, test it safely.

Fine-tuning is optional. It may begin only when all of the following are satisfied:

1. Diverse, rights-cleared, high-quality labels are available.
2. Non-training improvements have been evaluated.
3. A documented business and safety case shows expected benefit over the base-system candidate.
4. Provider retention, training-use, security, privacy, and deletion terms are approved.
5. The exact training corpus, code, configuration, and model release are reproducible from manifests and hashes.
6. Explicit approval identifies the data, provider, model, scope, and experiment.

**Fine-tuning controls:**

- Use only the approved training partition, never development, sealed-holdout, or current runtime cases.
- No ungoverned online learning, self-label training, silent provider-side training, or automatic use of a live report outside the approved learning pipeline.
- Train offline with no canonical database authority.
- Produce a model card, training-data card, experiment receipt, failure analysis, cost record, and rollback plan.
- Compare against both the unchanged baseline and the best non-training candidate.
- Reject a candidate that improves an average score while worsening critical-error, uncertainty, provenance, or escalation behaviour.

**Exit condition:** A candidate is rejected with evidence or approved only for proposal-only shadow evaluation.

### 13.11 8C.7 - Independent holdout and prospective shadow evaluation

**Objective:** Prove that the selected candidate generalises beyond the data used to develop it.

**Required process:**

- Reveal sealed holdout labels only after candidate selection.
- Preserve all outputs, evidence manifests, and scored receipts.
- Run prospective reports in shadow mode beside the approved baseline.
- Do not permit candidate output to submit or lock canonical Physical Models.
- Investigate results by error scenario and cohort, not only aggregate score.
- Reassess calibration, safe abstention, and exception-review rate on prospective evidence.

**Exit condition:** Predeclared acceptance criteria pass on both sealed holdout and prospective shadow evidence with no unmitigated critical regression.

### 13.12 8C.8 - Controlled automation release and monitoring

**Objective:** Increase automated throughput without weakening existing control boundaries.

| Autonomy level | Permitted behaviour |
| --- | --- |
| Proposal assistance | Automated evidence extraction and structured proposal; human reviews all material items. |
| Exception-led proposal | Automated proposal for high-confidence items; human reviews targeted exceptions plus audit samples. |
| Controlled physical submission | Only after separate approval; existing Validator, controlled-write, lock, audit, and rollback controls still apply. |
| Final release | Human-only under Phase 14 regardless of model accuracy. |

**Monitoring and retraining rules:**

- Monitor error, conflict, exception, and provenance rates by confidence band, source quality, report/site cohort, and physical category.
- Alert on drift, increasing critical error, false confidence, source conflict, or evidence-provenance failure.
- Keep a rollback-ready prior candidate.
- Treat every dataset, retrieval, calibration, prompt, and model release as a new governed learning release requiring the same benchmark, shadow, approval, and rollback gates.

**Exit condition:** Controlled automation policy, monitoring, incident process, rollback procedure, and retraining runbook are proven.

## 14. Phase 9 - Technical system selection

**Status:** Blocked by Phase 8 replacement Physical Model Lock

**Objective:** Select technically applicable systems only from authorised technical releases, Opening by Opening.

### Required work

1. Search the estimate's pinned Technical Authority Registry release.
2. Evaluate blank openings without inventing service attributes.
3. Evaluate service penetrations against service, material, size, quantity, substrate, plane, orientation, opening, FRL, spacing, edge distance, support, fixing, and dependencies.
4. Preserve every mismatch and unknown; never use a commercial analogue as technical approval.
5. Create one active defensible Repair Strategy Lock per supported Opening.

### Exit condition

Every supported Opening has one current, traceable, technically defensible strategy lock. Unsupported conditions remain explicitly blocked.

## 15. Phase 10 - Quantity and labour

**Status:** Blocked by Phase 9

**Objective:** Derive deterministic component quantities and authorised labour without silent defaults or invented productivity.

### Required work

1. Derive quantities from selected systems, opening geometry, service topology, and component algorithms.
2. Keep inputs, units, waste, rounding, procurement minimums, mobilisation, access, preparation, installation, QA, documentation, and cleanup distinct where material.
3. Use approved productivity sources for every required activity code.
4. Recover shared labour exactly once.

### Exit condition

All required quantities and labour are deterministic, authorised, traceable, and complete; missing productivity remains fail-closed.

## 16. Phase 11 - Commercial recovery

**Status:** Blocked by Phases 9-10

**Objective:** Recover each required commercial component exactly once through the approved pricing hierarchy.

### Required work

1. Apply exact or parameterised governed rates only after line-specific applicability.
2. Use component-built pricing or a governed bounded expert path only where the appropriate authority permits it.
3. Lock the commercial method for every component.
4. Reconcile all shared, included, and allocated value once.
5. Keep technical authority distinct from commercial evidence.

### Exit condition

Every required component has one traceable commercial basis, no duplicate recovery, and no unexplained omission.

## 17. Phase 12 - Independent validation and immutable snapshot

**Status:** Blocked by Phases 8-11

**Objective:** Independently validate the complete estimate and freeze a deterministic release snapshot.

### Exit condition

No unresolved validation blocker remains. The snapshot is immutable, reproducible, hash-bound, and sufficient to regenerate all output artifacts.

## 18. Phase 13 - Output and proposal generation

**Status:** Blocked by Phase 12

**Objective:** Render technical and client-facing deliverables only from the validated immutable snapshot.

### Exit condition

Outputs contain only snapshot-backed facts, reconcile to canonical totals, render correctly, and pass structural and visual QA.

## 19. Phase 14 - Human Release

**Status:** Blocked by Phase 13

**Objective:** Preserve accountable human authority for final client and production release.

### Non-negotiable rule

No agent, benchmark, prompt, or trained model may approve a final release. Automation may prepare evidence and propose decisions; a competent authorised human accepts the exact validated snapshot and output set.

### Exit condition

A human reviewer accepts the corrected UAT and production-release checklist, bound to the exact immutable snapshot and output hashes.

## 20. Phase 15 - Production hardening

**Status:** In progress

**Objective:** Turn proven UAT architecture into a reproducible, secure, observable, recoverable, and maintainable production system.

### Required production gates

- Clean-machine deployment, dependency locking, migration, configuration, and recovery evidence.
- Security tests for malicious evidence, prompt injection, path traversal, formula injection, secret leakage, and cross-role escalation.
- Backup, restore, rollback, audit, monitoring, and incident procedures.
- 10-, 100-, and 1,000-defect performance and cost benchmarks.
- Snapshot/output regression and release reproducibility.
- Phase 8C qualification evidence before expanding automation beyond controlled proposal assistance.

### Exit condition

Production operation is reproducible and observable; controlled automation is independently qualified; security, data governance, recovery, performance, and human-release controls are proven.

## 21. Phase 16 - Deferred structural steel and ductwork

**Status:** Deferred

Structural steel and full fire-rated duct-run scope remain separate work packages. They require their own physical taxonomy, source libraries, technical applicability, component algorithms, quantity logic, commercial logic, benchmark corpus, and acceptance evidence.

No steel or duct calculator data may be imported into the active fire-seal/penetration runtime until this roadmap phase is separately designed and approved.

## 22. Roadmap-wide release rules

1. Source evidence is immutable; corrections are governed amendments or separate adjudication records.
2. Every canonical write is least-privilege, auditable, and receipt-bound.
3. Proposal-only experimentation is the default for expensive, uncertain, or model-changing work.
4. Human fixtures, adjudications, and sealed benchmark labels are unavailable to inference for the same case.
5. High-resolution verified evidence improves automated input quality but does not justify inventing concealed or uncertain physical facts.
6. Training and continual learning are governed, reproducible, and independently evaluated. Routine reports may contribute through the permissioned, versioned learning pipeline; they never cause silent self-modification or bypass release gates.
7. Correct abstention is preferable to an unsupported confident claim.
8. Human involvement is targeted to exception review and final release, not routine hidden assistance.
9. No downstream phase may bypass an unresolved upstream gate.
10. This roadmap must be revised when verified execution evidence changes its factual state, while preserving earlier versions as decision history.

## 23. Related documentation

This documentation-only publication is self-contained on its target branch.
The two linked documents below are included with this roadmap update. Other
architecture, knowledge-alignment, and evidence documents must be linked only
when they are independently published to the target branch; this avoids
publishing GitHub links that resolve only in a local or unrelated worktree.

- [Admission-Bound Canonical Writer Deployment Runbook](./ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md)
- [External Signer Operating Model for Adjudicated Admissions](./ADJUDICATED_ADMISSION_EXTERNAL_SIGNER_OPERATING_MODEL.md)
