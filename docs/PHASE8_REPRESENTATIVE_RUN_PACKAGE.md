# Phase 8 representative run package

This procedure executes the existing linked-original, proposal-only visual
runner once against an explicitly approved retained report. It is a
canonical-no-write validation operation only: it cannot create an admission,
submit a canonical physical model, or create a Physical Model Lock. The run
does create disposable retrieval/retention files, SQLite snapshot changes that
are rolled back, and output receipts; database rollback does not delete those
filesystem artifacts.

Do not create or run a package without a recorded approval for the retained
report and its retrieval location. Approval of this guide, a previous report
review, or access to the storage location is not approval to use the report.

This is trusted operator-controlled UAT tooling, not an untrusted production
ingestion boundary. The approval fields preserve the recorded governance
decision but are not a cryptographic, expiring, or single-use authorization.

## Required package contents

Place `package.json` beside the following files and directories. All paths in
`package.json` are relative to the package directory. Absolute paths and parent
traversal are rejected.

- the approved report PDF;
- `photo-rows.json`, containing the report's reviewed photo rows;
- `parent-evidence.json`, mapping every photo ID to its immutable parent
evidence ID in the database copy;
- a SQLite database copy, not the live database;
- a storage-root snapshot containing the parent stored files referenced by that
database copy;
- an empty or disposable retrieval-root directory;
- a post-inference human-reference JSON file; and
- the command and model settings for the two dedicated zero-tool runtime
identities.

The package loader verifies the report hash, checked-out revision,
deterministic source-tree hash, approval scope, dedicated runtime identities,
paths, JSON shape, duplicate JSON keys, and the configured linked-original
host allowlist. The source-tree fingerprint fails closed if a symbolic link or
Windows junction is present anywhere in the executable source set. The executor
then confirms that
each parent evidence record belongs to the named estimate and that its stored
file resolves inside the packaged storage snapshot. The inference packet is
then allowlisted to current retentions and explicitly mapped ready parents for
the selected Defect; other pre-existing visual rows are excluded.

## `package.json` contract

The top-level object has exactly these six entries:

```json
{
  "schema": "CLASSIFIRE-PHASE8-REPRESENTATIVE-RUN-PACKAGE-v1",
  "package_id": "approved-run-identifier",
  "approval": {},
  "execution": {},
  "inputs": {},
  "runtime": {}
}
```

`approval` records a non-empty approval reference, approver, UTC timestamp,
`rollback_only_linked_visual_proposal` scope, uppercase SHA-256 of the report,
and precisely the current configured linked-original allowlist.

`execution` pins the full 40-character checked-out Git revision and a SHA-256
fingerprint of the executable source set (`src/classifire`, this package runner,
and `pyproject.toml`). Git pins Python, JSON, and TOML files to LF line endings
so the raw-byte fingerprint is reproducible across clean checkouts. This binds
an uncommitted candidate worktree as well as its base Git revision. It also
records the estimate ID, defect reference, and
operator reference. Its four booleans must be:

```json
{
  "rollback_only": true,
  "canonical_submission_allowed": false,
  "physical_model_lock_allowed": false,
  "human_reference_visible_to_inference": false
}
```

`inputs` names the report, photo rows, parent-evidence mapping, database copy,
storage root, retrieval root, and human-reference file. `runtime` names an
existing absolute gateway command and the fixed
`cf-phase8-visual-physical` and `cf-phase8-visual-validator` identities, plus
the approved literal-loopback URL and provider/model settings. The gateway
command must already exist and is trusted operator-supplied executable input;
the package loader validates its location but does not prove the executable's
provenance. Because the command process inherits the local execution
environment, human approval must cover the exact executable paths as well as
the runtime identities and models.

## Execution

First run the preflight from the exact checked-out source revision and
source-tree fingerprint named in the approved package. It validates package and
snapshot bindings, confirms only that the local process can see a gateway token,
and calls the local Gateway's read-only `sessions.describe` method against a
fixed probe key. The probe creates no session and starts no runtime. It performs
no retrieval, no model request, and no external inference egress.

```powershell
$env:PYTHONPATH = "$PWD\src"
C:\CLASSIFIRE\.venv\Scripts\python.exe `
  scripts\run_phase8_representative_package.py `
  --package C:\approved-package\package.json `
  --output C:\approved-preflight-output `
  --repository-root $PWD `
  --verify-only
```

Review both `preflight-receipt.json` and `runtime-readiness-receipt.json`. The
second receipt covers only the no-write local Gateway probe; `--verify-only`
does not construct or probe the malware scanner because it performs no linked
retrieval or inference.

Before the real run, configure the governed private ClamAV endpoint described
in [Production configuration](PRODUCTION_CONFIGURATION.md). The real run
requires the daemon to advertise and complete `INSTREAM`; it passes that exact
scanner into report, image, cache and retained-evidence processing. Use a fresh
output directory. If Gateway or scanner readiness cannot be confirmed, the
command writes a content-safe `failure-receipt.json` and stops before
linked-original retrieval:

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:CLASSIFIRE_CLAMAV_HOST = "clamav.internal.example"
$env:CLASSIFIRE_CLAMAV_PORT = "3310"
$env:CLASSIFIRE_CLAMAV_TIMEOUT_SECONDS = "10"
C:\CLASSIFIRE\.venv\Scripts\python.exe `
  scripts\run_phase8_representative_package.py `
  --package C:\approved-package\package.json `
  --output C:\approved-output `
  --repository-root $PWD
```

The command opens only the packaged SQLite copy. It begins an explicit outer
SQLite transaction before the existing runner can retain evidence, rolls that
transaction back even when inference fails, expires ORM state, and compares the
protected canonical-state fingerprint and counts before and after rollback.
It fails if those values differ.

The human reference is never provided to the inference runtime. Only an approved
visual result is compared after the runtime closes. A blocked result records the
comparison as skipped and produces no comparison receipt. The output directory
contains only the hashed artifacts actually produced for that outcome. A zero
exit status requires both an approved visual result and a passing post-inference
human-reference comparison.

When managed inference produces successful stages, the output also includes
`openresponses-transport-receipts.json`. This governed local sidecar retains
the exact content-safe preimage behind each stage's opaque transport hash. The
writer verifies those preimages against the controller receipt before writing
them. The `CLASSIFIRE-PHASE8-REPRESENTATIVE-RUN-v2` receipt commits the
canonical bundle hash, and `completion-receipt.json` records the exact sidecar
file hash as `artifacts.openresponses_transport_receipts_sha256`. A required
sidecar write failure prevents the completion receipt, although earlier output
files may remain as an incomplete run. Historical v1 runs remain historical
evidence; they are not backfilled or described as transport-reconstructible.

The writer does not set or prove a filesystem access-control list. The output
directory must be access-restricted, and this sidecar must be excluded from
publication and human-review handoffs because its hashes and internal UUIDs are
stable correlators even though it contains no source bytes.

When a valid Validator explicitly returns `BLOCKED`, the runner also writes an
`evidence-review-request.json` artifact when it can safely retain structured
issues or limitations. It links to the controller/proposal hashes, includes any
Validator-declared unresolved blind observations with their retained evidence
references, asks a human to resolve each item against retained or newly governed
evidence, and expressly does not authorize submission, locking, or pricing.
Signed URLs and similar capability text are excluded from this review artifact.
Newly written JSON artifact hashes are calculated from the exact UTF-8/LF bytes
written to disk, including on Windows.

## Offline recovery of a blocked review request

A prior blocked run may predate the review-request output. Do not rerun the
report merely to recreate that artifact. If the approved package, completion,
representative-run, controller and proposal receipts remain available, and all
of the controller-bound local OpenClaw sessions remain available, use the
offline recovery command:

```powershell
$env:PYTHONPATH = "$PWD\src"
C:\CLASSIFIRE\.venv\Scripts\python.exe `
  scripts\recover_phase8_evidence_review_request.py `
  --package C:\approved-package\package.json `
  --completion C:\blocked-run\completion-receipt.json `
  --representative-receipt C:\blocked-run\representative-run-receipt.json `
  --controller C:\blocked-run\proposal-controller-receipt.json `
  --proposal C:\blocked-run\proposal.json `
  --transport-receipts C:\blocked-run\openresponses-transport-receipts.json `
  --openclaw-root C:\Users\operator\.openclaw `
  --output C:\blocked-run-review-handoff `
  --repository-root $PWD
```

Recovery is fully local and does not open the retained source report or any
linked-original file. It does read the bound local session transcripts, which
can contain prior prompt content. It reconstructs the deterministic session key
for every successful stage, requires the exact
session-index entry and transcript, canonical-hashes the sole assistant JSON
payload, validates the final blind inventory, proposal and Validator response,
and writes exactly `evidence-review-request.json` and `recovery-receipt.json`
to a new output directory. The recovery receipt records historical
`LF_RENDERED_JSON_SHA256` binding explicitly where older Windows outputs used
that convention.

`--transport-receipts` is required for a v2 representative receipt. Recovery
verifies its canonical bundle hash, the exact sidecar file bytes and every
retained preimage against the controller stages, then records only verification
status, count and hashes in the recovery receipt. For a historical v1 receipt,
omit this argument; recovery marks the missing capability as
`LEGACY_TRANSPORT_BINDING_UNAVAILABLE` and rejects an unadvertised sidecar.

This proves correspondence among the retained package, receipts, local sessions
and payload hashes. It does not replay Gateway authentication, tool attestation,
tool audit, OpenResponses response identity or external transport, and it does
not replay the malware scanner or prove the referenced clean/latest attestation
chain. It does not claim that mutable local OpenClaw history is immutable. It
performs no retrieval, inference, canonical submission, lock, pricing or
human-reference comparison.

The retained v17 execution used this controlled workflow and ended with
`VISUAL_PROPOSAL_BLOCKED`. It proved the rollback and authority boundaries but
did not approve a physical model. A later offline recovery produced the
content-safe review handoff without reopening the retained report or linked-
original files and without rerunning inference. The bound local session
transcripts were read. See `PROJECT_STATE.md` for the current verified evidence and source
fingerprints.
