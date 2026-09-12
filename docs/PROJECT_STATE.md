# CLASSIFIRE Project State

Reconciled 2026-09-12 after the authorized controlled Word acceptance and restart.
[The validation record](./WORD_ACCEPTANCE_ACTIVATION.md) distinguishes preparation,
actual application acceptance and remaining connector transport coverage. Exact
operator plans, receipts and generated artifacts remain private and outside Git.
This is an implementation snapshot, not a production-readiness certificate.

## Current position

The modular Draft prototype supports scope creation/review, selected technical
candidate review, independent estimates and four paired PDF/XLSX report profiles.
It has a shared authenticated client adapter and portable selected-project ZIPs.
The accepted hybrid direction (ADRs 0001/0002) remains unchanged. The full production
platform, broad document interpretation and canonical Phase 8-14 exits are incomplete.

| Evidence | Verified state at this checkpoint |
| --- | --- |
| Shared source | `origin/main` eb3ddb3f6ec23bd3ce66d7f7c82b7edaf830c4c2, merge of PR #257; tree matches tested ff0272b |
| Word inspection | PR #252 merged as c5d4774; retained DOCX parsing/pictures and migration 0047 |
| Word review/packages | PR #253 merged as 2fb422e after PR CI 34657065137 succeeded |
| Word client | PR #254 merged as c496baf; source commit 4e2a2b1. PR CI 34662617629 subsequently succeeded; main CI 34662645680 ended cancelled (not a pass). The merge preceded the PR success |
| Parent main failure | Run 34658986190: 1 failed / 1,894 passed. Test dates were collected before midnight and evaluated afterwards; this was a test timing error, not evidence of a weakened production guard |
| Correction | PR #255/18418f3 fixes only the test clock; all 23 targeted tests and hosted run 34662942874 passed. Merged as 7847288 at 2026-09-12 01:12:24 UTC; later run 34664119693 exceeded its 30-minute limit and ended cancelled, not passed |
| Runtime | Authorized synthetic trial activated tested ff0272b after successful post-merge CI; actual user-confirmed Scope and original-bearing ZIP survived an operating-system process restart |
| Migration | Source head remains 0047. Disposable PostgreSQL history/restore checks passed. Actual trial had verified metadata-created lineage; approved startup added only the Word source table, with no fabricated Alembic stamp or downgrade |
| Documentation | PR #256 merged as 1f12e4b after successful exact-head CI; its earlier pending-activation statements are superseded by this checkpoint |
| PostgreSQL correction | PR #257 source ff0272b merged as eb3ddb3 after run 34681923704 passed. Post-merge run 34683024367 passed 2,043 tests and all checks; no job was restarted for an observation timeout |

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
| Client/UI | `draft_client.py`, typed capabilities, evidence tools and durable client requests reuse the same services. Word adds five tools and `review_word_scope`; exact schemas and bounded redacted field errors are exposed | Client proposals require separate same-user browser confirmation. Word application acceptance and actual connected text/image reads are verified. Dedicated connector Word upload/scan and remote attachment retrieval remain untested; Excel transport acceptance must be reconciled separately |

Domain services above are in `src/classifire/services/`; UI/client adapters are
in `src/classifire/`.
The authoritative architecture description is [CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md).

## Verification and health

The controlled Word journey used an actual authenticated browser upload, real ClamAV
scan, retained text/image inspection, connected typed proposal, separate human Scope
and package confirmations, browser downloads and an approved process restart. The
connected Word text/image tools became available and returned the same retained content.
Scope revision 2 retained five source references; its content matched the confirmed
proposal. Quantities and dimensions stayed null. The image was a 12x8 red placeholder,
so text assertions remained provisional rather than becoming invented visual facts.

The 12,847-byte ZIP contained exactly the manifest, saved Scope and byte-exact original
DOCX. Repeated downloads before/after restart matched. All pre-existing Scope revisions,
packages and originals remained exact; 60 other database tables were unchanged. No
matching, estimating, reporting, canonical admission, lock or release ran implicitly.
Runtime policy was unchanged; no OAuth/tunnel configuration change was made.

Preparation passed 159 affected tests, three PostgreSQL regressions, eight SQLite/history
checks, Ruff, Mypy and Bandit. Exact candidate and post-merge CI each passed 2,043 tests.
These are recorded execution results; documentation edits do not rerun or broaden them.
Dedicated connector upload/scan and remote attachment transport are not covered by the
successful browser upload/scan. The complete I2 client transport exit remains open.

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

The ordering below is shared by the architecture, roadmap and handoff. I1 is complete;
I2's authorized application journey is proven. **The next I2 action is to close the
dedicated connector upload/scan transport gap**, without repeating activation or the
completed confirmations. A new source or project needs an explicitly selected synthetic
test context; preserve the accepted project's saved evidence. A blocked external step
does not authorize deployment, customer evidence use or rule changes.

### Immediate next actions

1. **I1 - Complete.** PR #255 corrected the test clock; PR #257 fixed evidenced
   PostgreSQL migration-history compatibility. PR #256 documentation is merged.
   Candidate run 34681923704 and post-merge run 34683024367 passed. Preserve these
   results and inspect new runs when new changes are published; do not restart jobs
   because observation is slow or count the earlier cancellation as success.
2. **I2 - Application acceptance passed; dedicated transport coverage remains.**
   Authorized activation, actual browser upload/scan, connected Word reads and typed
   proposal, separate human Scope/package confirmations, exact ZIP and restart all
   passed. Reuse existing Word client/intake/review/package services and migration 0047.
   The tools are now discoverable; do not rebuild them or repeat OAuth setup.
   Next success criteria: an explicitly selected synthetic DOCX reaches the retained
   source through the actual connected upload tool, explicit connected scan exposes
   the correct text/image hashes, and no Scope/package or downstream state changes
   implicitly. Reconcile the supported local-file/runtime attachment transport before
   calling it; preserve confidential URLs and credentials. Use an explicitly selected
   test destination, and separate human confirmations if further Draft edits are needed.
   Validation: real tool results, retained original/scan/document hashes and read-only
   state comparisons. Unit tests and browser uploads cannot prove this transport.
   Uncertainty: runtime attachment delivery and supported document layouts; this small
   placeholder-image fixture is not representative customer evidence.
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
