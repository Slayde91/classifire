# Selected native proposal history in ProjectPackage

Local implementation with passing targeted validation. This contract does not establish successful CI,
public publication, activation, browser acceptance or full production AI lineage.

## User interaction

The existing package configuration offers optional, initially unchecked saved AI proposals.
Selecting history discloses that the question, included conversation, selected application
context and generated reply will travel in the ZIP. This can include private project,
technical or pricing data. Only the retained request conversation is included; this is not
an export of every chat message. Ordinary unsaved advice has no portable history record.

Each selected proposal pins either one recorded decision identity or explicitly no selected
decision. Preview checks the original generation and selected decision before the existing
separate package save. A decision recorded later cannot be substituted into an old package.
No selected decision does not claim that no decision exists now. Changed selections need
a new preview/save; Scope confirmation and package confirmation remain separate actions.

Saved package and imported-package pages provide one-item-at-a-time read-only inspection
and exact JSON download. These views have no proposal-restoration or Scope-confirmation
controls. Reopening never dispatches generation, scanning, matching, estimating or reports.

## Forward format and bounds

Nonempty `native_proposals` selects ProjectPackage v7. Each strict reference has
`proposal_id` and required nullable `decision_id`; omitted decision identity never means
latest. Canonical UUIDs, unique proposal identities and deterministic ordering are required.
At most ten proposals can be selected. Empty/absent history preserves the existing v1-v6
selection encoding and package format. Existing Match and evidence selections remain valid.

Each member is `artifacts/native-proposal-{UUID}.json`, using
`CLASSIFIRE-NATIVE-PROPOSAL-HISTORY-v1`. Its fields are schema, historical-only authority,
original proposal and its checksum, selected decision and its checksum (or explicit nulls).
The original native document/decision canonical checksums remain reproducible from their
retained fields. This is not the raw provider wire response or proof of provider identity.
Dynamic review availability, notices and signed save/preview authorizations are excluded.

A member is bounded to 1 MiB plus 32 KiB. The existing 128 MiB archive, 32-member and
2 MiB manifest limits still apply. Oversized selections fail rather than silently dropping
history, originals or reports. Checksums establish exact internal consistency, not authenticity.

Proposal identity, original Draft/project, base revision, prepared graph and evidence selector
bindings are checked. Decisions must bind the same generation, actor and Draft. Confirmed
outcomes reference base revision plus one and a consistent changed-payload claim; rejected
outcomes cannot claim a Scope result. Selected Scope bytes substantiate a decision only when
they are the same revision. Earlier revision bodies remain external, not silently copied or
claimed verified by this package. A proposal/decision newer than selected Scope is refused.

The source inventory identifies the report context's source ID and processed-document hash.
Original files are included only when separately selected through existing source controls;
unselected sources remain external. This does not add a new parser or infer picture ownership.
Other referenced technical/library bodies remain outside the history export.

## Access and foreign history

Local composition reuses current owner, active permission, retained generation integrity,
source access and clean-scan checks. It reads only the explicitly selected decision.
Existing technical/library context permissions and Estimate export restrictions apply.
An unselected later decision is not a dependency of an older package; selected corrupt
history and unsafe or inaccessible retained sources are withheld, never repaired silently.

Import validates selected member inventory, bounds, checksums and cross-bindings. Original
native generations and decisions stay in the retained original archive as foreign,
unverified claims. Import does not create native proposal/decision rows, issue save tokens,
remap historical actors into local approvers or turn source claims into technical approval.
Current imported-project ownership and typed context permissions protect inspection/download.

Nested re-export preserves the exact original archive through the existing origin mechanism.
Imported history is reached through its declared origin member path, not by treating a
foreign proposal ID as a local editable proposal. JSON history inspection does not scan or
unlock binary attachments; original-file downloads/re-export retain their separate scan checks.

## Architecture and migration

**Current architecture:** immutable proposal generations and separate human decisions live
in existing 0048/0049 tables. ProjectPackage already composes selected artifacts and retains
original imported archives. Its existing application services own all access and confirmations.

**Change:** a bounded history contract extends the existing package serializer/inspector and
workspace pages. Generation-only reads are shared with the native proposal reader; decisions
are read independently when selected. Imported history uses the existing archive/origin store.

**Reason:** users need review provenance to travel with explicitly selected project work,
without inventing local approval or silently updating an already saved package.

**Consequences:** selected history carries additional private content and consumes the existing
archive budget. Reopening rechecks current access and source integrity. Foreign history stays
historical; the deterministic core and all technical/commercial/release boundaries remain.

**Migration impact:** no new table or database migration; current head remains0049. V7 is a
forward interchange format that older binaries cannot read. Any later activation/rollback
requires exact-version CI, separate approval, matched database/storage backup, disposable15433
restore and restart checks. Preserve newer packages and reconcile post-backup writes before
any rollback; a code-only downgrade is not presumed safe. Never rehearse on live15432.

## Required evidence and remaining limits

Validate pending/confirmed/rejected selections; old bytes after later decisions; source/access
refusal; rehashed contradictions; explicit package/import confirmations; legacy bytes; exact
original-bearing ZIP; imported read-only history and nested re-export; and no implicit domain
or provider execution. Use selected-checkout PYTHONPATH, fresh basetemp and disposable15433.

Four synthetic PostgreSQL15433 HTTP/service cases passed in261.72s, including the
reproduced unselected-corrupt-decision boundary and exact old/original-bearing ZIPs.
Saved/imported HTML structure assertions passed. Three SQLite cases passed in8.24s,
covering exact legacy multi-review/Estimate/report bytes, rejected history, bounded
selection and denied Estimate-context export without export rights. The initial test-only
response-field error is preserved separately. Full Ruff, Mypy240 and scoped Bandit passed.
The 77-case native-decision/package/import regression passed with two warnings in989.64s.
An additional saved re-export test reproduced a404 for retained nested history; the UI
now reuses the recursive inspector for display/download. All eight final history/package/
import UI cases passed with one warning in278.29s.
Expired scan access was refused without extra writes. The older full run at1aeded3 completed
2,593 passes, two Windows symlink skips and386 warnings in7,243.62 seconds. It does not
cover this feature or later script/claim fixes; targeted evidence remains separate.

Application23f5110 passed actual-main HTTP startup/restart in test mode on owned15433/8837.
The same two recorded histories were separately packaged, imported and re-exported. Two
server processes reopened identical ZIP/JSON, unchanged source Scope3 and imported Scope2.
Blank openings and unknowns remained; replay, CSRF and undeclared-member refusals caused no
extra writes. Provider, scanner and downstream capability counters stayed zero. Both owned
servers stopped. A fresh backup/restore matched71 tables,76 rows, schema and retained bytes;
a fresh process reopened three exact packages and both decisions without changing rows.

The initial read-only PostgreSQL transaction refused existing source-row locks. The completed
follow-up used the normal transaction mode with a SQL-mutation rejection guard (346 reads,
26 source locks, zero mutation attempts) and complete before/after row/schema comparisons.
Those locks preserve quarantine coordination; no guard was removed. Owner/ACL restoration
was excluded. Private failed receipts remain: the HTTP harness initially expected409 for a
missing confirm field (actual422), then for an old-session CSRF (actual403). With current CSRF,
the old import approval correctly returned409. These corrections changed verification only.

Browser initialization remains unavailable, so rendered-browser and live acceptance are
unverified. The main app ran in test mode; this is not production configuration approval.
Synthetic replies/scanner verdicts do not prove real-provider behavior, malware detection,
report accuracy, technical suitability, raw prompt/version lineage or full history coverage.
