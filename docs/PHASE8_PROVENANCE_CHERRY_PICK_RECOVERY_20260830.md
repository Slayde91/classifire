# Phase 8 provenance cherry-pick recovery - 30 August 2026

## Scope

This record documents an isolated recovery decision for the four
delete-versus-add conflicts left by the
interrupted cherry-pick of `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`
(`feat(phase8): add reviewed visual provenance`) in the legacy root checkout.
It is a source-control recovery record only. It creates no canonical evidence,
physical model, technical decision, commercial decision, lock, or release.

## Conflict evidence

The root index has no stage-2 (ours) version for these paths, while the
cherry-pick supplies stage-3 (theirs) versions:

- `src/classifire/services/phase8_linked_visual_run.py`
- `src/classifire/services/phase8_visual_evidence.py`
- `tests/test_phase8_linked_visual_run.py`
- `tests/test_phase8_visual_evidence.py`

The root checkout is materially divergent and remains preserved. This branch
does not resolve or alter its interrupted operation.

## Resolution

Keep the current `origin/main` versions of all four files. Do not transplant
the stage-3 versions from `c3e4c810`.

Reason: current main already includes the accepted successor
`e99b91b5cb62e76b9b1068954cfdc71fad678ec5` with the same feature subject,
merged by PR #71. The older commit is not an ancestor of current main and differs materially from
the accepted successor. Reapplying it would regress the newer implementation
and its tests.

## Per-file decision

| Conflicted path | Resolution |
| --- | --- |
| `phase8_linked_visual_run.py` | Retain the accepted current-main implementation. |
| `phase8_visual_evidence.py` | Retain the accepted current-main implementation. |
| `test_phase8_linked_visual_run.py` | Retain the current-main regression suite. |
| `test_phase8_visual_evidence.py` | Retain the current-main regression suite. |

## Validation required

Run the focused visual-evidence and linked-run tests from this exact
current-main recovery branch. A passing result demonstrates that the selected
newer implementation remains internally consistent; it does not make the
legacy root safe or publish the recovery branch.

## Completion condition

This isolated branch is ready for review when the focused tests pass and its
only diff is this recovery record. A commit, push, pull request, or merge needs
separate explicit authority.
