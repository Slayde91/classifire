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
5. Package creation retains its own confirmation. Reopening never repeats generation,
   scanning, Scope confirmation or package creation.

Ordinary advice is not saved by this action. An unsaved proposal remains transient.
A saved proposal is not marked accepted merely because a later Scope revision exists.

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

## Verified boundary and remaining work

The private validation receipt records actual test/browser results and hashes; do not
substitute this contract for successful CI or an operational acceptance receipt.
The synthetic browser journey saves/reopens exact proposal content, separately confirms
Scope and package, downloads the exact original-bearing ZIP, then restarts and reopens
history without repeating work. Synthetic replies/scanner verdicts do not prove real
provider behavior, malware detection, report accuracy or technical suitability.

Remaining: link retained generation to explicit later review decisions and revisions;
portable proposal/review history in ProjectPackage; richer non-Scope actions; retention
policy and broader operational/tenant/recovery validation. No full C1/C2/C3, Phase 8-16,
AI audit-lineage or production-readiness completion is claimed.
