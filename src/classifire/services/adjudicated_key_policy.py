"""Fail-closed resolution of the public key for an adjudicated admission."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from .adjudicated_admission import AdmissionVerificationError, validate_p256_public_key

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$")


class AdjudicatedKeyPolicyError(RuntimeError):
    """Safe policy error type; ``code`` is suitable for a later audit receipt."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Adjudicated key policy failed: {code}.")


def resolve_adjudicated_public_key(
    *,
    enabled: bool,
    public_keys: Mapping[str, str],
    issuer_key_ids: Mapping[str, Sequence[str]],
    issuer: str,
    key_id: str,
) -> str:
    """Resolve one configured public key only when its issuer binding is explicit."""
    if not enabled:
        _fail("ADJUDICATED_SUBMISSION_DISABLED")
    if not _valid_identifier(issuer) or not _valid_identifier(key_id):
        _fail("ADMISSION_POLICY_IDENTIFIER_INVALID")
    allowed_key_ids = issuer_key_ids.get(issuer)
    if not isinstance(allowed_key_ids, Sequence) or isinstance(allowed_key_ids, str):
        _fail("ADMISSION_ISSUER_KEY_UNBOUND")
    if key_id not in allowed_key_ids:
        _fail("ADMISSION_ISSUER_KEY_UNBOUND")
    public_key = public_keys.get(key_id)
    if not isinstance(public_key, str):
        _fail("ADMISSION_PUBLIC_KEY_UNAVAILABLE")
    try:
        validate_p256_public_key(public_key)
    except AdmissionVerificationError as exc:
        _fail(exc.code)
    return public_key


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _fail(code: str) -> None:
    raise AdjudicatedKeyPolicyError(code)
