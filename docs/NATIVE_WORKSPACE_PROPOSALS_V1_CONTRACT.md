# Native workspace proposal history v1

This local implementation extends the existing native Word/PDF/XLSX additions and
selected Scope replacement actions. It is Draft history, not a technical decision,
a saved Scope change, an external client request or permission to run another capability.

## User interaction

1. Preview selected application/evidence context and explicitly consent to generation.
2. Inspect the generated proposal. Generation still writes no application records.
3. Optionally click **Save proposal for later**. The panel discloses retention of the
   question, included conversation, disclosed context and generated reply before this step.
4. Reopen **Saved AI proposals** in the same Draft's assistant panel. A current proposal
   restores its existing review card; the user separately reviews and confirms Scope.
   A linked confirmation records the reviewed revision; explicit rejection closes the proposal
   without changing Scope. Reopening shows the decision separately from the original generation.
5. Package creation retains its own confirmation. Reopening never repeats generation,
   scanning, Scope confirmation or package creation.

Ordinary advice is not saved by this action. An unsaved proposal remains transient.
A saved proposal is not marked accepted merely because a later Scope revision exists.
A matching manual save without an explicit proposal link leaves its decision unknown.

## Retained contract and checks

`CLASSIFIRE-NATIVE-PROPOSAL-v1` contains a unique identity, actor, Draft, base revision,
generation time, configured model/provider label, parsed request, exact disclosed
context, validated generated fields and prepared review response. The request includes
only the conversation actually included in that request. Original file bytes and image
input bytes are excluded; retained source/image identities bind the context instead.
This is not the raw provider wire response, prompt-version history or full reproducible
model execution. The configured model label is not proof of a resolved provider version.

The server issues a signed, actor/Draft/document-hash-bound save authorization valid
for 15 minutes. Saving requires active current write permission, actual Draft ownership,
CSRF, the exact generated document and unchanged context. The service locks the Draft,
rechecks context, bounds the per-Draft quota and inserts the record plus a redacted audit
entry atomically. Duplicate exact saves return the existing identity without duplication.
A changed document, expired authorization or changed context is refused.

Canonical sorted JSON is limited to 1 MiB per proposal and 100 saved proposals per Draft.
An oversized generation has no save offer; review remains available. Quota exhaustion
refuses further retention. No deletion, automatic expiry or archival policy is implemented.
Saving does not grant read/write authority to the model or change protected domain state.

Reopening checks current active rights and owner, stored hash/bindings, retained source
integrity and current clean-scan requirements through the existing context readers.
Missing rights, foreign ownership, corruption or expired scans withhold the content.
A readable historical proposal whose revision/context or write permission has changed
shows a historical notice with no Scope review controls. Existing confirmation routes
still perform their own fresh guards; a saved proposal never bypasses them.

## Architecture and migration

**Before:** native proposal controls were transient; governed Scope revisions and
human source-review references were already durable. PDF suggestion batches are tied
to PDF pages; external client requests require external identity and distinct authority.

**Change:** one `DraftWorkspaceProposal` record and a bounded native retention service
use the existing database/session, audit, authentication and context readers. The same
assistant panel lists/reopens records and existing format-specific review paths confirm
changes. There is no new database, parser, worker, provider, framework or Scope writer.

**Reason and consequences:** users can leave and reopen a reviewed proposal without
inventing external identity or reshaping a PDF batch. Retention is an explicit additional
Draft write; users control disclosure, retention, Scope confirmation and packaging as
separate actions. Stored context increases private data retention and must remain within
the application's existing storage/access and backup boundaries.

**Migration:** forward migration `0048_draft_workspace_proposals`, after 0047, adds one
table, two foreign keys/indexes and revision/size constraints. Historical migrations
remain unchanged. Downgrade deliberately refuses to discard retained history. Any later
activation needs exact-version CI, explicit approval, a matched database/storage backup,
disposable PostgreSQL15433 restore verification, schema rehearsal, restart and rollback checks.
Do not test migrations on live PostgreSQL15432. An older build may reject a newer migration head;
code-only rollback is not assumed. Restoring a pre-upgrade database must account for all
writes since backup and preserve the newer backup/history before any destructive action.
No live migration or activation is authorized by implementing this feature.

## Explicit human decision linkage

The local decision extension uses an optional saved-proposal identity in the existing
Word, PDF, workbook and manual Scope review forms. Identity is bound into source-review
preview signatures; removal or substitution invalidates a signed preview. Each rendered
proposal card has its own identity. An in-flight retention request blocks that card's
review submission until its saved identity is known. Unsaved proposals still use the
existing manual path and are not silently retained.

Before a linked review or save, the existing retention service rechecks the owner,
active write permission, exact proposal, action/source, current context and base revision.
It locks the Draft and proposal in a consistent order. The same transaction that invokes
the existing Scope writer records one `DraftWorkspaceProposalDecision`; failure to record
the decision rolls back the Scope save. No decision service dispatches a Scope writer,
provider, scanner, Match, Estimate, report, package or canonical admission command.

The decision is a separate `CLASSIFIRE-NATIVE-PROPOSAL-DECISION-v1` record with actor,
time, original proposal hash, base revision, outcome and, for confirmation, a foreign key
to the exact saved Scope revision and hash of its retained envelope bytes. It records the
submitted graph payload hash and whether those graph fields differ from the prepared
proposal. This comparison does not claim that source-review selections were unchanged;
the final Scope retains the actual reviewed references. Reviewers can correct the graph.
A confirmed reviewed result never rewrites the original generation or proves that every
AI suggestion was accepted unchanged. These are Draft decisions, not technical approval.

Rejection requires its own checkbox and confirmation. It records no Scope revision.
There can be only one decision per proposal; a decided proposal cannot later be confirmed
or rejected again. An older signed preview cannot bypass that rule. Matching content,
matching entity IDs, a later revision, retention or conversational agreement cannot infer
a decision. Historical proposals can be explicitly rejected while still readable under
the current source/access checks. No expiry or background decision is introduced.

Reopening verifies decision hash, actor/proposal/Draft bindings and the linked revision's
integrity, and disables further review controls. Confirmed revisions remain downloadable
through existing permission checks. Corrupt decisions withhold the saved proposal view;
missing decisions remain explicitly unknown.

**Current architecture -> change:** migration0048 stores immutable generations;
forward migration `0049_draft_proposal_decisions` adds a separate bounded decision table,
three foreign keys, one-decision uniqueness and outcome/size constraints. Existing
writers, audit, session and review routes are reused. No existing migration is rewritten.

**Reason -> consequences:** users can see the actual recorded disposition and reviewed
result without inferring approval from similar content. The additional history contains
identities and hashes rather than another copy of private report/model content.

**Migration impact:** readiness now requires0049 and its decision table;0048/0047 remain
recognized migration-required histories. Downgrade refuses to discard decisions. The
previous0048 backup rehearsal alone does not establish0049 recovery. The separate local
b3c2203 rehearsal now verifies actual0048/0049 database and retained-file restores,
explicit confirmed/rejected decisions, exact generation/Scope/ZIP bytes and fresh-process
application reads on disposable15433. It excludes production owner/ACL restoration,
browser/server restart, live backup and operational acceptance. Any activation still needs
an exact approved plan, successful applicable CI, matched backup/disposable restore,
restart and rollback verification. Restoring a pre0049 backup would lose subsequent
Scope changes and decisions unless separately preserved/reconciled; code-only rollback
is not assumed. Never infer permission for live15432 from these synthetic tests.

## Verified boundary and remaining work

The private validation receipt records actual test/browser results and hashes; do not
substitute this contract for successful CI or an operational acceptance receipt.
The preceding 0048 synthetic browser journey saved/reopened exact proposal content, separately confirmed
Scope and package, downloaded the exact original-bearing ZIP, then restarted and reopened
history without repeating work. This does not verify the new 0049 decision controls. Synthetic replies/scanner verdicts do not prove real
provider behavior, malware detection, report accuracy or technical suitability.

Remaining: browser/restart and operational acceptance of the new decision controls;
portable proposal/review history in ProjectPackage; richer non-Scope actions; retention
policy and broader operational/tenant/recovery validation. No full C1/C2/C3, Phase 8-16,
AI audit-lineage or production-readiness completion is claimed.
