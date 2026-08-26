# CLASSIFIRE Master Roadmap

**Document status:** Active working roadmap

**Roadmap version:** 2026-08-27 r18

**Product status:** Pre-production prototype and controlled UAT build

**Supersedes:** The 18 August 2026 r2 Master Roadmap as the current working plan. The supplied PDF and earlier roadmap revisions remain immutable reference and decision-history records.

**Scope:** Passive-fire evidence intake, physical-model automation, technical selection, quantities, commercial recovery, validation, output, release, and production hardening.

## 1. How to read this roadmap

This roadmap separates approved direction from observed implementation state.

| Label | Meaning |
| --- | --- |
| **Completed** | Supported by current implementation, test, or execution evidence for the stated scope. |
| **In progress** | Approved work with material implementation or evidence, but incomplete exit criteria. |
| **Planned** | Approved direction that has not yet started. |
| **Blocked** | Cannot proceed without an upstream condition, evidence, or explicit authority. |
| **Deprecated / superseded** | Retained for history or selective recovery, but not an accepted current implementation path. |

The current code, test results, receipts, and live-state checks take precedence over older roadmap wording for factual status. The roadmap still controls sequencing, architecture, and acceptance criteria.

Nothing in a report, fixture, receipt, or attached reference document grants authority to make canonical writes, train a model, publish data, or release an estimate. Those actions require their own explicit approval and gates.

## 2. Executive status

### 2.1 Current product position

CLASSIFIRE has a controlled evidence-to-physical-model prototype. Shared `main`
at `1b3d7c9` contains the canonical runtime,
admission-bound writer, bounded visual correction guard, proposal-blind
inventory, mandatory blind reconciliation, deterministic proposal-only
controller and receipt, retained-evidence adapter, guarded linked-original
retrieval and retention, bounded linked-original-to-proposal runner,
literal-loopback OpenResponses transport, managed local runtime composition,
dedicated zero-tool identities, fail-closed provisioning, and the
post-inference validation-only human-reference comparator.

Shared main also contains the trusted operator-created representative-run
package, defect-scoped retention from a full-report retrieval pass,
report-derived parent validation, a read-only Gateway readiness probe, rollback
enforcement, content-safe blocked evidence-review output, and fully local
recovery from receipt-bound OpenClaw session history. These are controlled-UAT
capabilities, not production or canonical-write authority.

Separate August 26 branches contain a tested production-hardening candidate
stack through opaque human sessions and migration `0010`, fail-closed startup,
quarantine-first malware scanning, durable scan attestations and migration
`0011`, scan-bound inference receipts, and validation of every declared package
photo row. A clean committed local integration combines that stack with detailed
deployment-lineage readiness, and a further uncommitted candidate hardens XLSX
output. None of this work is on shared main, reviewed through a pull request as
one architecture, migrated in a live environment, or deployed.

A retained representative rollback-only run completed against an approved
report and linked-original source. Retrieval succeeded, but the independent
Validator blocked the proposal on real evidence insufficiency. Protected
canonical counts and fingerprint were unchanged after rollback, no human
reference was shown to inference, and no canonical submission or Physical
Model Lock occurred. Post-run hardening changed the candidate source tree, so
that run is historical execution evidence for its exact receipt-bound source,
not exact live proof of every byte in the final reviewed candidate.

The prototype is not production-authorised. It does not yet have a corrected active Physical Model Lock for the current real-report UAT, and all technical, quantity, commercial, snapshot, output, and release work remains downstream-blocked by that missing lock.

### 2.2 Verified recent advances

| Area | Verified current position |
| --- | --- |
| Evidence integrity | Proposal-only runs protect the canonical estimate with a component-level protected-state fingerprint rather than relying on a whole-database file hash. |
| Image quality | Shared main can discover allowlisted report-provided linked originals, bind them to displayed thumbnails, prove usable additional detail, retain verified bytes as immutable child evidence, preserve lower-resolution context, and feed retained bytes into the proposal-only controller. The retained representative pass retrieved every required original and restricted inference to current retentions plus explicitly mapped ready parents for the selected defect. |
| Image provenance | Shared main preserves explicit parent-thumbnail and page context for retained linked originals. Automated grouping of duplicates, re-encodes, crops, annotations, and alternate angles remains planned Phase 5 work. |
| Visual safety | Shared main enforces bounded correction semantics, fail-closed strict-schema receipts, proposal-blind inventory, mandatory reconciliation, ordered role separation, protected-state checks, byte-verified defect-bound retained evidence, no-tool transport semantics, and dedicated runtime identities. Synthetic inference proved the configured no-tool boundary; the representative pass then proved safe abstention by returning a valid Validator block without changing protected state. |
| Proposal-only safety | The controller has no database, canonical-write, admission, signing, registration, lock, device, or deployment capability. The transport accepts only literal loopback endpoints, rechecks image bytes, requires empty effective server tools, sends `tools: []` with `tool_choice: none`, and audits the exact session after every attempted request. |
| Reconciliation | Shared main has a post-inference human-reference comparator that binds proposal, strict controller receipt, and validation-only reference inputs by path and SHA-256. It verifies the proposal's canonical JSON binding and detects topology/substrate swaps rather than matching disconnected multisets. It has no database or inference interface. |
| Human adjudication | Shared main includes the provenance-bound v2 review and evidence-family validators. The retained local proposal-only record accounts for all seven review items and four unresolved observations exactly once, contains five Openings, six Services, and six links for the selected Defect, preserves site-dependent limitations, and leaves canonical state unchanged. |
| Representative rollback proof | The retained pass resolved all required linked originals, retained only the selected defect's governed evidence, completed four proposal-only inference stages, and stopped at `VISUAL_PROPOSAL_BLOCKED`. The rollback receipt records unchanged protected state and no canonical write or lock. |
| Evidence-review recovery | The current local tooling can recover a content-safe human review request from the exact package, receipts, proposal, and locally retained controller sessions without opening the retained report or linked-original files and without another inference request. It does read the bound local session transcripts and records that this history is mutable and that Gateway authentication, tool attestation, response identity, and external transport are not replayed. |
| Production security candidates | Pushed current-main-based branches implement server-side revocable human sessions, fail-closed production configuration/bootstrap, quarantine-first scanning, durable content-bound malware attestations, scan-bound inference receipts, and validation of every declared package photo row. These are tested candidate boundaries, not shared or deployed capability. |
| Output safety candidate | An isolated two-file XLSX candidate writes text literally and blocks automatic formula, URL, hyperlink, and external-link activation while preserving numeric, boolean, and blank cells. It is tested but uncommitted and unpushed. |
| Linked-image byte identity | Review found that the general linked-image path can scan/decode one read and later hash another read of the same mutable path; one preferred-path read is also unbounded before later validation. Single-buffer exact-byte identity remains an open Phase 5 correction. |
| Controlled-writer Gate A | The last completed exact-main audit was on `74346c5`, with reproducible admission-only plugin artifact SHA-256 `38812E99...AEE4` and clean candidate fingerprint `1B710710...F8CC`. Shared main and the local candidate are newer, so another exact-source Gate A candidate is required before any deployment decision. The audit itself remains review-only. |
| Gates B-F deployment | Retained local handoff evidence records migration `0008`, public-key policy, least-privilege scope reconciliation, plugin `0.5.0` upgrade/restart, and synthetic fail-closed validation as complete for that configured environment. These live boundaries were not rerun in this reconciliation and must be revalidated for changed source or environment. The real UAT estimate remains unchanged and has no admission, submission receipt, canonical model, or active lock. |
| Android admission signer | The retained local handoff records the non-debuggable `0.2.1-local` release APK, approved APK certificate, and `governance-p256-02` hardware-backed P-256 public proof. Device custody was not reverified in this repository reconciliation. No real admission is recorded as signed or registered. |

### 2.3 Current Phase 8 evidence position

The earlier full-resolution proposal-only UAT and offline adjudication produced
a provisional revision with **17 Openings and 22 Service groups**. The later v6
no-write preflight normalised that proposal to **17 Openings, 24 Services, and
24 Opening-Service links**. Both are non-canonical evidence artifacts, not an
approved Physical Model or authority to write one.

The newer representative full-report pass was a separate proposal-only
validation of one selected Defect. It did not supersede or approve the earlier
17/24 preflight. All required linked originals were available, four governed
images for the selected Defect entered inference, and the Validator blocked on
unsupported service classification/quantity and unresolved opening,
classification, and photo-relationship evidence.

The later human-review v2 record accounts for all seven structured review items
and four unresolved observations exactly once. It confirms the visible opening
relationships, photo relationship, flexible-duct count, and service groupings,
and a separate local no-write validator passes a limited five-Opening,
six-Service, six-link proposal-only record. It is not site verification or an
approved canonical model. Dimensions, depth and obscured boundaries, exact
substrate composition, service labels and documentary material proof, and
opposite-face continuity remain unresolved.

The adjudicated proposal comparison passes against the versioned adjudication record. The historical human-reference comparison remains a diagnostic with three explained differences:

1. A separate pipe retains unknown material rather than inventing PVC.
2. A clarified wall penetration differs from an older fixture's slab classification.
3. A clarified five-opening topology preserves uncertainty rather than forcing the older fixture's grouping or substrate assumption.

These differences must remain explicit. Passing a count comparison alone is never sufficient for a Physical Model Lock.

### 2.4 Immediate governing constraints

- The canonical estimate must remain unchanged until a controlled canonical preflight passes and a separately authorised submission occurs.
- `Rollback-only` and `no-write` mean no canonical database submission or lock. Approved UAT execution still writes only to disposable retrieval/storage snapshots and receipt/output directories; SQL rollback does not remove those disposable files.
- The historical human fixture and any adjudication for a report are validation-only; they must not be exposed to that report's runtime inference or used as hidden prompt answers.
- Full-resolution originals are preferred when verified. Lower-resolution thumbnails, crops, labels, and page renders remain contextual evidence when they preserve information not present in the original.
- Human adjudication is an exception mechanism for genuine conflict or ambiguity. It is not the intended routine input for every estimate.
- Routine live reports and their verified outcomes are intended to improve CLASSIFIRE through a governed continual-learning pipeline. They must not directly self-modify the model during the same live case.
- A trained or improved model never bypasses protected-state checks, independent validation, Physical Model Lock rules, or human-only final release.

### 2.5 24-26 August 2026 implementation reconciliation

The current report UAT remains **proposal-only**. The adjudicated revision and
its v6 17/24 normalisation are non-canonical; the newer representative pass is
Validator-blocked. No real admission has been registered, no canonical
Opening-Service-Link model has been written, and no replacement active Physical
Model Lock has been created. Technical selection, quantities, commercial
recovery, snapshot, output, and release therefore remain correctly blocked.

The original Phase 8 branch contains valuable UAT and later-phase foundation
work, but mixes physical, technical, commercial, agent, plugin, deployment, and
output concerns. Current implementation is being reconciled through small
reviewed slices rather than a bulk merge:

| Foundation workstream | Roadmap phases supported | Recorded factual status | Remaining evidence before completion |
| --- | --- | --- | --- |
| Layer 1 - runtime foundation | 0, 15 | **Completed for the merged foundation scope** through PR #16 and present on shared main. | Broader CI and production-hardening evidence. |
| Layer 2 - physical foundation | 1, 6, 8 | **Completed for the merged foundation scope** through PR #17 and present on shared main. | Resolve remaining site-dependent Phase 8 facts, then complete separately governed canonicalisation and lock boundaries. |
| Layer 3 - least-privilege agents | 3, 15 | **Completed for the local deployment scope** through PRs #18, #20, #25, and Gates D-E. | Revalidate in each different deployment environment. |
| Layer 4 - P-256 admission/writer | 1, 3, 6, 8, 15 | **Completed for local Gate F deployment validation**; writer, reconciled journal, key policy, and runtime boundary are active locally. | Evidence-resolved proposal, fresh preflight, external signature, offline registration, and separate one-time write authority. |
| Controlled plugin rebuild | 3, 15 | **Completed for the local deployment scope.** Exact-main `0.5.0` is installed under `phase8-admission-only`, restarted, and boundary-tested. | Revalidate for any different environment or source revision. |
| Representative package and runner | 5, 6, 7, 8 | **Completed for the merged shared-main UAT tooling scope.** A retained run safely reached a Validator evidence block and rolled back; the completion summary binds the exact receipt bytes. | Rerun inference only after a material governed input change and current approval. |
| Offline evidence-review recovery | 5, 7, 8 | **Completed for the retained blocked-run recovery scope.** Recovery v8 binds the corrected, formatted source fingerprint and reconstructs a content-safe review handoff without opening the report/linked originals or performing inference. It does read bound local transcripts. | Local session history remains mutable; the completed review still leaves site-dependent facts unresolved. |
| Human-session and production bootstrap stack | 0, 3, 15 | **Tested pushed branch candidates through migration `0010`.** Active-user checks, opaque sessions/revocation, fail-closed production configuration, bootstrap ordering, and schema readiness exist off main. | Bounded PR review, existing-database adoption, clean deployment, live migration, operations, and deployment authority. |
| Malware, scan-receipt, and photo-inventory stack | 3, 5, 7, 15 | **Tested pushed branch candidates through migration `0011`.** Quarantine-first scanning, durable attestations, scan-bound transport evidence, and validation of every declared package photo row exist off main. | Bounded PR review, linked-image single-buffer correction, governed scanner operations, data rights, live migration, monitoring, and recovery proof. |
| XLSX output safety | 13, 15 | **Tested uncommitted isolated candidate.** Literal text and disabled automatic links/formulas protect generated workbooks in focused and integrated tests. | Commit/publication review and broader snapshot/output release qualification. |
| Controlled canonicalisation | 8 | **Blocked.** | Preserve the unresolved facts unless future governed evidence becomes available; only a semantically accepted proposal with durable validation evidence may proceed to fresh preflight, external signature, admission registration, and separate write authority. |
| Signed lock-admission | 1, 6, 8 | **Planned and blocked.** | Separate signed lock design and authority after canonical model approval. |
| Legacy-root-only later-phase modules | 2, 5, 9-15 | **Deprecated / superseded as a bulk-merge path.** Additional guarded-technical registry, image-variant, repair-strategy, productivity/quantity, commercial, validated-snapshot/validation, release-control, and human-release modules/APIs exist on the divergent legacy root. Shared main retains lower-level technical, calculation, snapshot, Mission Control, and output foundations, but not those additional runtime/API layers. | Audit and transplant only still-valid slices after their upstream gates; do not count either source-file presence or legacy tests as current phase completion. |
| Automated Physical-Model Accuracy Programme | 8C | **Planned.** | Working prototype and the programme admission gate. |

The clean foundation stack is merged through Layer 4. PRs #45-#68 reconciled
the bounded visual-validation and linked-original proposal toolchain onto shared
main. The dirty `gpt/phase8-linked-original-images` root remains an
implementation/evidence source, not a safe staging source or merge candidate.
The representative-execution checkpoint formerly tracked by GitHub issue #42
has now produced a valid evidence block, and the reviewed recovery/tooling
slices are merged. Its next useful scope is governed evidence resolution. Legacy
stacked PRs #9-#13 must not be merged directly; each remaining valid change
needs current-main review, focused transplantation, or explicit supersession.

The latest retained controlled-write plugin audit records zero findings in its shipped dependency set. Ten findings remained in the then-current OpenClaw development dependency, with no safe upstream OpenClaw release available at that checkpoint. [GitHub issue #43](https://github.com/Slayde91/classifire/issues/43) tracks the update; forced dependency downgrades or overrides are not an accepted remedy.

### 2.6 Controlled canonicalisation and signer direction

The first canonical write must be admission-bound. A signed admission binds one estimate, one normalized Opening-Service-Link payload, one protected-state fingerprint, source/adjudicated artefact hashes, policy and implementation hashes, issuer/key identity, purpose, and expiry. The writer consumes that admission once, rechecks the current state in the write transaction, writes only the sealed physical facts, and **does not create a Physical Model Lock**.

P-256 is the approved production admission protocol. The retained local handoff
records `governance-p256-02` as a hardware-backed, non-exportable Android
Keystore key whose independently verified public proof was configured only for
issuer `classifire-governance`. This repository reconciliation did not reverify
device custody or the installed APK. No real admission is recorded as signed or
registered, and no private admission key is present in the repository. The
prior Ed25519 and debug-app paths remain superseded.

### 2.7 Immediate major sequence

Repository development and live governance remain separate. Dedicated zero-tool
runtime identities, controlled synthetic inference, the validation-only
comparator, linked-original retrieval/retention, the bounded runner, and the
rollback-only package are implemented for their stated shared-main scopes. The
representative pass and its 7+4 human review are complete for their limited
scopes, but the proposal is not an approved canonical model. The representative
package, review safeguards, and durable receipt boundary are now on shared main.
No site, remote-supervised, or documentary follow-up evidence is currently
available. The affected physical fields must therefore remain unresolved.
Source publication and assumption-led quoting do not authorise another report
run, canonical write, signature, admission, lock, or deployment.

1. **Completed:** publish and merge the fail-closed `0008` legacy-table retirement after proving it against a disposable copy of the configured database.
2. **Completed:** create and restore-verify a recoverable backup, migrate the configured database to `0008`, and confirm protected rows and both empty current journals are unchanged.
3. **Completed:** provision and approve the retained P-256 admission key, independently verify its public proof, and configure its issuer binding without placing a private key in CLASSIFIRE.
4. **Completed:** back up and upgrade the controlled-write plugin to exact-main `0.5.0`, select `phase8-admission-only`, restart the Gateway, and pass live/synthetic no-write boundary checks without changing the real UAT estimate.
5. **Completed for the retained run source:** execute one approved rollback-only representative pass. Retrieval and rollback succeeded; the Validator blocked the proposal and human comparison was correctly skipped.
6. **Completed with limitations:** the provenance-bound v2 human response accounts for every retained review item/observation and shared-main validators pass the limited 5/6/6 proposal-only record without reading or writing canonical state.
7. **In progress / blocked on unresolved evidence:** preserve the unknown dimensions, depth/boundaries, exact substrate, service labels/material proof, and opposite-face continuity unless future governed evidence becomes available.
8. **Open and unmerged:** review PR #74 at corrected head `9f5daca` as the exact seven-file evidence-intake foundation. It can govern future evidence but does not create that evidence or alter the Physical Model.
9. **Open and unmerged with a stale prerequisite:** recalculate PR #75 at `ef44254` against PR #74's corrected contract before reviewing the assumption-led desk quote. It is nontechnical and noncanonical and cannot approve the 5/6/6 topology.
10. **Tested branch candidates, unreviewed as shared architecture:** review the August 26 session, configuration, schema, malware, scan-receipt, photo-inventory, deployment-lineage, and XLSX hardening in bounded dependency order.
11. **Implementation defect open:** make linked-image scanning, decode, dimensions, hashing, and transport consume one bounded immutable byte buffer, with path-substitution and oversized-padded-image regressions.
12. **Blocked pending semantic acceptance and separate authority:** after the remaining evidence is governed, a durable visual-validation receipt is semantically accepted, and the separate lock boundary is approved, create a fresh proposal-only preflight, obtain a short-lived external P-256 signature, register an admission offline, and then obtain separate current authority for the one-time initial canonical write.
13. **Planned and blocked pending separate design and approval:** create a signed Physical Model Lock admission boundary before technical, quantity, commercial, snapshot, output, or release phases may advance.

### 2.8 Deprecated and superseded checkpoints

- The issue #42 checkpoint stating that the first representative run is pending is superseded by the retained Validator-blocked execution and completed limited human review. Keep the issue open until the merged work and remaining evidence/design blockers are recorded there.
- The 17/22 adjudication and v6 17/24 preflight are historical non-canonical artifacts, not accepted topology, reusable admission authority, or a completion target.
- Whole-database file hashing and count-only comparison are superseded by component-level protected-state fingerprints plus semantic and evidence-backed validation.
- The Ed25519 signer, debug-app keys, legacy initial-submission schema, and same-operation lock creation are superseded paths.
- Bulk merge of the divergent legacy root is deprecated. Only bounded, current-main-based reconciliation of still-valid capabilities is allowed.
## 3. Master roadmap at a glance

| Phase | Status | Primary exit condition |
| --- | --- | --- |
| 0. Product and repository baseline | In progress | Auditable private-repository lineage, controlled changes, and reproducible source state. |
| 1. Domain and workflow governance | In progress | Governed amendments, blank-opening semantics, visual approval, and no destructive scope replacement. |
| 2. Governed source libraries | In progress | Immutable, published, auditable technical and commercial releases. |
| 3. OpenClaw and controlled-write architecture | In progress - Gates A-F locally complete | Revalidate the deployment boundary for other environments; later phases still require their own controlled profiles and approvals. |
| 4. Mission Control integration | In progress | Visibility/control-plane integration without owning estimate truth. |
| 5. Evidence intake and evidence resolution | In progress; selected-Defect human review complete with limitations | Every downstream claim traces to retained report, page, image, and verified higher-detail source evidence. |
| 6. Physical Model engine | In progress; limited 5/6/6 proposal-only record exists | Defensible Barrier-Opening-Service model or explicit limitation for every known defect. |
| 7. Independent visual topology gate | In progress - controlled-UAT rollback/review proof complete | Independent non-mutating visual challenge is proven; durable canonical receipt enforcement and broader evidence remain. |
| 8. Corrected real Physical UAT | In progress and blocked on unresolved physical evidence and durable validation/lock gates | Semantically approved corrected physical model and replacement active Physical Model Lock. |
| 8C. Automated Physical-Model Accuracy Programme | Planned | Measured, leakage-safe reduction of human exception review; optional governed model training only after prototype evidence. |
| 9. Technical system selection | Blocked by Phase 8 | One current, defensible Repair Strategy Lock per supported Opening. |
| 10. Quantity and labour | Blocked by Phase 9 | Deterministic, authorised, complete quantities and labour. |
| 11. Commercial recovery | Blocked by Phases 9-10 | Every required component recovered once with traceable commercial basis. |
| 12. Independent validation and snapshot | Blocked by Phases 8-11 | No unresolved validation blockers and an immutable reproducible snapshot. |
| 13. Output and proposal generation | Blocked by Phase 12 | Snapshot-backed, reconciled technical and client-facing outputs. |
| 14. Human Release | Blocked by Phase 13 | Human acceptance of the exact validated snapshot and production checklist. |
| 15. Production hardening | In progress; substantial tested branch candidates remain unmerged and undeployed | Secure, observable, recoverable, reproducible production operation and qualified automation. |
| 16. Deferred structural steel and ductwork | Planned - deferred | Separate approved design, source authority, calculations, and acceptance evidence. |

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

1. Resolve the current Validator evidence block and obtain a semantically approved proposal before persisting any lock-eligibility receipt.
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
- Shared main includes a read-only `sessions.describe` readiness probe and authenticated literal-loopback Gateway fallback when the pinned CLI cannot provide the required RPC path. The probe creates no session or inference request.
- The representative package uses trusted operator-created configuration and a disposable SQLite/storage snapshot. It is controlled UAT tooling, not a cryptographic, expiring, single-use production authorisation format.

The August 26 pushed candidate stack adds scan-bound inference receipts and a
restricted transport-receipt sidecar after durable malware attestation. That
candidate architecture is not on shared main or deployed. Historical v17/v8
evidence predates the contract and cannot acquire it retroactively.

### Remaining work

1. Reproduce installation and controlled-write plugin deployment on a clean machine and in each target environment.
2. Complete operation, restart, recovery, timeout, credential-handling, and approved-package custody runbooks.
3. Maintain provider/model/configuration receipts without logging tokens, signed URLs, or private report content.
4. Validate policy propagation from UAT runner code into production services.
5. Before production use, define cryptographic package authority, expiry/replay policy, and a pinned Gateway-command identity rather than accepting trusted local operator configuration alone.
6. Review and operationally prove the candidate scan-bound transport contract without weakening role or canonical-write separation.

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
- Verified or revalidated cached JPEGs can be retained by content hash as immutable technical evidence, bound to an exact active embedded-image parent, page, and photo identity, with redacted retrieval provenance and an audit event. The retention boundary enforces the physical-model mutation guard, is replay-idempotent, and does not commit its caller's transaction.
- Shared main also accepts an exact immutable report-PDF parent only when report hash, page, photo metadata, native dimensions, and source bounds agree. Full-report retrieval remains complete while retention and inference are restricted to current retentions and explicitly mapped ready parents for the selected defect; unlisted same-Defect visual rows are excluded.
- Open PR #74 provides a governed intake contract if new site, remote-supervised, or documentary evidence later becomes available. The contract remains unmerged and creates no evidence, Opening, Service, link, canonical model, admission, or lock.
- Stale low-resolution conclusions are not allowed to suppress high-detail re-review.
- Some model-visible attachments are rehashed immediately before transport,
  but the general linked-image operation does not yet bind scanning, decode,
  dimensions, hashes, and transport to one immutable byte buffer.
- The pushed photo-inventory candidate validates every declared package photo
  row before retrieval, cache reuse, transport, retention, or inference. It is
  not shared-main implementation.
- The retained representative pass proved that higher-detail retrieval can still end in correct abstention: the originals did not resolve every physical relationship or quantity.

### Remaining work

1. If additional evidence becomes available, govern and retain only what is needed for dimensions, depth/boundaries, exact substrate, service labels/material proof, and opposite-face continuity. Until then, preserve those facts as unresolved; the 7+4 review handoff itself is complete.
2. Make one bounded immutable byte buffer the source for malware scanning,
   decode, dimensions, hashing, retention, receipts, and transport; add path-
   substitution and oversized-padded-image regression tests.
3. Generalise the linked-original workflow across multiple report formats and approved source hosts.
4. Build a governed evidence-family taxonomy for exact duplicates, re-encodes, crops, annotations, alternate angles, and genuinely distinct images.
5. Add multi-report evidence-quality metrics and adversarial retrieval tests.
6. Define a production evidence-retention, redaction, deletion, and data-rights policy.

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

**Status:** In progress - controlled-UAT proof and durable receipt registry complete; signed lock enforcement remains

**Objective:** Independently challenge a Physical proposal against the same retained evidence before canonical submission.

### Verified behaviour

- Historical controlled-UAT evidence shows Physical and Validator roles inspecting independently scoped visual evidence. Shared main now enforces that ordering through a dependency-injected controller and strict deterministic receipt.
- Shared main gives Validator corrections bounded authority and fails closed on malformed receipts, proposals, correction inputs, and ambiguous size-or-quantity authority.
- Shared main validates a proposal-blind Opening/Service inventory and requires each blind observation to receive one evidence-backed reconciliation disposition.
- A non-supported or incomplete correction fails closed with limitations.
- Evidence manifests, implementation revision, models, prompts, runtime policy, sessions, transports, stage requests, stage results, and protected-state fingerprints are receipt-bound.
- Proposal-only operation prevents visual agents from submitting or locking the canonical model.
- Shared main has a managed literal-loopback OpenResponses runtime that revalidates every retained image immediately before upload, binds deterministic prompts and the resolved provider/model, creates only fresh metadata sessions, requires a runtime empty-tool attestation, reads its token lazily, audits each attempted turn, and rejects any tool action or non-strict JSON response.
- Logical Physical and Validator roles are bound to separate configured OpenClaw identities. Both installed pinned zero-tool v2 profiles have independently verified empty live tool inventories, Docker sandboxing, no workspace access, and no elevation.
- One configured synthetic retained-image inference completed through the Validator identity with a valid strict payload and receipt. It recorded no tool calls, no human-reference visibility, no canonical-state connection, no canonical write, and no lock.
- A post-inference validation-only comparator binds proposal, controller receipt, and reference inputs by path and SHA-256 and detects topology/substrate swaps. It has no database or inference interface, and no real-UAT human reference fixture was copied to main.
- A representative rollback-only pass completed through the independent Validator. Retrieval succeeded, the result was `VISUAL_PROPOSAL_BLOCKED`, human-reference comparison was correctly skipped, and protected canonical state remained unchanged.
- Current local recovery tooling can reconstruct the blocked review request from receipt-bound local sessions without another inference request. Recovery proves the recorded local lineage and payload hashes, not immutable session custody or replay of Gateway/transport guarantees.

### Remaining work

1. Preserve the completed human-review decisions and remaining site-dependent unknowns; do not repeat the unchanged run merely to seek a different answer.
2. Repeat proposal-only validation only when evidence or approved candidate inputs materially change and current run authority exists.
3. Shared main implements the immutable `VisualValidationReceipt` registry and exact side-effect-free eligibility verifier. Design, approve, and enforce the separate signed lock-admission boundary that must call that verifier after semantic approval.
4. Broaden adversarial visual-gate tests beyond the current report.

### Exit condition

An independently validated, durable visual receipt is required for every canonical Physical Model Lock candidate.

## 12. Phase 8 - Corrected real Physical UAT

**Status:** In progress; human review complete with limitations, blocked on unresolved physical evidence, semantic acceptance, and signed lock gates

**Objective:** Replace the known-wrong retained physical state with a visual-validated, defect-level defensible Physical Model.

### Current verified milestones

1. The old incorrect unlocked physical state was removed through controlled reopen while preserving evidence, defects, and historical lock records.
2. Proposal-only safety, protected-state integrity, bounded correction policy, blind reconciliation, deterministic controller/receipt orchestration, the retained-evidence adapter, linked-original runner, and validation-only comparator are implemented on shared main.
3. Shared main includes the trusted representative package, report-derived parent validation, full-report/defect-scoped evidence handling, no-write readiness, enforced database rollback and post-rollback protected-state checks, blocked-review output, offline recovery tooling, and the durable receipt registry.
4. An earlier full-resolution UAT and human adjudication produced the provisional 17/22 proposal; the retained v6 preflight normalised it to 17 Openings, 24 Services, and 24 links without writing canonical state.
5. The newer representative pass retrieved every required linked original, used only the selected defect's retained evidence for inference, and safely stopped at a valid Validator block. Protected state was unchanged after rollback; no canonical submission or lock occurred.
6. The blocked review request was recovered locally from all receipt-bound successful stages. The recovery is content-safe and hash-bound but expressly does not make mutable local OpenClaw history immutable or replay Gateway and external transport evidence.
7. Human review v2 accounts for all seven review items and four unresolved observations. Shared-main validators pass the limited 5/6/6 proposal-only record while the retained response and unresolved site-dependent facts remain local evidence.

### Current gate

The representative package, review safeguards, and durable receipt registry are
merged on shared main. No site, remote-supervised, or documentary follow-up
evidence is currently available, so the facts the human review could not
establish remain unresolved. Corrected PR #74 can govern future evidence intake
but does not create evidence. PR #75 contains PR #74's older prerequisite and
must be recalculated before it can produce a qualified assumption-led
commercial proposal; it is not evidence resolution,
canonical preflight, signing, submission, locking, technical selection, or an
unchanged rerun. The earlier 17/24 preflight remains historical no-write evidence
and cannot be reused as admission authority.

Post-run output/recovery hardening changed the source tree. The retained
representative receipt therefore proves its exact historical source; the later
shared-main focused tests and recovery receipt are separate verification
evidence. Do not describe the retained run as exact execution of a later commit
or shared-main revision.

### Required evidence resolution

1. Preserve the completed v2 item-coverage record and its exact evidence/proposal bindings.
2. If future evidence becomes available, govern it for dimensions, depth/obscured boundaries, exact substrate, service labels/material proof, and opposite-face continuity; never infer concealed facts from appearance or commercial assumptions.
3. Revise the proposal/adjudication lineage only where new evidence and issue authority support the change.
4. Run proposal-only validation again only after a material governed input change, current report/inference authority, and a fresh source-bound package.
5. Preserve the persisted durable visual-validation receipt and exact eligibility verifier on shared main, then design, approve, and enforce the separate signed lock-admission boundary that must use it.
6. Require valid independent semantic approval before beginning canonical preflight.

### Later required preflight

Before any canonical write:

1. Recompute the protected canonical-state fingerprint and verify the expected baseline.
2. Confirm zero current canonical Openings, Services, links, and active Physical Model Locks for the estimate.
3. Confirm that the evidence-resolved proposal, review decisions, final-state receipt, diff, and comparison receipts bind by current hashes.
4. Confirm controlled-write Gateway health and exact write-tool scope.
5. Confirm no downstream technical, quantity, commercial, snapshot, or output records would be invalidated by the new model.

### Later required canonical operation

If preflight passes and the authorised approver directs it:

1. Deploy and verify the admission-bound writer through the [controlled-writer deployment runbook](./ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md).
2. Produce a fresh no-write preflight and obtain a separately governed, externally signed admission manifest bound to that exact payload and protected-state fingerprint.
3. Register the admission offline, then obtain separate current authority to submit the exact evidence-resolved Opening-Service proposal by admission ID.
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

Shared main contains lower-level technical and rule foundations, while the
divergent legacy root contains additional guarded-technical and repair-strategy
modules/APIs. Those root-only modules are review candidates, not current Phase 9
completion, and must not bypass the missing Phase 8 lock.

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

Open PR #75 adds an assumption-led desk-quote candidate using retained project
evidence and governed pricing releases. Because it is explicitly nontechnical
and noncanonical, it does not satisfy this phase's commercial-recovery exit
condition. It also contains PR #74's older evidence-contract prerequisite and
must be recalculated against the corrected contract before dependent review.

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

PR #75's PDF/XLSX desk-quote outputs are provisional proposal artifacts, not
validated-snapshot outputs, and do not satisfy this phase's exit condition. The
separate local XLSX injection-hardening candidate improves file safety only; it
does not make those outputs snapshot-backed or released.

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

### Verified candidate progress

Current-main-based pushed branches implement active-user checks, opaque
server-side human sessions and revocation, migration `0010_human_sessions`,
fail-closed production configuration/bootstrap, complete schema readiness,
quarantine-first ClamAV scanning, durable content-bound attestations, migration
`0011_malware_scan_attestations`, scan-bound inference receipts, and validation
of every declared package photo row. A clean committed local integration
reports one Alembic head and passed the retained integrated test scope. An
uncommitted XLSX candidate passed focused and integrated safety checks.

This is candidate progress only. No combined pull request, shared-main merge,
live migration, production scanner operation, deployment, or release is proven.

### Required production gates

- Clean-machine deployment, dependency locking, migration, configuration, and recovery evidence.
- Security tests for malicious evidence, prompt injection, path traversal, formula injection, secret leakage, and cross-role escalation.
- Backup, restore, rollback, audit, monitoring, and incident procedures.
- 10-, 100-, and 1,000-defect performance and cost benchmarks.
- Snapshot/output regression and release reproducibility.
- Phase 8C qualification evidence before expanding automation beyond controlled proposal assistance.
- Existing-database baseline adoption and upgrade evidence through `0010` and
  `0011`, including rollback and recovery.
- Governed malware-scanner availability, signature updates, failure handling,
  retention/deletion, observability, and incident response.
- Review and correction of linked-image single-buffer exact-byte identity.

### Exit condition

Production operation is reproducible and observable; controlled automation is independently qualified; security, data governance, recovery, performance, and human-release controls are proven.

## 21. Phase 16 - Deferred structural steel and ductwork

**Status:** Planned - deferred

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

These documents describe shared-main implementation and the explicitly named
open branch candidates with their governed boundaries. Runtime receipts and
customer evidence remain retained locally and must not be published merely
because their non-sensitive status is summarised here.

- [CLASSIFIRE Architecture](./CLASSIFIRE_ARCHITECTURE.md)
- [Current Project State](./PROJECT_STATE.md)
- [Current Session Handoff](./SESSION_HANDOFF.md)
- [Phase 8 Representative Run Package](./PHASE8_REPRESENTATIVE_RUN_PACKAGE.md)
- [Admission-Bound Canonical Writer Deployment Runbook](./ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md)
- [External Signer Operating Model for Adjudicated Admissions](./ADJUDICATED_ADMISSION_EXTERNAL_SIGNER_OPERATING_MODEL.md)
