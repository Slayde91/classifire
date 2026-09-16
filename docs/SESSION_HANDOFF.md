# CLASSIFIRE Session Handoff

Reconciled 2026-09-17 against GitHub, current source and private validation receipts.
Repository evidence outranks this checkpoint. The full production goal remains incomplete.

## Runtime implementation and completed publications

The verified runtime implementation baseline is
`009cbc9766c4990b937acb2ca4720a17628e927d`.

| PR | Published change | Verified merge | Successful PR run | Post-merge run |
| --- | --- | --- | --- | --- |
| #286 | saved Scope chat links | `c0f136b` | `35073202070` | `35076785315` success |
| #287 | decimal precision | `190dc17` | `35073214715` | `35076773492` success |
| #288 | due single-row worker claims | `b2f8785` | `35073227113` | `35076802648` success |
| #289 | Draft work/evidence log | `1d69255` | `35090914391` | `35094148466` success |
| #290 | governed Draft work photos | `009cbc9` | `35104192275` | `35108706394` success |

PR #290 merged normally with parents `1d69255` and `11b06ca` after the exact
read-only gate passed every head/base/file/CI/review/rules/merge-tree check. The feature branch
remains. No job was restarted, no control was bypassed and no branch was deleted. A superseded
old-head run `35102471364` failed after 1,877 passes on a stale migration-history expected
table set; two test-only expectation corrections then passed locally and in exact-head CI.
The old failed run remains evidence, not a result for the final head.

Exact post-merge run `35108706394` passed every configured job at merge `009cbc9`.
The final read-only receipt verifies the normal merge parents/tree, exact main and successful run.

## Merged Draft work-photo boundary

The existing Work log now supports:

- a separate Draft-owned `draft_work_photo_sources` table through forward migration0051;
- explicit JPEG/PNG retention and a separate malware-scan/validation action;
- a fixed subprocess image parser capped at 25 MiB, 50 megapixels and 12,000 pixels per side;
- exact stored-file id/hash/size binding, current-scan/quarantine and same-Draft checks;
- optional explicit photo selection on work records, capped at 20 distinct sources;
- `CLASSIFIRE-DRAFT-WORK-RECORD-v2` for new records while preserving v1 reads/reports;
- exact selected originals in `evidence/photos/` within the deterministic record ZIP.

The boundary remains Draft and unverified. A photo is supporting evidence, not installation
acceptance, inspection, compliance certification, technical approval, commercial authority or
Human Release. Upload, scan, record confirmation, Scope save and package save are separate
actions. No model, matching, costing or other capability runs implicitly.

Local validation passed 83 focused cases and covered all 114 unique changed tests using only
disposable PostgreSQL15433. Full Ruff, targeted Mypy and full Bandit passed. Full local Mypy
was incomplete only because that Python lacked optional JWT/MCP packages; exact-head CI
installed them and passed full Mypy over 248 source files. Exact-head run `35104192275`
passed 2,787 tests with 9 skips, full Ruff/build/Mypy/Bandit/Alembic checks and the separate
9-case Windows installer job.

Installed Chrome passed upload -> explicit synthetic scan -> select -> no-write preview ->
separate confirm -> HTML/ZIP report -> fresh app/browser profile -> reopen. The reopened ZIP
was byte-identical and contained the exact original PNG and a v2 record. Protected canonical
tables remained empty; provider and implicit-capability calls were zero. All nine screenshots
decode at 1440x1100 with nonblank pixel ranges, and restart screenshot pairs are byte-identical.
The sandbox image viewer/native helper still fails during initialization, so manual pixel
inspection is not claimed. Real scanner efficacy remains untested.

## Runtime and model boundary

No activation occurred. Live PostgreSQL15432 was never used. Port8820's last recorded
operational receipt remains rollback `6c1e2a4` with chat disabled; this work did not refresh
that process or database.

Both prior single model allowances are consumed. The `3911ca4` request returned valid
structured advice but failed semantic review. The owner separately approved exactly one
`b2f8785` synthetic `gpt-5-mini` call. Its 14,299-byte request and six CI bindings passed
67 offline safeguards, then the guarded wrapper timed out after 30,108 ms with no HTTP status
or response bytes. No reply exists for semantic assessment; provider processing or cost
remains unknown. Do not retry either request. No activation followed. Any further provider
call needs a new exact plan and separate approval.

## Local safety and evidence

The conflicted `C:/CLASSIFIRE` root remains recovery evidence at `de0cc5a`: 46 modified
tracked files, 14 staged additions, four DU conflicts, and an incomplete untracked inventory.
Do not clean, reset, resolve, stage or publish it. Latest exact tracked-root comparison passed.
Preserve unrelated branches and changes.

The current local change is docs-only worktree
`C:/CLASSIFIRE/.tmp/docs-post-pr290-state-20260917`, branch
`docs/post-pr290-state-20260917`, based on `009cbc9`. It records the already merged
runtime; it grants no activation and must contain only the reviewed documentation paths.

Private evidence under `C:/CLASSIFIRE/.tmp/`:

- `work-photo-browser-acceptance-20260916/acceptance-completion.json`: final rendered v2
  journey, source hashes, exact ZIP, database write log and visual-inspection limitation;
- `work-photo-browser-acceptance-20260916/local-validation-completion.json`: final head,
  114 changed tests, wheel/static checks and root receipt binding;
- `work-photo-browser-acceptance-20260916/readonly-gate-20260916T142735986629Z.json`:
  passed exact PR #290 merge gate;
- `work-photo-browser-acceptance-20260916/readonly-postmerge-20260916T150151745037Z.json`:
  passing final merge identity and exact post-merge CI receipt; the earlier pending receipt remains;
- `work-record-browser-acceptance-20260916`: #289 publication and tracked-root receipts;
- `chat-grounding-diagnostic-b2f8785-20260916`: exact approval, 67-case offline receipt
  and consumed timeout evidence. It grants no retry or activation.

Private scripts, profiles, screenshots, originals, ZIPs, receipts, credentials and customer
evidence stay outside Git. Tests use fresh owned databases on PostgreSQL15433, never live15432.

## Resume order and remaining limits

1. Validate and publish only the five reviewed documentation files through the normal PR/CI
   workflow. Do not repeat #290's browser, provider or local test journeys.
2. The next bounded product slice is paired PDF/XLSX output from one immutable saved work-record
   revision and its exact selected evidence. Reuse existing report services and versioned
   renderers; preserve unknowns and separate confirmation. Output grants no inspection/sign-off
   or Human Release authority.
3. Do not activate or migrate an operational database. Any adoption needs a current
   candidate-specific backup, disposable restore/migration, restart and compatible rollback
   plan plus separate approval. Migrations0050/0051 refuse destructive downgrade.
4. Do not retry consumed provider diagnostics. Preserve unknown physical facts, human
   confirmations and independent capability boundaries.

PDF/XLSX work reports, ProjectPackage work history, real scanner efficacy,
inspection/sign-off semantics, representative accuracy, operational activation and canonical
Phase8-16 exits remain unfinished.
