# CLASSIFIRE Project State

CI status snapshot: 2026-09-12 01:20 UTC. Named runs may finish after this audit;
re-query them before activation or publication decisions.

Reconciled 2026-09-12 against local source, Git diffs, current GitHub PR/CI records,
configuration, migration head and a read-only check of the existing app listener.
This is an implementation snapshot, not a production-readiness certificate.

## Current position

The modular Draft prototype supports scope creation/review, selected technical
candidate review, independent estimates and four paired PDF/XLSX report profiles.
It has a shared authenticated client adapter and portable selected-project ZIPs.
The accepted hybrid direction (ADRs 0001/0002) remains unchanged. The full production
platform, broad document interpretation and canonical Phase 8-14 exits are incomplete.

| Evidence | Verified state at this checkpoint |
| --- | --- |
| Shared source | `origin/main` 7847288511267e78be1de42019bc11d9ec303e40, merge of PR #255 |
| Word inspection | PR #252 merged as c5d4774; retained DOCX parsing/pictures and migration 0047 |
| Word review/packages | PR #253 merged as 2fb422e after PR CI 34657065137 succeeded |
| Word client | PR #254 merged as c496baf; source commit 4e2a2b1. PR CI 34662617629 subsequently succeeded; main CI 34662645680 ended cancelled (not a pass). The merge preceded the PR success |
| Parent main failure | Run 34658986190: 1 failed / 1,894 passed. Test dates were collected before midnight and evaluated afterwards; this was a test timing error, not evidence of a weakened production guard |
| Correction | PR #255/18418f3 fixes only the test clock; all 23 targeted tests and hosted run 34662942874 passed. Merged as 7847288 at 2026-09-12 01:12:24 UTC; current-main run 34664119693 is still in progress |
| Runtime | Loopback 127.0.0.1:8820 still listens under PID 23084. Its preserved checkout is the earlier Excel trial build 8fc4855; this check did not revalidate its database contents or a live ChatGPT journey |
| Migration | `python -m alembic heads` returned exactly `0047_draft_scope_docx_sources (legacy_adjudicated_lineage) (head)`; no live migration was applied |

PR #254 was merged prematurely by `gh pr merge --auto` while its checks were running.
The GitHub protection endpoint currently reports main unprotected. This is an observed
process gap: use explicit exact-head successful-check/review verification before merge.
Do not infer that an accepted merge command proves CI passed, or change repository
protections without authorization.

## Implemented capability boundaries

| Capability | Source-backed implementation | Limits and incomplete work |
| --- | --- | --- |
| Scope | `services/draft_scope.py`: separate defects, openings, services and observations; nullable measurements/quantities; multiple service-opening links; revisions/import/export. PDF page, Excel cell/picture and Word structural text/picture review share guarded revision writing | Draft service/opening graph is narrower than the full production physical model: substrate planes, service instances, treatments and richer relationships are not all separate Draft entities |
| Evidence intake | `draft_pdf_intake.py`, `draft_scope_xlsx.py`, `draft_scope_docx.py`, shared `draft_source_intake.py`, bounded parser workers, malware/quarantine and retained-byte checks | Supported formats/layouts are bounded. DOCX structural positions are not pages; pictures expose original content, not Word layout/crop semantics. General OCR/drawings/inspection records and representative coverage remain incomplete |
| Optional AI | `draft_pdf_suggestions.py` and suggestion contracts produce reviewable claims, with uncertainty and human decisions | No general autonomous evidence interpretation or proven replacement of every OpenClaw protection; manual workflow remains available |
| System matching | `draft_system_matches.py`: selected-target retrieval from an authorized retained technical release, immutable candidates, measured constraints/service sizes, human review and dependency staleness | Retrieval is not final suitability. Full configuration/substrate/insulation/installation constraints, bulk technical corpus and representative source coverage are incomplete |
| Estimating | `draft_estimates.py`, `draft_estimate_contract.py`: independent manual lines, explicit rate methods/overrides, decimal arithmetic, revision history and Scope/optional Match dependencies. Retained workbook rate selection exists | Full six-method automatic default derivation, validated extrapolation, yield/productivity/waste/pack/shared-recovery calculations and representative commercial acceptance are not complete |
| A/B pricing | Source profiles and review, A row observations, B system mappings, T9 coverage, T6 recipe links, T13 target-blind rosters and T10 bottom-up preview exist. `draft_pricing_quantities.py` already persists governed Scope-bound quantities (PR #233) | Do not rebuild the first quantity-basis feature. Preview is bounded to supported current confirmed sell-price evidence; unsupported inputs withhold amounts. Calibration, comparison/combination, holdout execution and production pricing activation remain later |
| Reporting | `draft_scope_reports.py` / `draft_estimate_reports.py` and versioned renderers retain paired PDF/XLSX bytes for scope-only, scope-and-system, estimate-only and complete profiles | Draft reports are not canonical release. Do not infer professional acceptance across every input from synthetic examples |
| Portable project | `draft_project_packages.py`, package inspection/materialization and imported-source services support selected revisions, imported origins and optional retained PDF/XLSX/DOCX originals | ProjectPackage v5 is not a full database backup or complete project/audit history; library source bodies and unselected artifacts are not automatically included |
| Client/UI | `draft_client.py`, typed capabilities, evidence tools and durable client requests reuse the same services. Word adds five tools and `review_word_scope`; exact schemas and bounded redacted field errors are exposed | Client proposals require separate same-user browser confirmation. Word is merged but not activated in the running trial; refreshed discovery and real Word/Excel acceptance are not proven by local tests |

Domain services above are in `src/classifire/services/`; UI/client adapters are
in `src/classifire/`.
The authoritative architecture description is [CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md).

## Verification and health

This reconciliation directly inspected source/contracts, relevant tests, staged/unstaged
root change inventories, current clean worktrees, PR/CI results, dependency configuration,
worker behavior, migration head and the loopback listener. This reconciliation ran 32 DOCX/parser and pricing recipe/evaluation contract tests
(32 passed in 10.15s), validated 53 local links/source references across ten edited
documents, and checked encoding/fences and Git whitespace; historical counts below are prior-run evidence.

Prior local Word feature evidence: 81 distinct selected client/retrieval/auth/PDF tests,
one Edge client-confirmation journey, Ruff, Mypy (229 source files) and Bandit passed.
Word review/package evidence additionally includes 105 integrated tests, 50 history/output
checks, 73 client/PDF checks and an Edge upload/review/package journey. These are bounded
synthetic checks, not current hosted validation or customer acceptance.

Health: functional Draft prototype, incomplete production assurance. Hosted suites take
close to the configured 30-minute job budget. Main protection is absent at the inspected
endpoint; CI must be explicitly observed. `worker.py` currently fails queued jobs with
“No registered handler”; it is not a production document-processing queue.

The root checkout is recovery evidence at de0cc5a on
`gpt/phase8-linked-original-images`: 46 unstaged modifications, 14 staged additions,
four DU conflicts and CHERRY_PICK_HEAD c3e4c810. Untracked code, migrations, docs,
operator state and generated/private data coexist. No root changes are included here.
See [local change classification](./LOCAL_CHANGE_CLASSIFICATION.md).

## Recommended Next Actions

The ordering below is shared by the architecture, roadmap and handoff. I1's correction
is complete; **I2 preparation is the highest-value next task**, while current-main CI
remains a prerequisite to activation. A blocked
external step does not authorize deployment, real evidence use or rule changes.

### Immediate next actions

1. **I1 — Correction complete; monitor current-main validation.** PR #255 passed
   and merged; do not redo it. Observe current-main run 34664119693 and this docs PR's
   exact-head checks before deployment/publication completion. Evidence: the failed parent
   main run, pending current runs and the unprotected branch. Components:
   `tests/test_technical_activation_boundary.py`, `.github/workflows/pull-request-validation.yml`.
   Dependency: GitHub checks/review; do not restart live runs or auto-merge pending checks.
   Acceptance: correction head/checks/merge are already verified; current-main
   validation is recorded without counting cancellation as success; diagnose actual failures before dependent work. Validation:
   `python -m pytest tests/test_technical_activation_boundary.py`, Ruff and exact GitHub
   run/PR inspection. Uncertainty: hosted duration and any newly surfaced failure.
2. **I2 — Complete one controlled Word client acceptance journey.** Prepare the existing
   synthetic app update, exact commit/migration/backup/rollback plan and read-only preflight;
   obtain activation approval before changing the app/database. Then refresh discovery,
   upload a synthetic DOCX, scan/read text and image, propose, have the user confirm, reopen
   and download a source-inclusive package. Evidence: source is merged; the live app is
   still the Excel build. Components: `scripts/run_draft_scope_demo.py`, Word client/intake/
   review services, client request UI, package services, migration 0047, Word client and
   package tests. Dependencies: I1, explicit activation approval, existing OAuth/tunnel,
   user attachment and human confirmation. Acceptance: actual tool calls and saved hashes
   prove the complete journey, null unknowns remain null, ZIP original matches the source;
   no matching/pricing/technical approval occurs implicitly. Validation: targeted Word/
   client/package tests, rendered browser workflow, recorded revision/hash before/after
   and exact ZIP bytes. Uncertainty: live file metadata/tool caching and supported layouts.
3. **I3 — Establish enforced merge checks as an owner decision.** Present the exact
   main protection/ruleset proposal for approval; do not change access/protection as part
   of documentation. Expected outcome: pending or failing CI cannot merge. Evidence:
   PR #254 incident and protection API response. Acceptance/validation: approved policy
   and a disposable negative-case PR demonstrate enforcement. Until then use the explicit
   manual/guarded check sequence. Uncertainty: repository permissions and selected policy.

### Near-term actions

4. **N1 — Finish the pending real Excel acceptance using the existing integration.**
   Reuse `draft_client_workbook_tools.py`, XLSX review/package services and
   `tests/test_draft_client_workbooks.py` / `test_draft_package_xlsx_evidence.py`.
   Depends on refreshed tools, synthetic attachment and human confirmations, not new OAuth.
   Done: retained workbook -> reviewed Scope -> exact original-bearing ZIP is demonstrated
   with actual calls and hashes. No current proof is claimed; metadata availability remains
   an integration uncertainty. Avoid rebuilding already implemented tools or packages.
5. **N2 — Validate representative quantity/recipe meaning before extending pricing.**
   Use the existing T6/T9/T10 path, quantity-basis UI, bottom-up service and tests
   `test_draft_pricing_quantities.py` / `test_draft_pricing_bottom_up.py`.
   Depends on authorized representative sources and reviewed units/commercial basis.
   Done: documented supported/withheld cases establish semantic correctness, no double
   recovery and exact repeatable amounts; approved gaps define the next small UI change.
   Validate source/Scope/recipe staleness, unit parity and browser/exact JSON output.
   Uncertainty: pack/yield/productivity/shared-work rules cannot be invented from test data.

### Later or dependency-bound actions

6. **L1 — Broaden evidence/corpus and portable history through bounded UI slices.**
   Retain T2-T8, full physical entities and complete project history in the roadmap.
   Extend existing intake/models/package contracts only after representative acceptance
   defines unsupported formats/history requirements. Validate parser containment, old
   artifact compatibility, migration/restore, pagination and measured capacity. Current
   evidence: bounded DOCX/XLSX parsers, selected-only package contract and handlerless worker.
   Uncertainty: supported workload, retention and storage cost are unmeasured.
7. **L2 — Production/hybrid assurance and advanced pricing.** Preserve T11-T14 and
   Phase 8-16 gates, independent evaluation, provider egress/privacy, tenant isolation,
   backup/restore, operational observability, protected writes and human release.
   Dependencies: approved semantic evidence and replacement-protection parity. Done means
   each retained roadmap exit has current test/runtime/receipt evidence; a prototype or
   model response is insufficient. No OpenClaw retirement, calibrated confidence, fleet
   replacement or production readiness is claimed. Costs/performance need measurements.

Publication and verification details: [SESSION_HANDOFF.md](./SESSION_HANDOFF.md).
