# External Signer Operating Model for Adjudicated Admissions

**Status:** Draft operating design; no key has been created, configured, or
used.  
**Purpose:** Define how an independently controlled external signer
authorises a one-time CLASSIFIRE adjudicated initial-model admission.  
**Does not authorise:** key creation, public-key configuration, admission
registration, canonical model submission, or Physical Model Lock creation.

## 1. Security boundary

CLASSIFIRE may verify an admission, but it must never be able to create one.
The signing private key stays non-exportable in an approved external signer and
is operated only by the nominated governance signer or an approved delegate.

CLASSIFIRE receives only:

- a stable public-key identifier;
- the public P-256 verification key in canonical DER SubjectPublicKeyInfo,
  encoded as unpadded base64url;
- an explicit issuer-to-key authorisation mapping; and
- a signed admission manifest plus its linked no-write preflight receipt.

The signer identity is an operational assignment recorded in the deployment
change record. It is not itself a cryptographic identifier and is not embedded
in source code.

## 2. Roles and separation

| Role | Responsibility | May not do |
| --- | --- | --- |
| Governance signer | Reviews and approves a single fresh admission; causes the external signer to sign it. | Operate through CLASSIFIRE with a private key. |
| Signer custodian | Creates, protects, rotates, and revokes the non-exportable signing key. | Submit a model merely by managing a key. |
| CLASSIFIRE verifier | Pins the public key and verifies manifest bindings and signature. | Create a signature or access the private key. |
| Controlled writer | Executes a registered admission ID once, after an in-transaction recheck. | Choose payload, register an admission, or create a lock. |

For the initial rollout, one accountable governance signer is acceptable. Key
signer custodian should be a separate accountable role wherever the
organisation can support that separation.

## 3. Required external-signer capability

Before selecting or creating a key, the signer custodian must confirm
that the chosen platform supports all of the following:

1. A **P-256** signing key whose private portion is non-exportable.
2. Signing of caller-provided canonical bytes using `ECDSA_P256_SHA256`.
3. Export of the corresponding public verification key.
4. Audit records for key creation, use, disablement, rotation, and deletion.
5. Human access control that requires the nominated signer to approve use.

Do not substitute an RSA, Ed25519, HMAC, password, API token, GitHub token, or
CLASSIFIRE application secret. The production v2 verifier accepts only
`ECDSA_P256_SHA256` admission signatures and canonical P-256 public keys.

## 4. Initial key and identity convention

The signer custodian proposes the following non-secret values for review
before configuration:

| Item | Required form | Example naming pattern |
| --- | --- | --- |
| Issuer ID | Stable lower-case identifier for the governance authority. | `classifire-governance` |
| Key ID | Stable identifier for this exact public key/version. | `governance-p256-01` |
| Public key | Unpadded base64url encoding of canonical 91-byte DER P-256 SubjectPublicKeyInfo. | Exported by the signer; never invented manually. |
| Issuer mapping | Explicit list of the Key IDs each issuer may use. | `classifire-governance -> [governance-p256-01]` |

The private key must not be exported, pasted into a terminal, stored in a
repository, sent to CLASSIFIRE, or placed in an `.env` file.

## 5. One-time admission approval flow

The signer must approve only a freshly generated, no-write preflight. The
manifest must bind exactly the values that CLASSIFIRE will verify:

1. Admission ID, purpose, project ID, estimate ID, source run ID, and
   adjudicated run ID.
2. Preflight receipt SHA-256 and normalized submission-payload SHA-256.
3. Protected-state fingerprint and fingerprint version.
4. Artifact digest map and policy-version map.
5. Issuer ID, Key ID, issue time, expiry time, and `ECDSA_P256_SHA256` signature.

Before signing, the governance signer must confirm:

- the preflight is current and says no canonical write occurred;
- the estimate, project, payload hash, and protected fingerprint are expected;
- the proposal remains subject to all withheld limitations;
- the manifest has a new admission ID and a short expiry; and
- no Physical Model Lock is requested or implied.

For the initial rollout, use a maximum manifest lifetime of **15 minutes**.
CLASSIFIRE will reject expired, mismatched, replayed, or issuer/key-unbound
admissions.

## 6. External signing procedure

1. Generate the no-write preflight from the current protected state.
2. Construct the admission manifest using the exact fields above and a valid
   placeholder signature field required by the schema.
3. Derive the canonical unsigned bytes through the approved manifest procedure;
   do not sign a reformatted or hand-edited JSON copy.
4. The signer produces a strict DER `ECDSA_P256_SHA256` signature over those
   canonical bytes with the approved non-exportable P-256 key.
5. Attach the base64url signature to the manifest without changing any other
   field.
6. Preserve the signed manifest and the preflight receipt in the organisational
   change record.
7. Provide the manifest to the offline CLASSIFIRE registration command only
   after a separate registration approval.

Registration creates an immutable admission-journal record only. It does not
submit a model or create a lock. Model submission requires a later, separate
current authorization.

## 7. Rotation, revocation, and incident response

- **Routine rotation:** add a new Key ID and explicit issuer mapping, validate
  it with a disposable synthetic manifest, then retire the old mapping after
  all valid short-lived admissions expire.
- **Suspected compromise:** immediately disable adjudicated submission, remove
  the affected issuer/key mapping, preserve audit evidence, and issue a new
  preflight after investigation. Do not attempt to reuse an existing admission.
- **Signer unavailable:** do not delegate silently. Keep the writer disabled
  until governance appoints a replacement signer and an approved signer key
  is configured.
- **Lost signer access:** do not weaken CLASSIFIRE verification or introduce
  a local fallback key. Restore access through the signer's approved recovery
  process or provision a new key after governance approval.

## 8. Evidence to retain

Retain, without private key material:

- Signer platform and key provenance record;
- issuer ID, Key ID, and public-key fingerprint;
- signer approval reference and signer audit reference;
- no-write preflight receipt hash and signed-manifest hash;
- offline admission-registration receipt; and
- any key rotation, revocation, or incident decision.

## 9. Next required decision

Before any key creation or CLASSIFIRE configuration, provide:

1. the external signer platform and accountable signer custodian;
2. confirmation that it supports non-exportable P-256 signing of canonical
   bytes; and
3. explicit approval for that administrator to create the initial signing key.

Until all three are present, the adjudicated writer remains disabled and no
admission, canonical model, or Physical Model Lock may be created.
