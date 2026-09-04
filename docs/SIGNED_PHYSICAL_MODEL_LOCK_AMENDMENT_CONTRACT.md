# Signed Physical Model Lock Amendment Contract

## Status and boundary

`CLASSIFIRE-SIGNED-PHYSICAL-MODEL-LOCK-AMENDMENT-v1` is a strict, no-write
external-signature contract for a **future** amendment of an active signed
Physical Model Lock.

The verifier and preflight verify eligibility only. They do not invalidate a
lock, edit retained physical records, create a replacement lock, submit
canonical state, choose a technical system, calculate a quantity or price, make
a snapshot, or release anything.

A separately additive admission journal may retain a fresh, verified manifest,
canonical prospective payload, preflight receipt, and human-governance audit
event. That journal does not invalidate a lock, edit canonical physical records,
create a replacement lock, create an execution outcome, or grant execution or
downstream authority. Exact replays are accepted only after every retained manifest,
payload, preflight, signer, timestamp, policy, and target binding is rechecked.

The generic unsigned reopen route does not call this contract. It remains limited
to its separate pre-technical boundary.

## Required signed bindings

The canonical JSON envelope has an amendment-admission UUID and binds exactly:

- one Project, Estimate, and active signed target lock;
- the target lock content hash and a SHA-256 of its retained signature text;
- the current retained physical-model content hash;
- one prospective `InitialCanonicalPhysicalSubmission` payload hash;
- one visual-validation receipt hash and every reviewed controller, evidence,
  family, and human-review hash required by that receipt;
- a nonblank amendment reason, policy versions, signer issuer/key identity,
  issue/expiry timestamps, and an ECDSA P-256 SHA-256 low-S signature.

Evidence, review content, source reports, images, prompts, provider responses,
and private signing keys are not included in the envelope.

Visual-review and canonical-submission digests are uppercase SHA-256 values.
The existing Physical Model Lock content hash remains lowercase because that is
the retained lock identity. Its decimal fields are semantically normalised before
hashing, so equivalent database renderings such as `100` and `100.0000` cannot
make an unchanged physical model appear stale.

## Eligibility recheck

`require_signed_physical_model_lock_amendment` is a database-reading gate. It
fails closed unless all of these remain true at the time it is called:

1. the Estimate and target lock have the exact signed Project/Estimate binding;
2. the lock is still active, has nonblank retained signature text, and its
   current physical hash still matches the stored lock hash;
3. the external amendment signature is valid, current, and exactly bound to the
   independently rebuilt facts and prospective payload;
4. the stored visual-validation receipt is intact, semantically approved, has
   no unresolved material items, and matches every signed receipt binding.

The verifier performs no write or audit event. It therefore cannot be mistaken
for approval or execution authority.

`preflight_signed_physical_model_lock_amendment` is the transaction-ready,
still no-write companion. It locks the target Estimate and active lock, re-runs
the signature/current-hash/visual-receipt checks after the relevant physical
rows are locked, rejects later technical/commercial/rule/snapshot/release work,
and proves every prospective canonical Defect belongs to the same Estimate.
Direct use of the preflight creates no admission, audit event, canonical
physical row, invalidation, or replacement lock. The separate admission journal
may persist the receipt only after it freshly completes that preflight in the
same caller-owned transaction; recording it remains non-executing.

`preflight_registered_signed_physical_model_lock_amendment` is the no-write
consumption bridge for a future writer. It loads the exact admission ID and
expected envelope hash, re-canonicalises and re-hashes the stored envelope and
payload, checks every retained journal binding, and then reruns the locked fresh
preflight. It returns no authority and performs no mutation or audit write.

`build_current_physical_model_lock_snapshot` exposes the exact canonical JSON
preimage used by the existing Physical Model Lock v1 hash. It includes the bound
Defect, evidence, Opening, Service, and ServiceOpeningLink row identities and
fields. The normal lock summary is derived through the same internal builder, so
the snapshot and persisted lock identity cannot silently diverge. The returned
parsed form is detached, and the operation writes nothing or grants no authority.

## Future execution requirements

A future separate signed lock-admission writer must, in one governed transaction:

1. obtain explicit execution authority and call the registered-admission no-write
   preflight, which reruns the fresh signed preflight
   while holding its outer transaction open;
2. retain the preflight's locks while applying only the manifest-bound amendment;
3. recheck technical, commercial, rule, snapshot, release, protected-state, and
   amendment lifecycle dependencies at write time;
4. create a separate immutable execution outcome linked to the already retained
   admission evidence, containing exact pre/post physical payload hashes and row
   identity mappings, plus an attributed audit receipt;
5. invalidate only the exact signed lock authorised by the envelope; and
6. leave replacement submission and replacement-lock creation as separate,
   explicitly authorised operations.

Until that writer exists and is separately authorised, this contract provides no
canonical mutation path.