# CLASSIFIRE Project State

Reconciled 2026-09-14 against the isolated native stack, migration source, retained
validation evidence and GitHub. This is current state, not production certification.
[Architecture](./CLASSIFIRE_ARCHITECTURE.md) defines composition and authority;
[roadmap](./CLASSIFIRE_ROADMAP.md) defines dependencies and exits;
[handoff](./SESSION_HANDOFF.md) gives the exact resume task.

## Current position

The functional Draft prototype provides independent Scope, selected-target Match,
Estimate and four paired PDF/XLSX report profiles. The native assistant now supports
bounded Word/PDF/XLSX evidence journeys and selected Scope edits locally. The full
production platform, representative accuracy and canonical Phase 8-16 exits remain
incomplete. Advice, technical approval, commercial authority and Human Release are
separate; no capability runs merely because an upstream action finished.

| Boundary | Verified position |
| --- | --- |
| Local candidate | `docs/native-evidence-review-20260914`, based on `0f932c1`, with application code at `ef790d1`; documentation-only reconciliation; no upstream |
| Shared main | `97c07786355bbe938696aee56131e3f7aefe9dc6`, the PR #270 diagnostic merge |
| Approved public feature | PR #271 remains open at exact `d864c51`, branch `feat/native-word-attachments-20260913`, base `main`; only its 12 files are approved |
| PR #271 CI | Run `34757320145` failed: 639 passed, one closed-review form assertion failed. No merge and no recorded reviews |
| Local CI correction | `8bce0b0`, one additional test file, is clean and one commit ahead of that feature upstream. Thirty affected tests passed. Separate public approval remains pending |
| Later native work | Later feature, fix, test and documentation commits are local and outside that 12-file public approval; do not push the larger stack through it |
| Operational app | Port 8820 listener remains PID 24324. The last approved receipt is rollback `6c1e2a4` with chat disabled; this inspection did not activate or reconfigure it |

Public feature CI failure is explained by the native attachment's third form. The
prepared strict correction verifies logout, attachment/CSRF/file controls and advice
consent while retaining closed-review and replay protections. It changes no production
code. An unchanged-job rerun is not a correction. Current successful checks and any
required reviews must be observed before merge; record post-merge CI separately.

## Native chat implementation and remaining acceptance

The native panel is part of the working UI, with dock/collapse/resize controls and
typed page/record selection. It uses CLASSIFIRE's configured API transport. The
existing external ChatGPT/MCP connector remains separate and is reused; neither an
embedded signed-in ChatGPT account nor shared external conversation history is claimed.

- **Attachment and evidence:** supported DOCX/PDF/XLSX uploads use existing retained
  intake, explicit scan and exact-byte readers. Preview and consent select bounded
  text/cells and verified PNGs. Original files and omitted evidence are not sent to
  the model. Document contents are untrusted evidence, never application instructions.
- **Scope proposals:** typed additions preserve existing rows, unknowns and source
  references. Selected saved Scope replacements show a field diff and use the manual
  editor. The existing human review saves a revision only after separate confirmation.
- **Saved proposals and decisions:** explicit retention preserves the generation,
  included conversation and disclosed context. Optional identity links one separately
  confirmed or rejected decision to its generation. A confirmation records the exact
  reviewed Scope revision; rejection changes no Scope. Similar later content never
  implies approval. Current rights/source/scan/context checks still apply.
- **Selected portable history:** ProjectPackage v7 offers exclude, proposal-only,
  or proposal plus one exact decision. Package confirmation is separate. Imported
  history stays foreign and read-only and creates no local proposal or approver.
- **Recent corrections:** delayed history replies cannot replace a newer selection;
  proposal-only export remains available after a decision; source/Draft lock ordering
  is consistent; rejection rechecks write permission after lock waits; completed
  rejection removes only its original UI cards. These have reproduced-failure and
  passing targeted evidence, not full production acceptance.

Word/PDF/XLSX synthetic attachment-to-Scope-to-original-ZIP journeys and the earlier
0048 saved-proposal browser journey passed. The newer 0049 decision and v7 history
controls have HTTP, artifact and restart checks, but rendered-browser acceptance
remains unverified: the browser helper failed initialization. No new model or scanner
call followed from reopening, downloading or this documentation reconciliation.

Ordinary advice remains unsaved unless its existing bounded tab-memory option applies.
Raw provider responses, prompt-version reproducibility, full portable AI history,
retention/expiry policy and non-Scope edit contracts remain incomplete. Blank openings
may have zero Services; unresolved links are held for review, never guessed into facts.

Contracts: [assistant interaction](./EMBEDDED_WORKSPACE_CHAT.md),
[native generations/decisions](./NATIVE_WORKSPACE_PROPOSALS_V1_CONTRACT.md),
[selected package history](./NATIVE_PROPOSAL_PACKAGE_HISTORY.md).

## Migration and operational boundaries

Published baseline `97c0778` uses 0047. The local candidate requires
`0049_draft_proposal_decisions`, following `0048_draft_workspace_proposals`.
Both add bounded history tables and refuse destructive downgrade. Attachment/review
adapters and package v7 add no further database migration. Migration identifiers,
package formats and Scope envelope versions are different contracts.

The approved `6c1e2a4` workspace activation previously passed matched backup/restore,
schema/storage and exact older Scope/package/original checks. Operational startup
used metadata without inventing an Alembic stamp. Do not infer that 0048/0049 have
been activated, or that an older binary can read the new schema/packages.

The later `7dbc1cc` advisory activation passed one synthetic browser reply, failed
its follow-up with HTTP 502, and rolled back successfully. The cause remains unknown;
neither billing nor a particular timeout is established. Earlier request allowances
are consumed. Diagnostic PR #270 merged after successful PR CI, but post-merge run
`34753856708` cancelled at 45 minutes, last recorded progress 52%, without a final
suite summary. Cancellation is not a pass and the job was not restarted.

Any new provider test or activation needs a separate exact approval, successful
applicable CI, fresh matched live backup, disposable PostgreSQL 15433 restore and
migration rehearsal, restart and rollback checks. Preserve all newer history and
reconcile post-backup writes before a rollback; code-only rollback is not assumed.
Never rehearse on live 15432. No OAuth, tunnel, allowlist, customer-report or technical/
commercial authority change is included in the local native implementation.

## Implemented capability boundaries

| Capability | Source-backed implementation | Limits and incomplete work |
| --- | --- | --- |
| Scope | `services/draft_scope.py`: separate defects, openings, services and observations; nullable measurements/quantities; multiple service-opening links; revisions/import/export. PDF page, Excel cell/picture and Word structural text/picture review share guarded revision writing | Draft service/opening graph is narrower than the full production physical model: substrate planes, service instances, treatments and richer relationships are not all separate Draft entities |
| Evidence intake | `draft_pdf_intake.py`, `draft_scope_xlsx.py`, `draft_scope_docx.py`, shared `draft_source_intake.py`, bounded parser workers, malware/quarantine and retained-byte checks | Supported formats/layouts are bounded. DOCX structural positions are not pages; pictures expose original content, not Word layout/crop semantics. General OCR/drawings/inspection records and representative coverage remain incomplete |
| Workspace | Shared Projects/Libraries navigation, hierarchy review register, guarded bulk edits, historical selections and saved system/price display | No new domain model or migration. Multi-review packages are merged; automatic pricing/recalculation and comprehensive visual/accessibility/scale acceptance remain incomplete |
| Workspace advice | `draft_workspace_chat.py`, optional transport and UI preview bounded selected saved Scope records with their ancestors and source-reference claims | One live synthetic browser reply succeeded; follow-up failed and rollback restored chat-disabled operation. This is an advisory API panel, not an embedded authenticated external ChatGPT/MCP session. No automatic writes or implicit capability calls |
| Optional AI | `draft_pdf_suggestions.py` and suggestion contracts produce reviewable claims, with uncertainty and human decisions | No general autonomous evidence interpretation or proven replacement of every OpenClaw protection; manual workflow remains available |
| System matching | `draft_system_matches.py`: selected-target retrieval from an authorized retained technical release, immutable candidates, measured constraints/service sizes, human review and dependency staleness | Retrieval is not final suitability. Full configuration/substrate/insulation/installation constraints, bulk technical corpus and representative source coverage are incomplete |
| Estimating | `draft_estimates.py`, `draft_estimate_contract.py`: independent manual lines, explicit rate methods/overrides, decimal arithmetic, revision history and Scope/optional Match dependencies. Retained workbook rate selection exists | Full six-method automatic default derivation, validated extrapolation, yield/productivity/waste/pack/shared-recovery calculations and representative commercial acceptance are not complete |
| A/B pricing | Source profiles and review, A row observations, B system mappings, T9 coverage, T6 recipe links, T13 target-blind rosters and T10 bottom-up preview exist. `draft_pricing_quantities.py` already persists governed Scope-bound quantities (PR #233) | Do not rebuild the first quantity-basis feature. Preview is bounded to supported current confirmed sell-price evidence; unsupported inputs withhold amounts. Calibration, comparison/combination, holdout execution and production pricing activation remain later |
| Reporting | `draft_scope_reports.py` / `draft_estimate_reports.py` and versioned renderers retain paired PDF/XLSX bytes for scope-only, scope-and-system, estimate-only and complete profiles | Draft reports are not canonical release. Do not infer professional acceptance across every input from synthetic examples |
| Portable project | `draft_project_packages.py`, package inspection/materialization and imported-source services support selected revisions, imported origins and optional retained PDF/XLSX/DOCX originals | Local v7 adds explicitly selected native proposal/decision history; packages are not a full database backup or complete project/audit history; library source bodies and unselected artifacts are not automatically included |
| Client/UI | `draft_client.py`, typed capabilities, evidence tools and durable client requests reuse the same services. Word adds five tools and `review_word_scope`; exact schemas and bounded redacted field errors are exposed | Client proposals require separate same-user browser confirmation. Word application acceptance and actual connected text/image reads are verified. Dedicated connector Word upload remains host-policy blocked; successful connected scan and remote attachment retrieval remain unproven; Excel transport acceptance must be reconciled separately |

Domain services above are in `src/classifire/services/`; UI/client adapters are
in `src/classifire/`.
The authoritative architecture description is [CLASSIFIRE_ARCHITECTURE.md](./CLASSIFIRE_ARCHITECTURE.md).

## Verification and health

These are versioned results. They do not sum to a full latest-candidate pass, and
synthetic fixtures do not establish customer accuracy or professional suitability.

| Version / scope | Observed evidence | Limit |
| --- | --- | --- |
| `d33f5ec`, earlier 0048 stack | 2,574 passes, two Windows symlink skips | Predates decisions and later fixes/history |
| `1aeded3`, earlier 0049 stack | Completed exit 0; JUnit confirms 2,593 passes, two skips | Predates v7 and later concurrency/UI corrections |
| `23f5110`, selected package history | Four PostgreSQL cases, three SQLite compatibility cases, 77 regressions and eight final HTTP/UI cases passed in their recorded runs | Targeted coverage, not a new full suite |
| `23f5110`, actual-main restart/recovery | Exact ZIP/JSON across two owned test server processes; 71 tables, 76 rows, schema and retained bytes matched after restore | Test mode, disposable 15433; owner/ACL restoration excluded |
| Word/PDF history round trips | Two explicit retention/Scope/package/import cases passed; exact originals and foreign read-only history | Synthetic reports and injected replies/scans |
| `23ab398`, explicit history selection | Two focused cases and ten history/compatibility regressions passed; nine ZIPs inspected | HTTP/form output, not rendered-browser proof |
| `c2a5157`, lock ordering | Deadlock reproduced; two concurrency and 16 regression cases passed on 15433 | Preserves source locks; not unrestricted concurrency assurance |
| `567e5a9`, rejection rights | Unauthorized rejection reproduced; corrected request returned 403 with no decision/audit; five selected regressions passed | Eighteen deliberately deselected; no claim of broader execution |
| `ef790d1`, rejection display | Delayed-card defect reproduced; all 35 shipped-script Node cases and 16 template/navigation/wrapper tests passed, no skips | Synthetic DOM, no new rendered-browser acceptance |
| Subsequent review | Thirteen complete test files matched 137 prior passing cases to unchanged test content; five saved ZIPs independently inspected, 21 member sizes/hashes and exact originals/history verified | Prior test runs plus new artifact inspection, not a new suite run |

The recovery readers require source-row locks. The completed verification used normal
transactions with a SQL-mutation guard: 346 reads, 26 locks, zero mutation attempts,
and unchanged row/schema snapshots. An initial read-only transaction refusal remains
in the private evidence; no quarantine lock or write guard was removed.

Private evidence under `C:/CLASSIFIRE/.tmp/`:

- `native-decision-full-validation-20260914/run.json` and `full-first.xml`.
- `portable-native-history-validation-20260914` and
  `native-history-http-restart-23f5110-20260914/attempt3/receipt.json`, plus that
  folder's sibling `recovery/continuation-receipt.json`.
- `native-proposal-lock-order-validation-20260914`,
  `native-proposal-rejection-rights-validation-20260914` and
  `native-rejection-display-validation-20260914`.
- `native-history-review-validation-20260914` holds unchanged-test and ZIP evidence;
  `native-document-reconciliation-20260914` records the current document review,
  link/consistency checks and updated per-file range ledger.

Current documentation work adds no application or test changes. Earlier full
Ruff/Mypy/scoped Bandit results belong to their tested versions. A fresh full suite
for the complete current application range and new-control rendered-browser proof
remain before a broad release claim. No real provider/customer run was executed here.

## Preserved acceptance and independent production gaps

The original controlled Word journey is complete within its recorded scope: browser
DOCX upload, actual scan, retained text/image reads, connected typed proposal,
separate human Scope/package confirmations and exact original ZIP after restart.
Do not repeat those confirmations. Its placeholder picture cannot prove visual
accuracy. Dedicated external connector upload remains host-policy refused; browser
upload success does not complete external upload/scan or remote attachment transport.
See [Word acceptance](./WORD_ACCEPTANCE_ACTIVATION.md).

Integrated register/row authoring/source inspection and multi-review packages/reports
are already implemented and merged through PRs #260-#267. Scope-and-system and
Complete profiles retain exact selected review dependencies; Complete uses unchanged
Estimate arithmetic. [Workspace acceptance](./INTEGRATED_WORKSPACE_ACCEPTANCE.md),
[row authoring](./REGISTER_ROW_AUTHORING.md), [multi-review packages](./MULTI_REVIEW_PROJECT_PACKAGES.md)
and [reports](./MULTI_REVIEW_REPORTS.md) preserve their bounded tests and synthetic
browser/restart evidence. PR #267 and its post-merge CI passed 2,399 tests; the later
native stack is not covered by those runs.

The human-reviewed ten-defect Draft reference and comparator are preparation for an
accuracy study, not a measured accuracy result. Representative report/technical/
commercial evidence, unresolved topology and Phase 8/8C gates remain separate.
Technical applicability, six-method price derivation, yield/productivity/waste/shared
recovery, calibration and target-blind evaluation are incomplete. Wider physical
entities, tenant isolation, production jobs, clean-machine recovery/performance,
close-out and protected OpenClaw retirement still need roadmap exit evidence.

Older implementation/publication chronology remains in Git at `0f932c1` in this
file and the prior handoff, with original contracts and private receipts preserved.
Consolidating current state does not erase failed attempts, expired approvals or
historical byte/recovery evidence, or change any production-phase status.

## Local change classification

The current isolated change is documentation only. The reviewed ancestor range has
84 changed files: 75 application/migration/test/configuration files with recorded
review scope and nine documents. The private ledger distinguishes complete-file
reviews from changed-line reviews; it is not a blanket confidentiality certificate
or publication approval. Private source reports, credentials, generated originals,
ZIPs, screenshots and operator receipts remain outside Git.

The root `C:/CLASSIFIRE` remains quarantined at `de0cc5a`: 46 unstaged modifications,
14 staged additions and four DU conflicts, with unrelated untracked files and
permission-denied historical test directories. Its untracked inventory is incomplete.
No root content was staged, resolved, reset or published. See
[local change classification](./LOCAL_CHANGE_CLASSIFICATION.md).

## Recommended Next Actions

1. **Finish current-candidate assurance and prepare a precise publication scope.**
   Use the updated per-file review ledger, inspect the whole diff for private data,
   and run the complete current application suite with selected-checkout PYTHONPATH,
   fresh basetemp and owned disposable 15433. Inspect new decision/package controls
   in a rendered browser when the helper is available. Prepare an exact commit/file
   manifest before seeking broader public approval; do not reuse the 12-file approval.
2. **Resolve the separate public CI gate.** The prepared one-file `8bce0b0` correction
   needs public approval, then new exact-head CI and any required reviews before
   merging PR271. Its equivalent assertion is already in the larger native stack;
   do not duplicate it. Poll existing active jobs; never restart because observation
   expired or treat cancelled/failed/missing results as success.
3. **Complete C1 and operational C2/C3 acceptance.** Diagnose the broader CI/runtime
   limits, then obtain separate approval for the exact prepared provider test and
   activation. Preserve rollback state, consumed allowances and existing confirmations.
4. **Advance the independent product gates.** Broader typed Match/Estimate/library
   actions, I2/N1 connector transport, reviewed technical/commercial semantics,
   T11-T14 evaluation, full physical/history coverage and Phase 8-16 production exits
   remain. No synthetic success grants technical approval, pricing authority or release.
