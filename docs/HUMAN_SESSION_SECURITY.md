# CLASSIFIRE Human Session Security Contract

**Status:** Phase 15 branch candidate; not deployed

**Scope:** Human browser and cookie-authenticated API sessions. OpenClaw and
agent-service bearer identities remain separate.

## Security objective

A browser cookie must not remain sufficient authority after CLASSIFIRE records
that session as logged out, expired, or superseded by a security-sensitive
account change. Browser-side cookie deletion alone is not revocation because a
copied cookie can be replayed.

## Cookie and persistence boundary

New human cookies contain only:

- `session_schema`, fixed to the supported integer schema version;
- `session_token`, a high-entropy opaque value; and
- the existing CSRF value.

The cookie contains no user ID, role, password data, or authentication
generation. CLASSIFIRE stores only the SHA-256 of the opaque token. Raw tokens,
cookies, CSRF values, passwords, and password hashes must never enter logs,
audit events, console output, or receipts.

Each persisted human-session record binds the token hash to one User, the
User's current authentication generation, an absolute expiry, and any later
revocation time and reason.

## Lifecycle

1. Login locks and rechecks the current User, verifies the password and active
   state, creates a new session bound to the current authentication generation,
   and commits the login state in one transaction.
2. Every human authentication lookup hashes the supplied opaque token and
   requires one matching, unexpired, unrevoked server record. The bound User
   must still exist, be active, and retain the exact bound authentication
   generation.
3. Normal logout revokes only the current server-side session, commits that
   revocation, and then expires the responding browser cookie.
4. Logout-all and governed password, role, email, activation, or security-policy
   changes rotate the User's authentication generation and revoke all of that
   User's existing session rows in the same transaction.
5. A new login after an account-wide revocation receives a new opaque token
   bound to the new generation. No revoked row is reactivated.

The initial absolute session lifetime is twelve hours, matching the signed
cookie lifetime. Expired and revoked records require bounded operational cleanup
without deleting their separate audit history.

## Fail-closed compatibility

Legacy cookies containing `user_id`, cookies missing the schema or token,
unknown future schema versions, malformed values, missing records, expired or
revoked records, deleted Users, inactive Users, and generation mismatches are
all treated as unauthenticated and the current cookie state is cleared.

Anonymous sessions with no authentication keys may retain their login-page CSRF
state. There is no silent conversion of a legacy cookie into a server-side
session.

CSRF verification first validates authenticated cookie structure. Malformed
cookie or form values return a controlled forbidden response rather than an
application error. An ordinary incorrect submitted CSRF value does not destroy
an otherwise valid session.

## Transaction and concurrency rules

- Login and account-wide revocation lock the same User row before finalising.
- Account mutation, generation rotation, session-row revocation, and the audit
  event commit together or roll back together.
- Production code must use the governed account-security mutation service for
  password hashes, roles, email addresses, and activation state. Direct ORM
  mutation of those fields is an unsupported internal bypass.
- Normal logout is idempotent and cannot reactivate a revoked row.
- A login committed before logout-all is revoked; a login beginning after the
  committed rotation may use the new generation.
- A request already authenticated and executing when revocation commits cannot
  be retroactively cancelled. High-consequence writes may require a final
  session recheck inside their own write transaction as a later bounded policy.

## Audit and operations

Normal logout audits the exact Human Session record. Account-wide revocation
audits the target User. Governed account changes separately record only safe
before/after fields and a password-changed flag. These events bind the actor,
reason, time, source address when available, and non-secret state transition.
They never contain a raw token, token hash, token hint, cookie, CSRF value,
password, password hash, or authentication generation.

Deployment requires the additive migration, draining old application nodes,
and a fresh login for every human session. The session-signing secret should be
rotated at cutover. Restoring a database backup can resurrect older session
rows, so recovery must also rotate the signing secret or revoke/rotate all human
sessions before service resumes.

The initial administrator must be created by an authorised operator through the
audited `classifire create-admin --operator-reference ...` command. There is no
environment-provided default administrator. Follow the
[production configuration and bootstrap runbook](./PRODUCTION_CONFIGURATION.md)
for the required configuration and the explicitly attributed `create-admin`
-> `init` -> `start` sequence.

Startup and operational commands never apply metadata changes to a non-empty
database. Production requires the exact reviewed Alembic head and its critical
session constraints. Development and test may create only a completely empty
database or reopen an already-current unversioned development schema.

This contract does not authorise a live migration, deployment, production
configuration change, canonical write, Physical Model Lock, or release.
