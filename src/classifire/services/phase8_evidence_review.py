"""Content-safe, non-canonical Phase 8 evidence-review artifacts."""

from __future__ import annotations

import re
import unicodedata

from ..blind_visual_inventory import blind_observation_catalog
from .phase8_visual_proposal import VISUAL_PROPOSAL_BLOCKED

EVIDENCE_REVIEW_REQUEST_SCHEMA = "CLASSIFIRE-PHASE8-EVIDENCE-REVIEW-REQUEST-v1"
_MAX_REVIEW_ITEM_TEXT_LENGTH = 2_000
_MAX_REVIEW_IDENTIFIER_LENGTH = 128
_REVIEW_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_URI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]{1,20}://")
_UNSAFE_REVIEW_TEXT_MARKERS = (
    "authorization:",
    "bearer ",
    "data:",
    "file://",
    "ftp://",
    "http://",
    "https://",
    "key-pair-id=",
    "signature=",
    "token=",
    "x-amz-",
)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _contains_unsafe_review_text(value: str) -> bool:
    folded = value.casefold()
    return (
        any(ord(character) < 32 or ord(character) == 127 for character in value)
        or _URI_SCHEME.search(value) is not None
        or any(marker in folded for marker in _UNSAFE_REVIEW_TEXT_MARKERS)
    )


def _safe_review_text(value: object) -> str:
    text = unicodedata.normalize("NFC", value.strip()) if isinstance(value, str) else ""
    if (
        not text
        or len(text) > _MAX_REVIEW_ITEM_TEXT_LENGTH
        or _contains_unsafe_review_text(text)
    ):
        return ""
    return text


def _safe_review_code(value: object) -> str | None:
    candidate = _safe_review_text(value)
    if (
        candidate
        and len(candidate) <= 120
        and all(
            character.isupper() or character.isdigit() or character == "_"
            for character in candidate
        )
    ):
        return candidate
    return None


def _safe_review_identifier(value: object) -> str | None:
    candidate = _safe_review_text(value)
    if (
        candidate
        and len(candidate) <= _MAX_REVIEW_IDENTIFIER_LENGTH
        and _REVIEW_IDENTIFIER.fullmatch(candidate)
    ):
        return candidate
    return None


def _safe_review_evidence_refs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            item
            for item in (_safe_review_identifier(candidate) for candidate in value)
            if item
        )
    )


def _blind_observation_details(
    inventory: object,
) -> dict[str, dict[str, object]]:
    """Return safe source details for stable blind-observation IDs only."""

    if not isinstance(inventory, dict):
        return {}

    catalog = blind_observation_catalog(inventory)
    details: dict[str, dict[str, object]] = {}

    def add(
        *,
        candidate_id_value: object,
        allowed_kinds: set[str],
        detail_value: object,
        evidence_refs_value: object,
    ) -> None:
        candidate_id = _safe_review_identifier(candidate_id_value)
        detail = _safe_review_text(detail_value)
        kind = catalog.get(candidate_id) if candidate_id else None
        if not candidate_id or not detail or kind not in allowed_kinds:
            return
        details[candidate_id] = {
            "blind_candidate_id": candidate_id,
            "kind": kind,
            "detail": detail,
            "evidence_refs": _safe_review_evidence_refs(evidence_refs_value),
        }

    openings = inventory.get("candidate_openings")
    if isinstance(openings, list):
        for item in openings:
            if isinstance(item, dict):
                add(
                    candidate_id_value=item.get("candidate_id"),
                    allowed_kinds={"opening"},
                    detail_value=item.get("detail"),
                    evidence_refs_value=item.get("evidence_refs"),
                )
    services = inventory.get("candidate_services")
    if isinstance(services, list):
        for item in services:
            if isinstance(item, dict):
                add(
                    candidate_id_value=item.get("candidate_id"),
                    allowed_kinds={"service"},
                    detail_value=item.get("detail"),
                    evidence_refs_value=item.get("evidence_refs"),
                )
    unresolved_candidates = inventory.get("unresolved_candidates")
    if isinstance(unresolved_candidates, list):
        for index, item in enumerate(unresolved_candidates, start=1):
            if isinstance(item, dict):
                add(
                    candidate_id_value=item.get("candidate_id") or f"V-U-{index:03d}",
                    allowed_kinds={
                        "unresolved:barrier",
                        "unresolved:opening",
                        "unresolved:service",
                        "unresolved:link",
                        "unresolved:classification",
                        "unresolved:photo_relationship",
                    },
                    detail_value=item.get("detail"),
                    evidence_refs_value=item.get("evidence_refs"),
                )
    limitations = inventory.get("limitations")
    if isinstance(limitations, list):
        for index, limitation in enumerate(limitations, start=1):
            add(
                candidate_id_value=f"V-L-{index:03d}",
                allowed_kinds={"limitation"},
                detail_value=limitation,
                evidence_refs_value=[],
            )

    return details


def _unresolved_blind_observations(
    *,
    visual_result: object,
    validator: dict[str, object],
) -> list[dict[str, object]]:
    """Retain only Validator-declared unresolved blind observations for review."""

    observations = _blind_observation_details(
        getattr(visual_result, "blind_inventory", None)
    )
    reconciliation = validator.get("blind_reconciliation")
    if not isinstance(reconciliation, list):
        return []

    unresolved: dict[str, dict[str, object]] = {}
    for item in reconciliation:
        if not isinstance(item, dict):
            continue
        candidate_id = _safe_review_identifier(item.get("blind_candidate_id"))
        if candidate_id is None:
            continue
        disposition = str(item.get("disposition") or "").strip().upper()
        observation = observations.get(candidate_id)
        if disposition != "UNRESOLVED" or observation is None:
            continue
        unresolved[candidate_id] = {
            **observation,
            "validator_detail": _safe_review_text(item.get("detail")) or None,
            "validator_evidence_refs": _safe_review_evidence_refs(
                item.get("evidence_refs")
            ),
        }

    return [unresolved[candidate_id] for candidate_id in sorted(unresolved)]


def _artifact_text_is_safe(value: object) -> bool:
    if isinstance(value, str):
        return not _contains_unsafe_review_text(value)
    if isinstance(value, list):
        return all(_artifact_text_is_safe(item) for item in value)
    if isinstance(value, dict):
        return all(
            _artifact_text_is_safe(key) and _artifact_text_is_safe(item)
            for key, item in value.items()
        )
    return value is None or isinstance(value, (bool, int, float))


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def build_blocked_visual_evidence_review_request(
    *,
    package_id: str,
    approval_reference: str,
    visual_result: object,
    controller_receipt_file_sha256: str,
    proposal_file_sha256: str | None,
) -> dict[str, object] | None:
    """Build a safe human-review request only for a Validator evidence block."""

    if getattr(visual_result, "status", None) != VISUAL_PROPOSAL_BLOCKED:
        return None
    validator_value = getattr(visual_result, "validator", None)
    if not isinstance(validator_value, dict):
        return None
    validator: dict[str, object] = validator_value
    verdict = str(validator.get("verdict") or "").strip().upper()
    if not isinstance(proposal_file_sha256, str):
        return None
    if (
        verdict != "BLOCKED"
        or not _safe_review_identifier(package_id)
        or not _safe_review_identifier(approval_reference)
        or not _valid_sha256(controller_receipt_file_sha256)
        or not _valid_sha256(proposal_file_sha256)
    ):
        return None

    review_items: list[dict[str, object]] = []
    issues = validator.get("issues")
    if not isinstance(issues, list):
        issues = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        detail = _safe_review_text(issue.get("detail"))
        if detail:
            review_items.append(
                {
                    "source": "validator_issue",
                    "code": _safe_review_code(issue.get("code")),
                    "detail": detail,
                    "evidence_refs": _safe_review_evidence_refs(
                        issue.get("evidence_refs")
                    ),
                }
            )
    limitations = validator.get("limitations")
    if not isinstance(limitations, list):
        limitations = []
    for limitation in limitations:
        detail = _safe_review_text(limitation)
        if detail:
            review_items.append(
                {
                    "source": "validator_limitation",
                    "code": None,
                    "detail": detail,
                    "evidence_refs": [],
                }
            )
    unresolved = _unresolved_blind_observations(
        visual_result=visual_result,
        validator=validator,
    )
    if not review_items and not unresolved:
        return None

    request: dict[str, object] = {
        "schema": EVIDENCE_REVIEW_REQUEST_SCHEMA,
        "status": "HUMAN_EVIDENCE_REVIEW_REQUIRED",
        "package_id": package_id,
        "approval_reference": approval_reference,
        "visual_proposal_status": VISUAL_PROPOSAL_BLOCKED,
        "controller_receipt_file_sha256": controller_receipt_file_sha256.upper(),
        "proposal_file_sha256": proposal_file_sha256.upper(),
        "review_items": review_items,
        "unresolved_blind_observations": unresolved,
        "reviewer_instructions": [
            "Resolve each review item against retained evidence or newly governed evidence.",
            "Record each item as Confirmed, Contradicted, or Unresolved before "
            "another proposal run.",
            "Do not submit, lock, or price this blocked proposal.",
        ],
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }
    return request if _artifact_text_is_safe(request) else None


__all__ = [
    "EVIDENCE_REVIEW_REQUEST_SCHEMA",
    "build_blocked_visual_evidence_review_request",
]
