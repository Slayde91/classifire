# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST).
**Product health:** pre-production foundations; independent capability UI prototype not yet demonstrated.
**Verified shared-main baseline:** `3b437dad9e42ec7ba2adf512b8ee67816d243473` (PR #186).
**Latest executable-change baseline:** `73c428e` (PR #185).

## Approved direction and current task

The user explicitly approved [ADR 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md)
and prioritized a working, testable UI prototype before broad refinement.
It refines the accepted hybrid [ADR 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md):
four independently callable capabilities, shared deterministic core, optional AI,
versioned artifacts and user-controlled continuation. Approval is complete;
implementation remains partial. No further approval of that direction is pending.

**Next engineering task: P0, a persisted Draft Scope workspace in the existing UI.**
Build its minimum contract together with the screen, save/reopen, validation and
exact JSON download. The former package-exporter-first task is superseded as the
immediate priority. A complete schema alone is not the prototype.

This session changes planning/guidance only. It does not claim a new working UI,
new runtime behavior, customer-data acceptance or production readiness.

## Implemented foundations and actual gaps

| Area | Verified source foundation | Remaining product gap |
| --- | --- | --- |
| UI/API | FastAPI/Jinja, login/CSRF, project/estimate pages, manual physical forms and scoped proposal-review pages (`main.py`, `ui.py`, `proposal_review_admin.py`, templates) | No independently persisted Draft Scope workspace or four-capability product flow. Existing opening/service forms write governed canonical rows. |
| Scope/evidence | Exact retained-byte ownership, PDF/bounded XLSX/DOCX locators, approved scopes/families, proposal controller/runners and review package lifecycle | Report runners remain service-only; no user-facing full report analysis flow. Broad formats/visual interpretation remain limited; unsupported content must stay explicit. |
| Physical authority | Distinct Defect/Opening/Service/links, admissions, guarded writes, amendments and replacement-lock services | Draft editing must use an explicit non-authoritative state boundary; historical real-UAT acceptance/lock status was not refreshed. |
| Technical | Source-bound Draft/review/revision, eligibility, immutable releases and current authority checks | No independent System Match workspace accepting saved/manual scope with complete applicability results. |
| Estimating | Decimal calculation, basic rates/rules, desk-quote proposal path, snapshot integrity and PDF/XLSX renderers | Independent Estimate artifacts, full component/recovery coverage and inferred-cost reliability remain incomplete. |
| Reporting | Existing canonical export uses active lock and retained snapshot; `build_estimate_snapshot` recalculates | Independent partial Draft reporting must consume supplied artifact snapshots without invoking estimation. |
| Orchestration | PRs #183-#185 completion acceptance, journal and optional transport lifecycle hooks | Managed producer assurance, general worker handlers/recovery and OpenClaw retirement remain incomplete; they do not block manual P0. |
| Packages | Existing narrow proposal/estimate exports plus unmerged local Draft archive candidate | No shipped complete ProjectPackage workflow; independent capability contracts, governed projection/download/import and client parity remain unfinished. |

Paths abbreviated in the table are under `src/classifire/`. Current code/tests
outrank this snapshot; foundations are not end-to-end product completion.

## Project health and verification

- Exact main [CI 33943428434](https://github.com/Slayde91/classifire/actions/runs/33943428434)
  succeeded on `3b437da`; 974 tests passed with 141 warnings in the prior verified
  log. Full static/migration checks passed in that workflow. No new application
  tests or live browser demonstration were run for this documentation task.
- Reviewed current source for UI, authorization, canonical physical writers,
  snapshot recalculation and export gates. Independent architecture and UI audits
  agreed that P0 can reuse the application shell but needs a distinct Draft boundary.
- One packaged migration head remains the previously CI-verified
  `0026_single_active_technical_release`. No migration changed here.
- Main's previously verified metadata reports no enforced branch protection;
  recheck before publication and never bypass failing CI or required review.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw development advisories)
  remain open. Draft PRs #9-#13 are legacy work; PR #187 carries this architecture
  review. Its earlier proposal CI passed; revised-head publication must be verified.
- Production tenancy, privacy, deployment/recovery, real report accuracy and
  canonical release are unproven. A successful prototype will not prove them.

## Local change classification

- Protected root `C:\CLASSIFIRE`: branch `gpt/phase8-linked-original-images`,
  HEAD `de0cc5a`, CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`.
  Existing linked-visual services/tests have four conflicts; staged, unstaged and
  untracked material remains recovery evidence. The root was inspected read-only.
- Active documentation branch `docs/four-capability-architecture-review-20260905`
  in `.tmp/four-capability-architecture-review-20260905`, based on `3b437da`.
  PR #187 originally contained proposed ADR 0002; this update records approval
  and aligns architecture, roadmap, goal, engineering guidance and handoff.
- `.tmp/project-package-draft-20260905`, branch `feat/project-package-draft-20260905`:
  three untracked files (`docs/PROJECT_PACKAGE_V1_CONTRACT.md`,
  `src/classifire/services/project_package.py`, `tests/test_project_package.py`).
  The prior review passed 22 synthetic tests. This session neither edits nor
  requalifies that candidate; reconcile it selectively within the prototype plan.
- Root-level `AGENTS.md` was absent from tracked main despite existing local
  guidance; this branch adds a maintained version without overwriting the legacy
  root copy. No tracked goal file existed; `GOAL.md` records the approved outcome.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT attempt failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Its recorded completion receipt was
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The historical outcome was rollback-only with no controller/runner canonical
write or Physical Model Lock. The receipt and database were not reopened here.
This history neither authorizes a rerun nor blocks synthetic manual Draft UI work.

## Recommended Next Actions

1. **Implement P0: a persisted, editable Draft Scope UI with exact JSON download.**
   Use the [handoff](./SESSION_HANDOFF.md#start-here--next-session), verify newer
   source first, preserve unrelated work, and demonstrate create/edit/validate/
   save/reopen after restart/download with isolated synthetic data and AI disabled.
2. Use feedback from that screen to add safe Scope import/intake, independent
   matching and estimating, and partial PDF/XLSX reports. Build only the supporting
   contracts each visible slice needs; retain all required authority boundaries.
3. Complete whole-project packaging and a thin ChatGPT client over proven shared
   commands, then broaden accuracy, edge cases and production operations based on
   measured needs. Keep OpenClaw retirement on its separate parity-gated track.

Related: [Goal](../GOAL.md), [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md).
