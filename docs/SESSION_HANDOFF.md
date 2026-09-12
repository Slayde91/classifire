# CLASSIFIRE Session Handoff

Reconciled 2026-09-13. Read [PROJECT_STATE.md](./PROJECT_STATE.md),
[workspace acceptance](./INTEGRATED_WORKSPACE_ACCEPTANCE.md),
[architecture](./CLASSIFIRE_ARCHITECTURE.md), [roadmap](./CLASSIFIRE_ROADMAP.md) and
[the earlier Word acceptance](./WORD_ACCEPTANCE_ACTIVATION.md). Current source,
Git/CI and runtime evidence override this checkpoint. Product direction remains in
root `GOAL.md`; this task does not complete production Phase 8-16 gates.

## Verified source and runtime

- Worktree: `C:/CLASSIFIRE/.tmp/integrated-project-workspace-20260913`, branch
  `feat/integrated-project-workspace-20260913`, base/inspected origin/main
  7dbc59bfa2fd52bd8238a2f7c5a99d71240420cb. The workspace source, tests and docs are
  local changes at this checkpoint; append actual publication results after observing them.
- PR #259 merged diagnostic source e2e8292 as 7dbc59b. Its private receipt records
  successful PR run 34698452617 and post-merge run 34699704284, each 2,066 tests.
  Those results belong to the diagnostic change, not the newer workspace diff.
- The user separately approved diagnostic activation. Fresh backup/restore verified
  all 69 tables, five Scope revisions, two packages and two stored originals. The
  approved restart preserved schema/files and exact Scope/package/original history;
  login-related changes were confined to users/audit events. The saved package route
  returned 200; an expired one-time review link returned 403.
- The actual connected upload still returns CLIENT_FILE_UNAPPROVED_HOST. The diagnostic
  identifies the rejected host privately; no new file or data/schema/file changes occurred
  in the probe. No allowlist or OAuth/tunnel setting changed. Do not repeat activation
  or earlier human confirmations to retry this external transport boundary.
- The integrated workspace browser checks used a separate synthetic app on 8840 and
  disposable PostgreSQL 15433. They do not deploy the workspace to the diagnostic trial.
  Preserve the pinned trial runtime and the conflicted root checkout.

## What the workspace candidate implements

- Shared Projects & estimates directory and six correctly named Libraries, retaining
  existing records, URLs and permission/owner boundaries.
- Spreadsheet-style Draft register with guarded selection/bulk edits, history,
  relationships, saved result projections, source warnings and an optional advice panel.
- The blank-opening clarification is preserved: zero Services is valid for a blank
  Opening. Historical missing/multiple parent links stay in review; no schema rewrite,
  automatic repair or dummy Service is introduced.
- Explicit saved systems/prices appear in the register. They remain immutable saved
  results; Scope edits mark them stale. Full inline matching, overrides and pricing
  authoring/recalculation are not implemented by this display. One Match and Estimate
  can be selected at once. Grid selection is contiguous; column preferences are not
  persisted, and undo covers unsaved grid edits until detailed-editor changes reset it.
- Chat previews bounded selected saved Scope context. Provider settings default disabled
  and remained disabled in browser UAT. This optional API panel is not an authenticated
  external ChatGPT/MCP session. It cannot save/approve data or run downstream capabilities.

## Verification and evidence

- 157 unique affected tests across 12 files passed with zero remaining failures/skips.
  First run: 33 passed and one missing-register template failure. The fail-closed template
  correction preserved assertions. Remaining runs passed 117 and 7 cases. Selected
  checkout PYTHONPATH, disabled cache and fresh basetemps were used; PostgreSQL tests
  touched only `127.0.0.1:15433/classifire_containment_test`.
- Edge navigation checks preserved synthetic IDs and exact Draft Estimate links, with
  no page errors or mobile document overflow. These routed requests through ASGI/SQLite.
- Actual isolated browser UAT performed column bulk edit, undo/redo, saved Scope revision
  3, reopened revision 2 exactly, retained five source references and null quantities,
  displayed stale source claims, and previewed saved chat context. No provider call ran.
- Automated package preview/save/download retained exact Scope 3 and selected original
  DOCX in a 12,706-byte ZIP. It is a synthetic automated confirmation, not human approval
  or repetition of the earlier separately human-confirmed Word package. Scope 3 and
  that same ZIP stayed exact after an isolated 8840-only restart against database 15433.
- Private receipts: `workspace-regression-20260913/validation-receipt.json`,
  `workspace-navigation-browser-20260913/receipt.json`, and
  `integrated-workspace-uat-20260913/` containing `grid-browser-receipt.json`,
  `package-browser-receipt.json` and `restart-browser-receipt.json`. Logs, screenshots
  and generated artifacts remain outside Git.

The original Word acceptance and PRs #252-#258 remain completed historical work;
do not rebuild their intake, client, confirmation or package paths. The new workspace
checks are bounded synthetic evidence, not general multimodal accuracy or production
readiness. A real report has now been supplied for accuracy assessment; keep it private.
Human reference labels and suitable original/linked images remain necessary before
measuring service, substrate or quantity accuracy.

## Local change classification and next work

The current candidate contains UI/navigation/templates/styles, register projection and
editor code, optional bounded advisory transport/configuration, corresponding tests and
this documentation. It adds no domain model, schema, migration or canonical authority.
Private test helpers, logs, screenshots and outputs are execution evidence, not files to
stage. Preserve unrelated changes and the legacy root; its historical conflict inventory
is in [LOCAL_CHANGE_CLASSIFICATION.md](./LOCAL_CHANGE_CLASSIFICATION.md), not a new audit.

1. Review the complete explicit candidate diff, final checks and remaining acceptance
   limits. Record commit/push/PR, exact-head successful CI, required reviews and actual
   merge outcome. Poll existing jobs; never restart because observation timed out.
2. Keep runtime activation, provider enablement and any exact host-policy/OAuth/tunnel
   change as separate explicit approval decisions. Do not broaden the allowlist or grant.
3. Continue accuracy acceptance from an agreed human-labelled report/image sample. Keep
   unknowns and contradictions visible; use existing retained-source/review services.
   Do not infer quantity from row/image count or run matching/pricing/release implicitly.

The full redesign criteria remain incomplete: general accurate multimodal analysis,
complete inline technical/pricing work, live integrated AI, representative performance
and comprehensive usability/accessibility acceptance. The retained technical/pricing
roadmap and production gates remain applicable; no phase is advanced by this handoff.

## Recommended prompt for continuation

```text
Continue CLASSIFIRE's integrated workspace candidate from the verified isolated checkout and acceptance receipts. Inspect AGENTS.md, Git/worktrees/upstream/diff, current PR/CI, project state and runtime. Preserve the conflicted root and the separately approved e2e8292 diagnostic runtime. Do not rebuild completed Word/client/package work or repeat completed human confirmations. Reconcile the workspace's actual publication result, test/browser/package evidence and remaining accuracy, inline technical/pricing and live AI gaps. Keep supplied real evidence private; agree human reference labels and adequate original images before claiming accuracy. No workspace activation, provider enablement or OAuth/tunnel/host-policy change without explicit approval. Use selected-checkout PYTHONPATH and fresh test paths; PostgreSQL tests only on disposable15433. Commit explicit reviewed files, push normally, merge only after observed successful exact-head CI and required reviews, and record actual results and limitations. Poll existing jobs without restarting them because observation timed out.
```
