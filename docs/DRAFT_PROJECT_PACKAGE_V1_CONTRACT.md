# Draft ProjectPackage v1

Status: implemented current P5 increment; see PROJECT_STATE.md and live Git/PR/CI
for verification/publication. This is a selected Draft workspace package, not a
whole database backup or full project extraction. v1 export remains byte-compatible;
new-project import and imported-project v2 re-export are described below.

## Current architecture -> change -> consequences

Existing Scope, System Match, Estimate and report services already retain exact
versioned artifacts. The shared `draft_project_packages` service composes their
authorized reads. The FastAPI/Jinja UI configures, previews, explicitly saves and
downloads a package without invoking matching, calculations or report generation.
No provider, agent, dependency or canonical write authority is added.

Migration 0034 adds `draft_project_packages` in the existing database. Each record
holds its Scope workspace, package revision/parent hash, exact manifest, original
ZIP bytes and hashes, creator and timestamp. Unique workspace/revision plus an
expected revision prevent conflicting saves. The existing SQLite-safe transaction
helper preserves caller rollback; callers own commit. Older migrations are unchanged.
Migration 0035 now adds imported origins; deployment readiness requires that head.
0033/0034 remain recognized upgrade lineages.

## Selection and lifecycle

A package selects one saved Scope revision, optionally one exact review and one
Estimate revision, and up to four Scope/system plus four Estimate/complete reports.
An Estimate's embedded Scope/review must equal those selected; a report must contain
the same selected dependency revision. Scope-only packaging needs no matching or
estimating. Choosing an Estimate can prefill its required review through a preview
link. Users can change membership and explicitly save a new package revision.

Preview reads without database writes or download audit events. Its content hash
binds project labels, selection, membership and member hashes. Save recomposes and
checks the preview hash, expected package revision, source bytes and permissions;
it records one create audit. Reads validate retained archive/row/source bindings,
parent linkage and current access. Download records one exact-archive audit and
returns original bytes. Reconfiguration never rewrites old packages. Scope, review,
Estimate, project or source changes are shown as current staleness separately from
the frozen download. Historical data can remain exportable with a visible warning.

## Portable content and authority

`CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v1` uses Draft/historical_only authority. Manifest
includes selected project labels, workspace identity, selection, capability status,
source membership, package revision/parent hash, creator/time and member inventory.
Members contain original versioned Scope/review/Estimate JSON and selected report
snapshots plus exact PDF/XLSX. Their existing provenance, uncertainties, review and
override history remain intact. Parent hashes/reference claims do not imply every
historical revision or source body is included.

Project evidence references are external; technical/pricing source bodies are
withheld. Manifest pointers locate the exact retained provenance within artifact
JSON. No source-body export permission is inferred from a hash. Unselected
capabilities, outputs and earlier revisions are omitted explicitly by policy; no
claim of complete database or evidence membership is made. Missing source references
remain visibly unrecorded. Restricted library bodies, credentials and storage paths
are not extra archive members. Manually entered artifact text remains user content,
not a general-purpose secret-redaction guarantee.

Reuse active-human project ownership/read/write. Technical read is required for a
review, Estimate read/export for commercial content, and library read for retained
workbook selections. Existing report integrity checks apply to every selected pair.
Revoked access denies saved package reads/downloads; inaccessible packages are not
listed. Scope-only packages retain the existing Scope read/download boundary.
CSRF, bounded forms and duplicate/unknown selection-field refusal remain enforced.
No imported claim, approval, signature or lock can gain local authority through this
export. A separate `/package-import` upload inspection screen now exists, but it
does not save an imported project or make uploaded report binaries downloadable.

## Archive and verification

Sorted JSON and ZIP members, fixed ZIP timestamps/attributes and stored compression
make a given saved manifest reproducible. Native v1 bounds: 64 MiB archive, 2 MiB manifest,
28 members. File paths are generated, never taken from original filenames. Member
size/SHA-256 and exact ZIP re-encoding are checked without filesystem extraction;
unsafe, duplicate, extra, compressed, altered and oversized archive members fail.
The structural inspector is not a semantic importer or authorization verifier;
service reads additionally reconstruct exact content through authorized readers.
The new `draft_package_import.inspect_package` additionally validates the complete
manifest/selection/source inventory and every JSON artifact/report dependency. Its
authorized preview is read-only; foreign approval remains unverified. Binary header
and hash checks do not establish malware safety or agreement with the snapshot.
Input uses configured upload limits plus its v1/v2 archive limit. Safe retention,
local identity mapping and transactional import are implemented below; structural ZIP
checks alone still confer no import or download authority.

Tests cover no-write preview, coherent dependencies, unchanged history, rollback,
conflicting saves, permission loss, source policy, malformed archives and forward
migration. A synthetic Chrome journey saves Scope-only/combined/reconfigured
packages and verifies exact ZIP downloads after actual restart. The combined ZIP
retains the original PDF/XLSX bytes; this increment does not rerender those outputs.

## Imported project lifecycle and v2 re-export

Implemented in `draft_package_import`, `draft_package_materialization`,
`draft_import_origin` and `draft_import_reports`. These shared use cases serve the UI;
no provider, canonical physical model, eligible technical release or release lock is
created. Preview is read-only. A 15-minute signed confirmation binds exact ZIP hash,
active user and current session/nonce; it is consumed in that browser session after
success. The user supplies a new project reference/name and explicitly confirms.
This is not a distributed exactly-once request journal.

One transaction creates a new owned Project/Draft Scope, imports Scope as local
revision 2 through its existing lineage contract, and creates local Match/Estimate
revision 1 where present. Each gets a new top-level identity. Scope entity IDs and
Estimate line IDs remain scoped inside that new workspace. Original line values,
summary, decisions, source references and historical authors/times are retained;
import does not silently recalculate. Later explicit edits append local history.

Migration 0035 adds immutable `draft_package_imports` (original archive and hashed
identity mapping) and Draft-owned `draft_imported_report_sources`. Match has either
a native LibraryRelease or an imported origin, enforced by a database constraint;
it never fabricates a local release. Estimate origin is separately bound. Existing
native rows, revisions, FKs and package bytes are preserved. Initial local revision
hashes bind the retained mapping. Destructive downgrade is refused.

Imported Match uses `CLASSIFIRE-DRAFT-SYSTEM-MATCH-v4`; imported Estimate uses
`CLASSIFIRE-DRAFT-ESTIMATE-v3`. Both declare `content_schema_version`,
`provenance: package_import` and `CLASSIFIRE-IMPORTED-ORIGIN-v1`: import ID, original
archive hash, source schema/artifact/revision, semantic hash, exact file hash and
`authority: foreign_unverified`. Native content validators still apply. Native
formats remain unchanged. Original candidate/source/constraint facts and original
Estimate history prefixes cannot be overwritten. Users may edit review preferences
and Estimate values; fresh technical measurement review requires separately chosen
current local sources. UI and newly generated reports identify foreign authority.

Report snapshots and PDF/XLSX remain exact original members inside the original ZIP.
They do not become fake native report rows. Each binary also receives its own local
source binding via existing shared retention/scan/quarantine controls. Original
bytes may be supplied again for a new owned binding; the caller cannot adopt another
owner's record by hash or reset shared quarantine. Bindings enforce exact file hash
and size. Report-bearing import requires PostgreSQL. Scope/review/Estimate-only
import also works on SQLite.

A scan must be current and clean, followed by a bounded separate-process format
check before report or original-ZIP download/re-export. Missing scanner, malware,
expired scan, processing failure, changed bytes and lost rights fail closed. Checks
are repeated for saved package downloads, including all ancestors. PDF checks reject
active actions/forms/attachments and bound pages/objects. XLSX rejects formulas,
external relationships and active content; static PNG logos are permitted only by
the report worker's bounded image policy. Existing evidence/pricing XLSX intake
keeps its strict image rejection. Scanning/format checks do not prove report claims
or numerical agreement with source snapshots. Production OS sandboxing remains an
operational assurance task; process separation alone is not that proof.

`CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v2` retains the selected current local artifacts and
one exact original ZIP at `origins/<sha256>.zip`, with original-to-local mapping.
That original can itself contain an origin. Semantic inspection recursively validates
all included packages and mappings; every original report/history byte remains
available without flattening or silently dropping it. v1 remains 64 MiB/28 members;
v2 is bounded to 128 MiB/32 members, 8 archive levels and a cumulative 256 MiB
inspection budget. Import refuses a depth that could not be re-exported within the
level bound. Configured upload limits and individual attachment limits still apply.
Re-export must fit its archive limits; unlimited history/size is not promised.

All included descendant capabilities govern permissions. Estimate writes require
Estimate write rights; Estimate exports require export rights; restricted pricing
references require library read rights. New reports render selected local revisions
without matching or estimating again. A source hash, imported author or foreign
approval cannot grant local library, project or human-release authority.

## Remaining work

Selected-workspace portability is distinct from whole-project completeness. Source
bodies remain external/withheld; multiple workspaces, complete revision histories,
redistribution policy, quota/retention operations and existing-project conflict
resolution remain planned. Thin ChatGPT access should reuse these proven commands,
with explicit authenticated ownership and a bounded end-to-end demonstration.
OpenClaw retirement and production acceptance require their own verified exits.


## Candidate v3: explicit project PDF membership

Locally implemented and regression-tested; publication and browser acceptance remain. `Selection.pdf_sources`
contains up to four unique sorted source UUIDs, each referenced by the selected saved Scope
as local retained PDF evidence. Empty selection omits the new field when serializing, so
legacy selection/manifests remain unchanged. Selected PDF bytes occupy generated
`evidence/<source-id>.pdf` paths. Source inventory entries say included and name that path;
unselected project evidence stays external and technical/pricing bodies stay withheld.

V3 has an explicit origins list (empty or one retained origin), the existing 128 MiB and
32-member bounds, exact ZIP encoding and unchanged recursion/cumulative inspection limits.
Export rereads owned, clean retained bytes and compares source/hash/size/document binding to
Scope references. Import verifies member/Scope/hash consistency but does not trust claims.
It retains evidence PDFs with the shared imported-attachment service; mapping v2 includes
original/local attachment identities, paths and hashes. Legacy mapping v1 remains unchanged.
All evidence binaries, including nested ancestors, require current clean scan/format checks
before original ZIP download or re-export. PostgreSQL is required for binary retention.
There is no automatic conversion of imported page references into local human approval.


## V4 amendment: explicit Scope workbook membership

The shared package service now accepts optional `Selection.xlsx_sources`: at most
four unique sorted source UUIDs, disjoint from selected PDFs. Each must have a
local-retained XLSX evidence reference in the selected saved Scope. The UI exposes
an unchecked workbook choice; MCP discovers the same exact Selection schema.
Empty workbook selection is omitted on serialization, preserving v1-v3 selections
and exact historical package reconstruction. New workbook-bearing exports use
`CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v4`; older readers must upgrade to open these.

Each selected original workbook occupies `evidence/<source-id>.xlsx`; original
filenames never become paths. Source inventory binds every included reference to
its member. Export rereads owned/current-clean source bytes and compares their
hash, size and parsed-document hash to saved evidence. Preview/save/download keep
existing revision, exact-input and permission checks. The archive retains existing
128 MiB/32-member and origin-depth/cumulative limits; combined selections can be
rejected when those limits are exceeded. Restricted pricing and technical-library
source bodies remain withheld.

Semantic import checks workbook membership, magic, source hash/size and Scope
reference type. This is consistency checking, not proof of file safety or truth.
Import retains a new owned attachment through the existing shared intake service,
using the native Scope workbook purpose and parser. Original pictures and formula
text are preserved; formulas are never evaluated. The stricter generated-report
XLSX parser is unchanged. Current malware scan and bounded workbook parsing are
required before imported workbook/origin download or re-export. Nested ancestors
remain checked; quarantine propagates across shared exact-byte bindings.

Original/local attachment identities reuse import mapping v2. Imported Scope
references remain foreign/unverified; parsing does not create local evidence review,
technical approval, pricing, locks or release. No database migration, dependency or
parallel storage pipeline is introduced. Standalone and ChatGPT use shared services.

Synthetic validation covers optional UI selection/save/download, original-byte
identity, unknown quantities, changed source/member refusal, legacy-format refusal,
import/scan/re-export/two-generation history, foreign ownership and shared quarantine.
Playwright exercised selection through ZIP download with ASGI test transport; this
is browser proof, not hosted deployment or real ChatGPT acceptance.
