# Draft ProjectPackage v1

Status: implemented current P5 increment; see PROJECT_STATE.md and live Git/PR/CI
for verification/publication. This is a selected Draft workspace package, not a
whole database backup, full project extraction or safe import implementation.

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
Deployment readiness recognizes 0033 as requiring migration, not a current database.

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
make a given saved manifest reproducible. Bounds: 64 MiB archive, 2 MiB manifest,
28 members. File paths are generated, never taken from original filenames. Member
size/SHA-256 and exact ZIP re-encoding are checked without filesystem extraction;
unsafe, duplicate, extra, compressed, altered and oversized archive members fail.
The structural inspector is not a semantic importer or authorization verifier;
service reads additionally reconstruct exact content through authorized readers.
The new `draft_package_import.inspect_package` additionally validates the complete
manifest/selection/source inventory and every JSON artifact/report dependency. Its
authorized preview is read-only; foreign approval remains unverified. Binary header
and hash checks do not establish malware safety or agreement with the snapshot.
Input is bounded by the lesser of 64 MiB and configured upload size. Safe retention,
local identity mapping and transactional import remain unimplemented.

Tests cover no-write preview, coherent dependencies, unchanged history, rollback,
conflicting saves, permission loss, source policy, malformed archives and forward
migration. A synthetic Chrome journey saves Scope-only/combined/reconfigured
packages and verifies exact ZIP downloads after actual restart. The combined ZIP
retains the original PDF/XLSX bytes; this increment does not rerender those outputs.

## Remaining work

Next: safe new-project package import and local provenance/identity mapping across
all retained capability artifacts, with explicit unresolved external sources and no
foreign authority. Then share proven use cases through ChatGPT. Broader source-body
membership/redistribution, multiple workspace/artifact collections, full history,
retention/quotas and full project coverage remain planned. These limits do not
complete production readiness or authorize OpenClaw retirement.
