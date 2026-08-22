# CLASSIFIRE Project State

**Verified snapshot:** 2026-08-22 (AEST)
**Working branch:** `gpt/phase8-gateb-legacy-table-retirement`
**Merged base:** `dec65fef` (`origin/main`, merged Gate A test PR #36)
**Current scope:** Gate B schema-drift repair and deployment-readiness verification.

This document records repository evidence. The initial local signer work did
not use operational authority. Later user authority covered the approved logo
treatment, source publication, and an Android smoke-test attempt; the execution
environment independently retained its safeguards for persistent APK signing
material and device deployment.

## Current repository reconciliation - 2026-08-22

### Current Gate A and Gate B position

Shared main is `dec65fef633b4844304974a966baab8498a99acc`. The
admission-only plugin was rebuilt from that exact clean tree and verified with
artifact SHA-256
`38812E99DC138A198EE58BF6E00E9B34E081502CB43C39089418BC53E3C2AEE4`.
The read-only Gate A auditor returned `LOCAL_CANDIDATE_REVIEW_REQUIRED` with no
missing paths, `deployment_authorised=false`, and
`live_change_performed=false`. The exact-main candidate fingerprint is
`2CEA7EDECEC705CC5182141DE98F8B0D47794CE81D45C7B947ECAF09CDC13557`.

Read-only inspection of the configured local database found integrity `ok`, no
foreign-key violations, zero admission and submission-receipt records, and
Alembic revision `0007_reconcile_adjudicated_admission_lineages`. It also found
an empty stray `physical_model_initial_submissions` table that the reviewed
`0007` migration and fresh-install tests require to be absent. Gate B is
therefore not complete.

A narrow local `0008_retire_legacy_initial_submissions` migration now removes
that table only when it is empty and fails closed if any record exists. Twenty
focused migration, lineage, preflight, and Gate A tests pass, and Ruff passes.
A byte-identical disposable copy of the current database upgraded to `0008`:
the legacy table was removed, integrity and foreign-key checks passed, both
current journal tables remained empty, all protected row counts and hashes
were unchanged, and the source database SHA-256 remained
`D66E336F1C6245528D199EA22571037934342CCA0EBDF2E6314A570766540A16`.

The next valid action is review and publication of the `0008` repair, followed
by a verified recoverable backup and the same migration against the configured
database. Gate C public-key configuration and runtime deployment remain later
gates. The APK release-signing certificate is not an admission verification
key and must not be used for Gate C.

The older sections below preserve chronological signer and reconciliation
evidence. Where they describe an earlier branch, main revision, Gate A blocker,
or next action, this current section supersedes them.

### Superseded earlier reconciliation snapshot

The current shared main revision is
`3f42b1631fcc0881ac5f9049b1023b29309e270f`, which includes the merged
handoff reconciliation PR #33. After the Phase 8 baseline `e2f646b`, shared
main adds the offline Android admission signer, its tests, approved icon
resources, and handoff/custody documentation. The signer is merged and
locally regression-checked; it is not an admission, registration, canonical
submission, or Physical Model Lock operation.

The deployment runbook currently names a Gate A candidate-audit script and a
v6 post-merge preflight receipt, but neither is present on shared main. Both
remain untracked items in the separate, heavily dirty primary checkout. They
must not be treated as published deployment evidence, staged from that
checkout, or used for a live deployment.

That untracked writer material was reviewed in a native isolated worktree. It
uses a divergent `canonical_models` architecture and has 346 committed files
of divergence from shared main. It must not be merged wholesale. Shared main
already contains the newer admission-writer lineage (`12c2e5c`, `e19bc45`,
and `7e8141f`) with the reconciled migration head
`0007_reconcile_adjudicated_admission_lineages`.

On an isolated worktree whose content matches shared main, 55 focused
admission, migration, boundary, and plugin-profile tests passed. The offline
signer verification previously produced 9 focused Python contract/security
tests and 6 Android unit tests with zero failures or errors. No device was
connected, no Android admission key was created, no APK was signed, and no
admission, canonical, or lock action occurred in these checks.

A current-main Gate A source auditor now fingerprints the writer, migration
lineage, preflight policy, governance tests, plugin source, and compiled
plugin artifact without reading configuration, opening a database, contacting
a runtime, or performing a live action. Its direct run against this unreviewed
worktree correctly returned `LOCAL_CANDIDATE_DIRTY_REVIEW_REQUIRED`, with both
`deployment_authorised=false` and `live_change_performed=false`.

The next valid operational task remains a clean, reviewed shared-main
deployment candidate with a plugin artifact rebuilt in an approved deployment
environment. A zero audit exit does not authorise deployment, admission
registration, canonical submission, or a Physical Model Lock. Do not revive
or publish the divergent dirty writer worktree.
## Repository position

Merged main `e2f646b` includes the reconciled Phase 8 admission-only writer from
PR #25 and the Android P-256 provisioning proof from PR #24. The signer work in
this snapshot is uncommitted and exists only on
`gpt/phase8-android-admission-signing-local`.

The primary checkout at `C:\CLASSIFIRE` remains on
`gpt/phase8-linked-original-images` with extensive pre-existing tracked and
untracked work. It was not switched, reset, cleaned, staged, or otherwise
altered for signer implementation. Work was isolated at:

`C:\CLASSIFIRE\.tmp\phase8-android-admission-signer-20260822-v2`

Preserve all unrelated dirty work, especially `agent-definitions/` and
`classifire logo.png`. Never use `git add .` in the mixed checkout.

## Phase 8 evidence

The current retained post-merge no-write receipt is:

`data/real-uat/20260822-phase8-postmerge-preflight-147042-v6/24-adjudicated-canonicalisation-preflight.json`

Verified values from that receipt are:

| Item | Value |
| --- | --- |
| Schema | `CLASSIFIRE-ADJUDICATED-CANONICALISATION-PREFLIGHT-v3` |
| Status | `PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED` |
| Submission eligible | `false` |
| Canonical/database/Gateway writes | all `false` |
| Lock eligible | `false` |
| Normalised topology | 17 Openings, 24 Services, 24 links |
| Payload SHA-256 | `85B3D16F92E32AA6BF05B5CD8C0192F9719C2FB45D081C26D1159733E65B8FB3` |
| Protected-state fingerprint | `18768A9E368C7D0692A950303FCAC9401AFBE7C3632BE6A063FCB67B9671F8F1` |
| Fingerprint version | `CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1` |
| Receipt SHA-256 | `1BF735B2D441B214967672072323C37B587C4E8659EF8F8BDC9D0D3A120D43F2` |
| Generated | `2026-08-22T05:24:50Z` |

The v6 receipt is evidence of a successful no-write preflight only. It is not a
signed admission or authority for a later operation. No new admission package
was created in this signer session. The previously retained v3 signed package
is expired and must not be reused.

The 17/24 proposal remains provisional and non-canonical. It retains unresolved
material, size, quantity, FRL, and other evidence limitations. No replacement
active Physical Model Lock exists, so Phases 9 onward remain blocked.

## Offline Android signer

The local Android app now implements the missing admission-signing workflow:

- local-only document-picker import and export with no Internet permission;
- exact v2 manifest field, UUID, identifier, SHA-256, signature-placeholder,
  timestamp, expiry, and maximum 15-minute lifetime validation, with the same
  decoder-backed base64url rule enforced before signature export;
- backend-compatible sorted, compact UTF-8 canonical JSON with the signature
  field omitted from the signed bytes;
- explicit display of project, estimate, run, preflight, payload, protected
  state, artifact, policy, issuer, key, fingerprint, and expiry bindings;
- issuer/Key ID lookup against a matching secure-hardware-backed Android
  Keystore key and stored public-key fingerprint;
- Android 12+ acceptance only for Trusted Environment or StrongBox keys, with a
  narrowly scoped Android 11 fail-closed compatibility check;
- strong-biometric approval for `SHA256withECDSA`;
- strict P-256 low-S DER normalisation and local public-key verification before
  export; and
- explicit separation of the default signing screen from the separately
  authorised key-provisioning/proof screen; and
- screenshot and recent-app preview protection on both signer screens.
- resource-backed UI text for deterministic lint-clean localisation handling; and
- fail-closed lifecycle handling that clears stale reviews, serialises biometric
  attempts, ignores callbacks for replaced manifests, and permits retry only while
  the current manifest remains unexpired.

Application backup, device transfer, and cleartext traffic are disabled. The
app has only the biometric permission in the merged debug manifest. It contains
no registration, canonical-submission, lock, or network client.

The packaged local debug APK was also inspected directly. Its effective manifest has
exactly `USE_BIOMETRIC`, no Internet permission, backup and cleartext traffic disabled,
only `OfflineSignerActivity` exported as the launcher, and `MainActivity` non-exported.
It is explicitly a debug artifact (`debuggable=true`) and must not be treated as a
release or deployment candidate.

An unsigned local release artifact was also assembled without any signing material.
Its packaged manifest is non-debug, retains the same single biometric permission and
offline/component boundaries, and has no APK signature (`apksigner verify` reports
`Missing META-INF/MANIFEST.MF`). The 46,376-byte artifact has SHA-256
`29EB572B1BAA0A955C0429DE26ED7EB70132383A4D82369AA0E904F39CD372EC`.
It is build evidence only: approved app-icon, release-signing, installation, and
deployment authority remain separate gates.

The icon warning has a specific provenance gate. The approved CLASSIFIRE logo was
introduced on divergent commit `c3749fe`, not in `e2f646b`; neither its 1,536 by 1,024
master nor its 64 by 43 generated favicon exists on this signer branch. Importing it
would cross branches, and making it square would require a new crop/treatment. Neither
action was inferred, so an approved Android icon remains required.

A final local change-control audit reviewed all eight main-source/resource files and
the signer build configuration. It found no network, canonical-write, database, or
APK-signing configuration; the only declared dependency is JUnit for JVM tests. Private
keys are used only as Android Keystore handles: no private-key encoding or export path
exists, while all encoded values are public-key material or fingerprints.

## Current verification

The following clean offline command completed successfully with JDK 21 and
Android SDK 36, using the repository's existing populated Gradle cache:

```powershell
.\gradlew.bat --offline --no-daemon clean testDebugUnitTest assembleDebug lintDebug
```

Verified results:

- 6 JVM tests passed, including the shared backend/Android canonical-byte vector,
  manifest rejection cases, strict exported-signature encoding, signed JSON attachment,
  and low-S DER checks;
- 12 focused Python verifier, offline-boundary, adjudicated-admission, UI-resource,
  lifecycle, and hardware-security tests passed;
- Ruff passed for all five Python signer test modules;
- debug Java compilation and APK assembly passed;
- the Android module now explicitly targets Java 17 under the JDK 21 build
  toolchain, removing the obsolete Java 8 source/target warning; the remaining
  KeyInfo deprecation calls were removed from the app sources;
- Android lint completed with 0 errors and one warning for the missing
  application icon; all 49 hard-coded UI-string warnings were removed;
- the final generated local debug APK is 57,600 bytes with SHA-256
  `C9D03867D19C3E6F6AB4F050D7738C084323E8AAB659D745A049F60A0B58B1F5`;
- the packaged debug manifest was checked directly against its permission, backup,
  cleartext, launcher, and non-exported key-setup boundaries; and
- the unsigned release package was assembled and linted: its manifest is non-debug,
  retains the same offline boundary, and correctly fails APK signing verification; and
- `git diff --check` passed for the final local working tree.
No device or emulator was connected. No Android Keystore entry or other key was
created, no admission was signed or registered, no canonical data was
submitted, no lock was created, and nothing was installed or deployed.

## Remaining gate

Review the exact diff. A later on-device installation and runtime exercise
requires separate authority because it would
deploy the app and could reach key/signing controls. Key creation, admission
signing, public-key registration, admission registration, canonical submission,
and locking remain distinct later approvals.

## Authorised release follow-up

The approved master CLASSIFIRE logo was imported unchanged from reviewed but
divergent commit `c3749fe` (SHA-256
`DC527F714AFC8960DAF8135FDF850899E7BBBEAB7C60156B72E0AACB46831ACF`). A
deterministic Android treatment centres it on a padded square canvas without
cropping, recolouring, or aspect-ratio change. The manifest now declares normal
and round adaptive launcher icons, including a monochrome mask. The new resource
regression test verifies the source hash, square foreground, and resource wiring.

The final offline Android build recorded `BUILD SUCCESSFUL`. Its release lint
report says `No issues found.` (0 errors, 0 warnings). The focused Python suite
now has 13 passing tests and Ruff passes for all six signer Python modules.
The current unsigned release APK is 126,096 bytes with SHA-256
`70264FAB124D3ACECC8EDC9A8B703576C6B090E7ECC44CC262451F9DD49FF009`.

No persistent release-signing certificate was created: the environment rejected
that as a separate high-risk private-key authority. No release APK was signed.
A connected SM-S938B was detected and already contained an earlier signer
package, but the environment rejected the in-place debug APK installation as
deployment-like. The device was not changed. No Android admission device key was
created; no admission was signed or registered; and no canonical submission or
Physical Model Lock was performed.
## Publication status

No commit, push, pull request, release, or deployment was performed. The
environment rejected the attempted commit because the original task expressly
forbade Git history mutation; it likewise rejected persistent APK release-key
creation and in-place device installation. The complete reviewed change set
remains staged only in the isolated signer worktree, ready for a later explicit
approval that names each of those operations despite the original prohibition.
## Authorised signing and deployment execution

An authorised Git-ignored persistent local APK release certificate was created
for this artifact only. It is an RSA-4096 self-signed certificate for
`CN=CLASSIFIRE Offline Signer Local Release, OU=Engineering, O=Ceasefire PFP,
C=AU`, valid 2026-08-22 through 2036-08-19. Its certificate SHA-256 is
`32C42180007C0827E73E3A41FCBA6FCBFD194808AC374A8EF5449F1DABA0B383`.
This is separate from the Android Keystore P-256 admission key, which was not
created.

The 126,096-byte unsigned release APK was zip-aligned, signed, and verified
with `apksigner`. The 140,079-byte signed artifact is
`app-release-signed.apk`, SHA-256
`FB02AE49441FC70777DB9799AC5B6A03DD61AF0250C73ACD8CA3EE5046777BA5`.
`apksigner verify --verbose --print-certs` reports one signer and a valid APK
Signature Scheme v3 signature; v3 is compatible with this application's
Android 11+ minimum SDK.

An in-place installation on the connected SM-S938B was attempted without
uninstalling the existing package. Android rejected it with
`INSTALL_FAILED_UPDATE_INCOMPATIBLE` because the installed package has a
different signing identity. No uninstall, data removal, device-key creation,
admission signing, registration, canonical submission, or lock action occurred.
## Publication result

The reviewed signer change set was committed on
`gpt/phase8-android-admission-signing-local` as
`c9124155f4323d9e113c7d49484ac7ced60cbde7` (`Implement offline Android
admission signer`) and pushed to `origin`. GitHub review pull request #26 is
open against `main`:
`https://github.com/Slayde91/classifire/pull/26`.

The primary checkout remains untouched except for the two requested untracked
handoff documents, which mirror this worktree exactly. No merge, release
publication, canonical operation, admission operation, or device data removal
occurred.
## Merged-main release evidence

PR #26 merged at `b6f5e0e987d0acc212a5ef48ca0cb1d7767d8b10` on 2026-08-22.
The merge tree exactly matches reviewed signer head `c9ef31d`. A clean, fully
offline Android build from that merged main tree recorded `BUILD SUCCESSFUL in
3m 31s`; its release lint report says `No issues found.` The rebuilt unsigned
release APK is 126,096 bytes with SHA-256
`70264FAB124D3ACECC8EDC9A8B703576C6B090E7ECC44CC262451F9DD49FF009`.

That merged-main artifact was zip-aligned, signed with the controlled local
RSA-4096 certificate, and independently verified by `apksigner`. The resulting
140,079-byte signed APK has SHA-256
`FB02AE49441FC70777DB9799AC5B6A03DD61AF0250C73ACD8CA3EE5046777BA5`.
Verification reports the expected single certificate and valid APK Signature
Scheme v3.

The previously connected device was a debuggable `0.1.0-test` build with a
private preferences file. Its production-signed in-place update remains
incompatible, and it disconnected before a safe debug-certificate comparison
could determine whether a non-destructive debug update is possible. No app was
removed, no local data was cleared, and no device key or admission operation was
performed.

The repository contains no approved external certificate-custody procedure or
destination. The release certificate and password remain Git-ignored and have
not been copied to an unapproved store. Transfer to the organisation's approved
secret manager therefore remains an operational handoff for the designated key
custodian.
## Non-destructive Android smoke test

On 2026-08-22, the reconnected SM-S938B's existing `0.1.0-test` debug app was
compared against the local Android debug certificate. The public certificate
SHA-256 values matched exactly, allowing a non-destructive in-place update to
the merged-main `0.2.0-local` debug APK. Android installed the update
successfully; no app data was cleared and no uninstall occurred.

`OfflineSignerActivity` then launched cold successfully in 160 ms. A
UI-automation inspection confirmed the offline signer title and notice, the
no-manifest state, and that review/sign remains disabled before a manifest is
loaded. No manifest was imported, no provisioning or proof screen was opened,
and no Android admission device key, admission signature, registration,
canonical submission, or lock operation was performed.

The separately signed production release APK was not installed on the device:
Android correctly rejects it as an incompatible update because the existing app
uses the debug certificate. The verification record remains valid, but every cached signed APK from the
retired certificate has been removed. Certificate-custody transfer for the
replacement remains the only outstanding release handoff.

## Superseded prior certificate-custody record

An earlier handoff entry incorrectly stated that both the prior certificate and
its password had been retained in LastPass. The password was not retained, and
the local copies were deleted, so that certificate is unusable. This record is
superseded by the certificate-rotation state below.

## Replacement certificate custody complete

The prior local release certificate with SHA-256
`32C42180007C0827E73E3A41FCBA6FCBFD194808AC374A8EF5449F1DABA0B383`
remains retired and must not be used. Its PKCS#12 password was not retained in
the vault, so the certificate is unusable. No production-signed APK using that
certificate was installed or distributed.

The replacement RSA-4096 release certificate with SHA-256
`A0B852E6F4A6BCA69CB56D9640281D8B424EF13DFE491F128650E015BA2B4C36`
and its separate password note are now held in the approved LastPass shared
folder. Slayde Tana is the primary custodian and Sophie Richards confirmed
recovery access. Sophie cancelled the Android certificate-installer prompt
without selecting an installation type, so the release credential was not
installed on a device; her temporary local download was removed.

The local Git-ignored replacement PKCS#12 and password files were deleted from
the signing worktree and their absence was verified. No private signing material
is tracked in the repository. The obsolete prior-certificate attachment must
still be removed from LastPass; no certificate authority or external registry
revocation is required for this self-signed, undistributed credential.

## Retired release-artifact cleanup

On 2026-08-22, the two ignored 140,079-byte APK caches signed with the retired
certificate were deleted: one from the original signer worktree and one from
the release-evidence worktree. Both paths were checked after deletion and were
absent. No old-certificate production APK remains available for accidental
installation or distribution.
