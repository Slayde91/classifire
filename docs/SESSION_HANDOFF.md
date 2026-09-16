# CLASSIFIRE Session Handoff

Reconciled 2026-09-16 against GitHub, current source and private validation receipts.
Repository evidence outranks this checkpoint. The full production goal remains incomplete.

## Shared main and completed publications

Shared main is `1d692556d4c342d363c273b084f5ad736e5dd4df`.

| PR | Published change | Verified merge | Successful PR run | Successful post-merge run |
| --- | --- | --- | --- | --- |
| #286 | saved Scope chat links | `c0f136b` | `35073202070` | `35076785315` |
| #287 | decimal precision | `190dc17` | `35073214715` | `35076773492` |
| #288 | due single-row worker claims | `b2f8785` | `35073227113` | `35076802648` |
| #289 | Draft work/evidence log | `1d69255` | `35090914391` | `35094148466` |

All eight listed CI runs completed successfully at the relevant exact commits. No job was
restarted, no control was bypassed and no branch was deleted. Do not repeat or republish
these changes. The #289 post-merge receipt is
`work-record-browser-acceptance-20260916/readonly-postmerge-20260916T124812353378Z.json`.

## Current direct-photo candidate

Work only in `C:/CLASSIFIRE/.tmp/draft-work-photos-20260916`, branch
`feat/draft-work-photos-20260916`, based on merged `1d69255`. The candidate adds:

- a separate Draft-owned `draft_work_photo_sources` table through forward migration0051;
- explicit JPEG/PNG retention and a separate malware-scan/validation action;
- a fixed subprocess image parser capped at 25 MiB, 50 megapixels and 12,000 pixels per side;
- exact stored-file id/hash/size binding, current-scan/quarantine and same-Draft checks;
- optional explicit photo selection on work records, capped at 20 distinct sources;
- `CLASSIFIRE-DRAFT-WORK-RECORD-v2` for new records while preserving v1 reads/reports;
- exact selected originals in `evidence/photos/` within the existing deterministic ZIP.

The boundary remains Draft and unverified. A photo is supporting evidence, not installation
acceptance, inspection, compliance certification, technical approval, commercial authority or
Human Release. Upload, scan, record confirmation, Scope save and package save are separate
actions. No model, matching, costing or other capability runs implicitly.

The final focused suite passed 83 cases using only disposable PostgreSQL15433. Full repository
Ruff, targeted Mypy and targeted Bandit passed. The rendered installed-Chrome journey passed
upload -> explicit synthetic scan -> select -> no-write preview -> separate confirm -> HTML/ZIP
report -> fresh app/browser profile -> reopen. The reopened ZIP was byte-identical; it contained
the exact original PNG and a v2 record. Protected canonical tables remained empty. Provider and
implicit-capability calls were zero; synthetic scanner calls were one.

Nine screenshots were captured, but the local image viewer and native browser helper both
failed during sandbox initialization. Manual pixel inspection is therefore not claimed. The
rendered DOM, native CDP events, screenshot capture, response bytes, database write log and
fresh-process checks passed. Real scanner efficacy remains untested. Private evidence is under
`work-photo-browser-acceptance-20260916`; preserve the two corrected harness failures recorded
in its final receipt.

## Runtime and model boundary

No activation occurred. Live PostgreSQL15432 was never used. Port8820's last recorded
operational receipt remains rollback `6c1e2a4` with chat disabled; this work did not refresh
that process or database.

Both prior single model allowances are consumed. The `3911ca4` request returned valid
structured advice but failed semantic review. The owner separately approved exactly one
`b2f8785` synthetic `gpt-5-mini` call. Its 14,299-byte request and six CI bindings passed
the 67 offline safeguards, then the existing guarded wrapper timed out after 30,108 ms with
no HTTP status or response bytes. No reply exists for semantic assessment; provider processing
or cost remains unknown. Do not retry either request. No activation followed. Any further
provider call needs a new exact plan and separate approval.

## Local safety

The conflicted `C:/CLASSIFIRE` root remains recovery evidence at `de0cc5a`: 46 modified
tracked files, 14 staged additions, four DU conflicts, and an incomplete untracked inventory.
Do not clean, reset, resolve, stage or publish it. Worktree-registry and status checks show it
remains unchanged. Preserve unrelated branches and changes.

Private scripts, profiles, screenshots, originals, ZIPs, receipts, credentials and customer
evidence stay outside Git. Tests must use fresh owned databases on PostgreSQL15433 with
`CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN=classifire-containment-test-drop-all`. Never
use live15432.

## Private evidence index

All paths below are under `C:/CLASSIFIRE/.tmp/`.

- `work-record-browser-acceptance-20260916`: #289 browser acceptance, publication, merge and
  post-merge evidence; its latest root comparison passed.
- `work-record-validation-20260916`: the original 119-case work-log validation, four inspected
  ZIPs and 333-file wheel receipt.
- `work-photo-browser-acceptance-20260916`: final v2 direct-photo browser acceptance, exact ZIP,
  source hashes, database write log, screenshots and known visual-inspection limitation.
- `work-photo-browser-acceptance-pre-v2-20260916`: superseded pre-v2 acceptance retained as
  history; do not substitute it for the final receipt.
- `chat-grounding-diagnostic-b2f8785-20260916`: exact approval, 67-case offline receipt and
  consumed timeout evidence. It grants no retry or activation.
- `diagnostic-source-b2f8785-20260916`: clean detached diagnostic source, deliberately without
  the work-log/photo migrations.

## Resume order and remaining limits

1. Read this worktree's AGENTS, PROJECT_STATE, roadmap and work-record contract. Verify branch,
   diff, receipts and root preservation before acting.
2. Do not repeat the final 83-case or rendered-browser journeys unless application source
   changes. If source changes, regenerate the bound evidence.
3. Finish package/diff/secret checks, commit only explicit candidate files, push normally,
   open a PR to main, and merge only after exact-head CI/review checks succeed. Observe
   post-merge CI without restarting it.
4. Do not activate or migrate an operational database. Any adoption needs a current
   candidate-specific backup, disposable restore/migration, restart and compatible rollback
   plan plus separate approval. Migrations0050/0051 refuse destructive downgrade.
5. Do not retry the consumed provider diagnostics. Preserve unknown physical facts, separate
   human confirmations and independent capability boundaries.

PDF/XLSX work reports, ProjectPackage work history, real scanner efficacy,
inspection/sign-off semantics, representative accuracy, operational activation and canonical
Phase8-16 exits remain unfinished.
