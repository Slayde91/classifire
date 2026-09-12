# Local change classification — 2026-09-12

This is a publication-scope inventory, not a claim that all legacy work is valid.
Only the documentation reconciliation is included in its commit. No recovery file,
private evidence, runtime credential or generated artifact is copied into the PR.

## Worktrees and logical change sets

| Set | Classification | Treatment / evidence |
| --- | --- | --- |
| Current documentation branch | Ready/intended after document checks | Four maintained documents, requested root entry points, this classification and minimal stale GOAL/AGENTS guidance corrections; no application code |
| Word feature branch `feat/word-client-20260912` | Ready/unrelated to docs | Clean, committed/pushed 4e2a2b1, PR #254 merged c496baf. Local validation and PR CI passed; its merged-main run ended cancelled, not passed |
| Word review branch `feat/word-scope-review-20260912` | Ready/unrelated to docs | Clean c132709, merged PR #253/2fb422e. Its PR CI passed; post-merge date-test failure is tracked separately |
| Test-clock correction `fix/technical-activation-test-clock-20260912` | Ready/unrelated to docs | Clean 18418f3, PR #255 merged 7847288 after hosted CI and 23 targeted tests passed; no test code is restaged here |
| Existing Excel runtime worktree | Uncertain/incomplete for new deployment | Earlier 8fc4855 trial build/PID23084/port8820 retained. No current database-content or live client acceptance audit; no update authorized by docs request |
| Other `.tmp/` worktrees and historical candidates | Uncertain/incomplete | Not individually revalidated or eligible for bulk merge; inspect the chosen logical feature before reuse |

## Root tracked changes

Root remains on `gpt/phase8-linked-original-images` at de0cc5a, tracking the same-named
origin branch; ahead/behind was 0/0 for that upstream at inspection. It is not current
main. CHERRY_PICK_HEAD is c3e4c810. All 64 changed tracked paths below are
**Uncertain/incomplete** and excluded: 46 unstaged modifications, 14 staged additions,
4 DU conflicts. The staged/unstaged diff inventories were reviewed; representative
source and contract hunks show mixed admission, agent-scope, evidence-review, UAT and
provenance work. That does not establish correctness of the entire change set.

```text
 M .env.example
A  docs/PHASE8_EVIDENCE_FAMILY_REVIEW_TEMPLATE.md
A  docs/PHASE8_HUMAN_REVIEW_V2_CONTRACT.md
A  docs/PHASE8_VISUAL_PROVENANCE_COMPLETENESS.md
 M openclaw-plugin-classifire-controlled-write/openclaw.plugin.json
 M openclaw-plugin-classifire-controlled-write/package-lock.json
 M openclaw-plugin-classifire-controlled-write/package.json
 M openclaw-plugin-classifire-controlled-write/src/index.ts
 M pyproject.toml
A  scripts/assess_phase8_visual_provenance.py
 M scripts/install_classifire_controlled_write_plugin.ps1
 M scripts/run_classifire_real_uat_assumptionaware.py
 M scripts/run_classifire_real_uat_defectwise.py
 M scripts/run_classifire_real_uat_deterministic.py
 M scripts/run_classifire_real_uat_fireseals.py
 M scripts/run_classifire_real_uat_fireseals_topologyaware.py
 M scripts/run_classifire_real_uat_fireseals_visualvalidated.py
 M scripts/run_classifire_real_uat_fireseals_visualvalidated_proposal_only.py
 M scripts/run_classifire_real_uat_intake.py
 M scripts/run_classifire_real_uat_integrated.py
 M scripts/run_classifire_real_uat_layoutaware.py
 M scripts/run_classifire_real_uat_photoaware.py
 M scripts/run_classifire_real_uat_proposal_only_safe.ps1
 M scripts/run_classifire_real_uat_resilient.py
 M scripts/run_classifire_real_uat_windows_safe.py
 M scripts/sync_classifire_agent_scopes.py
 M scripts/test_classifire_controlled_write_boundaries.ps1
A  scripts/validate_phase8_evidence_family_review.py
A  scripts/validate_phase8_human_adjudicated_proposal.py
 M scripts/validate_real_uat_human_physical_reference.py
 M src/classifire/agent_security.py
 M src/classifire/api/agent_intake_physical.py
 M src/classifire/api/physical_model.py
 M src/classifire/api/router.py
 M src/classifire/canonical_models.py
 M src/classifire/cli.py
 M src/classifire/config.py
A  src/classifire/services/phase8_evidence_family_review.py
A  src/classifire/services/phase8_evidence_quality.py
A  src/classifire/services/phase8_human_adjudicated_proposal.py
A  src/classifire/services/phase8_human_review_v2.py
DU src/classifire/services/phase8_linked_visual_run.py
DU src/classifire/services/phase8_visual_evidence.py
A  src/classifire/services/phase8_visual_provenance.py
 M src/classifire/ui.py
 M tests/test_agent_intake_physical_api.py
 M tests/test_migrations_fresh_install.py
 M tests/test_openclaw_controlled_write_manifest.py
A  tests/test_phase8_evidence_family_review.py
A  tests/test_phase8_evidence_quality.py
A  tests/test_phase8_human_adjudicated_proposal.py
DU tests/test_phase8_linked_visual_run.py
 M tests/test_phase8_role_policy.py
DU tests/test_phase8_visual_evidence.py
 M tests/test_phase8b_proposal_only.py
 M tests/test_physical_evidence_read_boundary.py
 M tests/test_physical_model_lock.py
 M tests/test_real_uat_assumptionaware_runner.py
 M tests/test_real_uat_fireseals_topologyaware_runner.py
 M tests/test_real_uat_human_physical_reference.py
 M tests/test_real_uat_photoaware_runner.py
 M tests/test_real_uat_resilient_runner.py
 M tests/test_validator_read_only_boundary.py
 M tests/test_visual_validated_uat_gate.py
```

The four DU paths are unresolved conflicts, not ordinary deletions. No reset, clean,
stash, conflict resolution, root commit or publication was performed.

## Untracked groups

Every top-level/directory group returned by `git ls-files --others --exclude-standard
--directory` is covered below. Full recursive status traversed large nested worktrees
and reported inaccessible historical test directories; no claim of complete readable
contents or readiness is made. Scope is deliberately classified by logical group.

| Paths/groups | Classification | Reason |
| --- | --- | --- |
| `.codex/`, `.config/`, `.vscode/`, `CLASSIFIRE.code-workspace` | Unsafe to include | Machine/operator/editor state; no reason to publish and possible private configuration |
| `.pytest-*/`, `.tmp-layer4-pytest/`, `.venv-cp314-backup-20260812/`, `Temp/`, `data/test-temp/` | Unsafe to include | Generated caches, environments/test artifacts and inaccessible descendants |
| `.tmp/` | Unsafe to bulk-publish; individual feature worktrees uncertain unless verified above | Contains operator settings, local scripts, synthetic artifacts and many independent worktrees; only explicit reviewed paths in the chosen checkout may be staged |
| `private-data/`, `data/real-uat/`, `data/uat/`, `data/gate-b-live-change-window-20260820/`, `data/gate-b-rehearsal-20260820/` | Unsafe to include | Private/operational evidence and receipts; no redistribution authority inferred |
| Root `AGENTS.md`, `agent-definitions/`, `tools/`, `openclaw-plugin-classifire-controlled-write/scripts/` | Uncertain/incomplete | Local instruction/tool/control-plane work; do not override current tracked instructions or install it implicitly |
| Root `classifire logo.png` | Uncertain/unrelated source asset | Approved branding source exists; current tracked UI asset is separate. No re-generation or replacement needed in this documentation task |
| Untracked `docs/*.md`, `docs/reports/*.pdf` | Uncertain/incomplete | Historical guidance/exported reports; not current implementation proof or automatically safe publication material |
| Untracked `migrations/versions/*.py` | Uncertain/incomplete | Legacy migration lineage differs from packaged current migrations; do not copy/rewrite history |
| Untracked `scripts/*.py`, `src/classifire/*.py`, `src/classifire/services/*.py`, `tests/*.py` | Uncertain/incomplete | Admission/submission/recovery/technical extraction implementations and tests not validated as a coherent current-main patch |

No secrets or customer contents were read to decide these publication classifications.
“Unsafe to include” means excluded from this public documentation commit, not permission
to delete the files. Existing local work remains intact.
