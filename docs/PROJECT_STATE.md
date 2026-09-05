# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST).
**Product health:** usable manual Draft Scope editing and JSON exchange; scope-only
Draft reporting is implemented and locally exercised. Broader capabilities and
production readiness remain incomplete.
**Verified shared-main baseline:** `e17cec31b571bbcec5153df95c9d4f35b16ed348`,
merged [PR #189](https://github.com/Slayde91/classifire/pull/189).
**Current increment:** `feat/draft-scope-reports-20260905` (P4a).
Local validation and final report/restart evidence passed. This documentation
checkpoint precedes publication; reconcile its exact commit/PR/CI/merge from Git.
Local evidence alone is not a claim that this increment has merged.

## Approved direction and current work

Accepted [ADR 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md) and
[ADR 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md) establish four
independently callable capabilities over shared deterministic services, optional
bounded AI and versioned artifacts. Prototype-first delivery is approved.

**P0 and P1a are merged.** The `/scopes` UI creates, edits, validates, saves,
reopens and downloads manual Draft revisions. Supported saved JSON can be previewed
without writes and explicitly imported as a successor revision. The 15-minute
preview binds exact bytes, destination/revision, actor and session. Imported v2
history survives manual edits and reimport; source identities remain unverified
claims, with local ownership and Draft/unreviewed status assigned by CLASSIFIRE.

**P4a is implemented locally:** select a saved v1/v2 Scope revision, preview its
content and explicitly create a scope-only PDF/XLSX report pair. One database row
retains the frozen Scope envelope, project labels, report/profile/render identities,
and both exact outputs. Downloads verify snapshot and output hashes. Later Scope
or project-label changes show the report as out of date and preserve its old bytes.
No Estimate, technical matching, AI, canonical admission or lock is required or run.

**Next product task after P4a publication: P2a, a saved System Match candidate-review
workspace.** Reuse the governed technical library and existing Scope revisions.
Text search supplies candidates to inspect; it does not prove applicability. P1b
real evidence intake remains required, with separate unresolved scan/retention
prerequisites rather than a global blocker on independent synthetic prototypes.

## Implemented foundations and remaining gaps

| Area | Verified implementation | Remaining product gap |
| --- | --- | --- |
| UI/API | FastAPI/Jinja shell, manual Draft editor and import/preview/confirmation/download; local report selection/detail/download routes | Independent matching/estimating screens and ChatGPT adapter remain incomplete. |
| Draft Scope | Strict v1 manual/v2 imported contracts, ownership, revision/graph/integrity checks, stale-save refusal, exact JSON exchange | Full evidence locators, service instances, independent planes/treatments and structured contradictions remain unfinished. |
| Source intake | Exact-byte ownership and bounded PDF/XLSX/DOCX adapters; proposal runners and review lifecycle | No demonstrated evidence-to-Scope UI. Uploads remain pending/not_configured without a working clean-scan producer; locked clean reads require PostgreSQL. |
| Physical authority | Separate Defect/Opening/Service/link records, admissions, guards, amendments and locks | Draft editing/import/reporting does not satisfy physical admission or Phase 8-14 exits. Historical real-UAT acceptance was not refreshed. |
| Technical | Source-bound Draft/review/revision, eligibility, immutable releases and authority checks | No saved independent System Match workspace. Current five-field text ranking is retrieval, not complete applicability validation. |
| Estimating | Decimal calculations, rates/rules, desk-quote proposals, snapshot integrity and renderers | Independent Estimate artifacts, pricing methods/overrides and full recovery coverage remain incomplete. |
| Reporting | Local `services/draft_scope_reports.py`, `outputs/draft_scope.py`, `DraftScopeReport`, snapshot/output checks, owner/admin routes and stale indication | Final P4a publication/restart evidence pending. Other profiles, production-scale retention and report pagination beyond the newest 20 remain future work. |
| Orchestration | PRs #183-#185 acceptance/journal/transport foundations; manual Draft operations and local reports run without AI/OpenClaw | Producer assurance, general recovery and retirement parity remain incomplete. |
| Packages | Saved v1/v2 Scope JSON exchange preserves historical local revisions and imported metadata lineage | No complete ProjectPackage ZIP, rights/membership projection, raw imported-source attachment store or complete foreign revision history. |

Paths in the table are under `src/classifire/`. Confirmed values in manual/imported
Scopes remain unreviewed assertions. A bounded prototype does not prove complete
Scope Analysis, all four capabilities, tenant privacy or authoritative release.

## Project health and verification

- Shared-main [CI 33949738802](https://github.com/Slayde91/classifire/actions/runs/33949738802)
  succeeded on `e17cec3`: 1,072 tests and 141 warnings, plus required static checks.
- P4a service tests: **50 passed, one local PostgreSQL test skipped**. Reporting
  HTTP tests: **16 passed**. Output tests: **7 passed**. These are separate checks;
  combined regression: **124 passed**; full migration/deployment/preflight: **43 passed**.
  Existing Starlette/Alembic warnings remain. Full Ruff, Mypy (149 files), Bandit,
  JavaScript syntax and whitespace checks passed. Hosted exact-head CI remains a
  separate publication requirement, including the locally skipped PostgreSQL test.
- HTTP tests parsed both PDF and XLSX, verified one frozen snapshot, preserved v1/v2
  lineage and historical bytes, and checked ownership, sessions, CSRF, stale inputs,
  corrupt outputs and no downstream/canonical calls. They exposed a logo sizing
  failure; the renderer fix passed the full HTTP suite.
- The synthetic browser workflow exercised v2 import, saved revision 2 reporting,
  both downloads and out-of-date reporting after revision 3, with earlier bytes
  unchanged. PDF page images and nine workbook tabs were inspected; native Excel
  was used read-only because the available workbook rendering helper was not
  Windows-compatible. Normal output has three PDF pages; long-text output has four.
- Final regenerated reports passed actual restart and exact-byte comparison with
  no browser page errors. PDF SHA-256: `1ed6dbd5f4beda3f720b8095e265bc4899891f2b84c20a0e550fb812c37e6cde`.
  XLSX SHA-256: `c20f1e826854f8fb17424c5376dc5d171ffddc91384c0c21be2b1abb6e480dc8`.
  The report retains three unverified import records. The isolated demo contains
  four Drafts, 11 revisions and three reports from verification, with zero canonical
  defects/openings/services/links/estimates/Physical Model Locks.
- Candidate migration head is `0028_draft_scope_reports`, following existing
  `0027_draft_scope_revisions`. The new table atomically retains snapshot plus PDF
  and XLSX, each bounded to 8 MiB. The UI lists the newest 20 reports; older report
  IDs remain readable. No new library, database or infrastructure dependency.
- Existing JSON import remains bounded to 288 KiB and 16 imported-source records.
  Full source attachments and foreign revision chains are not retained by P1a.
- No customer evidence, real provider execution, operational canonical write,
  Physical Model Lock, deployment or release was performed by this increment.
- Draft content is owner/admin restricted. Existing `/projects` names/references
  remain shared for project readers; full tenant privacy is not established.

## Known dependencies and technical debt

P1b requires a real scanner producer, source retention and verified storage before
parsed uploads are exposed. `save_upload` sets pending/not_configured; `worker.py`
has no registered processing handlers. The optional `clamd` dependency is not a
working scan path. Locked clean-byte reads require PostgreSQL. Resolve the shared
same-filename upload temporary-path concern before general intake. Do not invent a
clean result or change quarantine/authority guards to make a demonstration pass.

For P2a, `release_scope.active_technical_release_ids(db, release)` supports explicit
release selection without an Estimate. Its legacy compatibility permits unbound
variants and older manifests: these must remain visibly unresolved in the new UI.
Current Scope v1/v2 lacks service material/size, FRL and insulation requirements;
no candidate may be called applicable because missing criteria were skipped.
Candidate retention/rejection and review notes are unapproved decisions. Record
exact dependencies and mark later Scope/library/source changes stale, preserving
older artifacts without automatically rerunning matching or estimating.

Report bytes in the database keep this bounded prototype atomic. Measure growth
before changing retention/storage architecture; do not replace a working prototype
with speculative storage infrastructure. Current canonical exports keep their
existing lock gates and estimate snapshot semantics.

## Local change classification

- Protected root `C:\CLASSIFIRE`: `gpt/phase8-linked-original-images`, HEAD
  `de0cc5a`, CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`.
  Four linked-visual conflicts and staged/unstaged/untracked recovery work remain
  untouched. Do not reset, clean, resolve, broadly stage or publish from this root.
- Active worktree `.tmp/draft-scope-reports-20260905`, branch
  `feat/draft-scope-reports-20260905`, based on `e17cec3`: report service/model,
  renderers/UI, migration 0028, related current-head/deployment fixtures, tests and
  aligned documentation. This is the reviewed P4a scope; verify publication from current Git/PR evidence.
- P0 `.tmp/draft-scope-ui-20260905` and P1a `.tmp/draft-scope-import-20260905`
  worktrees are clean and preserved. They retain their prior synthetic demos.
- `.tmp/project-package-draft-20260905` still has three unrelated untracked files:
  `docs/PROJECT_PACKAGE_V1_CONTRACT.md`, `services/project_package.py` and its test.
  Its prior 22 synthetic tests are historical evidence, not current qualification.
- Current synthetic report files/screenshots are under
  `.tmp/draft-scope-report-artifacts`; long-text/hostile output QA is under
  `.tmp/draft-scope-report-output-qa`. Prior import demo/tools/artifacts remain
  local. Generated files, databases, browser cookies and receipts are not PR files.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Historical receipt:
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The recorded outcome was rollback-only with no canonical write or Physical Model
Lock. The receipt/database were not reopened. This does not authorize a rerun.

## Recommended Next Actions

1. Reconcile P4a publication and finish it if outstanding. Local artifact/restart,
   regression/migration/static checks passed; verify exact-head CI and actual merge.
2. **Deliver P2a: saved System Match candidate review** over an explicit Scope
   revision and governed technical release. Provide a usable inspect/keep/reject,
   save/reopen/download flow, missing-criteria explanations and stale dependencies.
   Follow the concrete handoff; do not label text relevance technical approval.
3. Complete evidence intake with its actual scan/retention prerequisites, independent
   estimating and further report profiles; then complete ProjectPackage portability
   and shared ChatGPT access. Retire OpenClaw only after proven protection parity.

Related: [Goal](../GOAL.md), [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md),
[Scope demo](./DRAFT_SCOPE_DEMO.md), [Report contract](./DRAFT_SCOPE_REPORT_V1_CONTRACT.md).
