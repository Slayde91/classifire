"""Retained workbook evidence and reviewed batch-to-Scope commands, never pricing."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DraftScopeXlsxSource, User
from .draft_scope import (
    DraftScopeError,
    _actor,
    _append_revision,
    _revision_envelope,
    _valid_hash,
    get_draft,
    read_revision,
    validate_payload,
)
from .draft_scope_evidence import (
    MAX_EVIDENCE_REFS,
    TARGET_COLLECTIONS,
    observation_hash,
    reference_identity,
    reference_label,
)
from .draft_scope_xlsx_contract import SCHEMA, digest, selected_rows, validate_document
from .draft_source_intake import DraftSourceIntake, SourcePolicy


def _run_worker(content: bytes, *arguments: str, image: bool = False, word: bool = False) -> bytes:
    validator: Callable[[Any], bool] = validate_document
    if word:
        from .draft_scope_docx_document import validate_document as validate_word

        validator = validate_word
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    try:
        result = subprocess.run(  # noqa: S603 # nosec B603
            [sys.executable, "-m", "classifire.services.draft_pricing_worker", *arguments],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            env=environment,
        )
        limit = (4 if image else 2) * 1024 * 1024
        if result.returncode != 0 or not 1 <= len(result.stdout) <= limit:
            raise ValueError("worker output")
        if image:
            if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("image format")
        else:
            document = json.loads(result.stdout)
            if (
                not validator(document)
                or document["manifest"]["source_sha256"] != hashlib.sha256(content).hexdigest()
                or document["manifest"]["source_size_bytes"] != len(content)
            ):
                raise ValueError("worker binding")
    except (
        OSError,
        subprocess.TimeoutExpired,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
    ) as exc:
        raise DraftScopeError(
            "SCOPE_DOCX_PROCESSING_FAILED" if word else "SCOPE_XLSX_PROCESSING_FAILED"
        ) from exc
    return result.stdout


def _process(content: bytes) -> bytes:
    return _run_worker(content, "--scope-evidence")


def intake() -> DraftSourceIntake:
    return DraftSourceIntake(
        SourcePolicy(
            model=DraftScopeXlsxSource,
            purpose="draft_scope_xlsx",
            extension=".xlsx",
            magic=b"PK",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            schema=SCHEMA,
            code_prefix="SCOPE_XLSX_",
            audit_name="draft_scope_xlsx",
            process=_process,
            valid_document=validate_document,
        )
    )


def _review_context(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    expected_document_hash: str,
    settings: Settings,
    *,
    source_api: DraftSourceIntake | None = None,
    review_schema: str = "CLASSIFIRE-DRAFT-XLSX-SCOPE-REVIEW-v1",
) -> tuple[User, dict[str, Any], dict[str, Any], dict[str, Any]]:
    actor = _actor(db, actor, "project:write")
    current = read_revision(db, actor, draft_id)
    if type(expected_revision) is not int or expected_revision != current["revision"]:
        raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
    source_api = source_api or intake()
    source, document, content = source_api._document(
        db, actor, draft_id, source_id, settings.storage_root
    )
    if source.document_sha256 != expected_document_hash:
        raise DraftScopeError(source_api.policy.code_prefix + "SOURCE_CHANGED", 409)
    binding = {
        "schema": review_schema,
        "actor_id": actor.id,
        "draft_id": draft_id,
        "expected_revision": expected_revision,
        "current_hash": current["sha256"],
        "source_id": source.id,
        "source_sha256": content.sha256,
        "source_size_bytes": content.size_bytes,
        "original_filename": source.original_filename,
        "document_sha256": source.document_sha256,
        "scan_sha256": hashlib.sha256((source.scan_json or "").encode("utf-8")).hexdigest(),
    }
    return actor, current, document, binding


def _rows(document: dict[str, Any], plan: Any):
    try:
        return selected_rows(document, plan)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise DraftScopeError("SCOPE_XLSX_MAPPING_INVALID") from exc


def _mapped_items(row: dict[str, Any], kinds: list[str], draft_id: str, basis: str):
    fields = row["fields"]
    findings = []

    def problem(field: str, message: str) -> None:
        findings.append(
            {
                "code": "XLSX_FIELD_UNRESOLVED",
                "severity": "warning",
                "path": f"{row['sheet']}!row{row['row']}.{field}",
                "message": message,
            }
        )

    def value(field: str, maximum: int = 500) -> str:
        cell = fields[field]
        if cell is None:
            return ""
        if cell["kind"] not in {"text", "number"}:
            problem(
                field, "The source cell is a formula or unsupported value; it was not inferred."
            )
            return ""
        raw: str = cell["value"]
        text = raw.strip()
        if len(text) > maximum:
            problem(
                field, "The source value is too long for this field; review it and enter a value."
            )
            return ""
        return text

    def number(field: str) -> str | None:
        raw = value(field, 100)
        if not raw:
            return None
        if re.fullmatch(r"(0|[1-9][0-9]{0,8})(\.[0-9]{1,6})?", raw) is None:
            problem(
                field,
                "The source number is ambiguous or unsupported; the Draft value stays unknown.",
            )
            return None
        return raw

    items = []
    for kind in kinds:
        identity = str(
            uuid5(UUID(draft_id), f"scope-xlsx-v1:{basis}:{row['sheet_index']}:{row['row']}:{kind}")
        )
        label = value(kind + "_label", 200)
        if not label:
            label = f"{kind.capitalize()} from sheet {row['sheet_index']} row {row['row']}"
            problem(
                kind + "_label",
                "The source label is missing or unsupported; this is a generated Draft label.",
            )
        item: dict[str, Any] = {"id": identity, "label": label}
        if kind == "defect":
            description = value("defect_description", 4000)
            location = value("location", 4000)
            combined = "\n".join(
                part for part in (f"Location: {location}" if location else "", description) if part
            )
            if len(combined) > 4000:
                combined = ""
                problem(
                    "defect_description",
                    "Combined location/description is too long; enter a reviewed summary.",
                )
            item["description"] = combined
        elif kind == "opening":
            plane = value("plane").lower() or "unknown"
            if plane not in {"wall", "floor", "soffit", "unknown"}:
                plane = "unknown"
                problem("plane", "The source plane is unsupported; it remains unknown.")
            item.update(
                defect_id=None,
                plane=plane,
                substrate=value("substrate"),
                width_mm=number("width_mm"),
                height_mm=number("height_mm"),
                blank=False,
                state="Unresolved",
            )
        else:
            quantity = number("quantity")
            unit = value("unit").lower()
            if unit not in {"each", "m", "mm"}:
                if quantity is not None or fields["unit"] is not None:
                    problem("unit", "Quantity is withheld until its unit is explicitly reviewed.")
                quantity, unit = None, "each"
            item.update(
                opening_ids=[],
                service_type=value("service_type"),
                quantity=quantity,
                unit=unit,
                state="Unresolved",
            )
        items.append((kind, item))
    return items, findings


def prepare_mapping(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    plan: dict[str, Any],
    expected_document_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Prepare one selected batch for editing without saving or inferring relationships."""
    with db.no_autoflush:
        actor, current, document, binding = _review_context(
            db, actor, draft_id, source_id, expected_revision, expected_document_hash, settings
        )
        plan, rows = _rows(document, plan)
        payload = copy.deepcopy(current["content"])
        targets, findings = [], []
        basis = digest(
            {
                "current": binding["current_hash"],
                "source": binding["source_sha256"],
                "document": binding["document_sha256"],
                "plan": plan,
            }
        )
        for selection, row in zip(plan["selections"], rows, strict=True):
            items, problems = _mapped_items(row, selection["kinds"], draft_id, basis)
            findings.extend(problems)
            for kind, item in items:
                payload[TARGET_COLLECTIONS[kind]].append(item)
                targets.append(
                    {
                        "target_kind": kind,
                        "target_id": item["id"],
                        "row": row["row"],
                        "image_ids": [],
                    }
                )
            for problem in problems:
                text = f"Workbook mapping: {problem['path']}: {problem['message']}"
                payload["observations"].append(
                    {
                        "id": str(uuid5(UUID(draft_id), f"scope-xlsx-warning:{basis}:{text}")),
                        "text": text,
                        "state": "Unresolved",
                    }
                )
        model, graph_findings = validate_payload(payload)
        # Reuse the final review validator for total-ref and graph bounds even at preparation.
        prepared = preview_review(
            db,
            actor,
            draft_id,
            source_id,
            expected_revision,
            model.model_dump(mode="json"),
            plan,
            targets,
            expected_document_hash,
            settings=settings,
        )
        prepared["findings"] = findings + graph_findings
        return prepared


def preview_review(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    payload: dict[str, Any],
    plan: dict[str, Any],
    targets: list[dict[str, Any]],
    expected_document_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    with db.no_autoflush:
        actor, current, document, binding = _review_context(
            db, actor, draft_id, source_id, expected_revision, expected_document_hash, settings
        )
        plan, rows = _rows(document, plan)
        model, findings = validate_payload(payload)
        normalized = model.model_dump(mode="json")
        if type(targets) is not list or not 1 <= len(targets) <= MAX_EVIDENCE_REFS:
            raise DraftScopeError("SCOPE_XLSX_TARGETS_INVALID")
        selected_rows_by_number = {row["row"]: row for row in rows}
        sheet = document["sheets"][plan["sheet_index"] - 1]
        images = {image["occurrence_id"]: image for image in sheet["images"]}
        selected, identities = [], set()
        for target in targets:
            if (
                type(target) is not dict
                or set(target) != {"target_kind", "target_id", "row", "image_ids"}
                or type(target["target_kind"]) is not str
                or target["target_kind"] not in TARGET_COLLECTIONS
                or type(target["target_id"]) is not str
                or type(target["row"]) is not int
                or target["row"] not in selected_rows_by_number
                or type(target["image_ids"]) is not list
                or len(target["image_ids"]) > 50
                or any(
                    type(identity) is not str or identity not in images
                    for identity in target["image_ids"]
                )
            ):
                raise DraftScopeError("SCOPE_XLSX_TARGETS_INVALID")
            identity = (target["target_kind"], target["target_id"], target["row"])
            if (
                identity in identities
                or len(set(target["image_ids"])) != len(target["image_ids"])
                or not any(
                    item["id"] == target["target_id"]
                    for item in normalized[TARGET_COLLECTIONS[target["target_kind"]]]
                )
            ):
                raise DraftScopeError("SCOPE_XLSX_TARGETS_INVALID")
            identities.add(identity)
            selected.append(dict(target, image_ids=sorted(target["image_ids"])))
        selected.sort(
            key=lambda target: (target["target_kind"], target["target_id"], target["row"])
        )
        observations = {item["id"] for item in normalized["observations"]}
        existing = {
            reference_identity(ref)
            for ref in current.get("evidence_refs", [])
            if "target_kind" in ref or ref["observation_id"] in observations
        }
        existing.update(
            (kind, identity, source_id, f"xlsx:{plan['sheet_index']}:{row}")
            for kind, identity, row in identities
        )
        if len(existing) > MAX_EVIDENCE_REFS:
            raise DraftScopeError("SCOPE_XLSX_REFERENCE_LIMIT")
        image_claims = {
            image_id: images[image_id] for target in selected for image_id in target["image_ids"]
        }
        binding.update(
            payload=normalized, plan=plan, targets=selected, rows=rows, selected_images=image_claims
        )
        # UTC isoformat has at most 32 characters. Account for that exact upper bound
        # for the eventual save timestamps, using the writer's own merge/encoder/budget.
        budget_time = datetime.max.replace(tzinfo=UTC)
        _revision_envelope(
            draft_id=draft_id,
            project_id=current["project_id"],
            actor_id=actor.id,
            expected_revision=expected_revision,
            created=budget_time,
            content=normalized,
            prior=current,
            entity_evidence_refs=_review_refs(binding, budget_time.isoformat()),
        )
        _actor(db, actor, "project:write")
        read_revision(db, actor, draft_id)
        return binding | {
            "review_sha256": digest(binding),
            "findings": findings,
            "target_labels": [reference_label(target, normalized) for target in selected],
        }


def _review_refs(preview: dict[str, Any], reviewed_at: str) -> list[dict[str, Any]]:
    """Create the same selected row/image claims for size validation and final saving."""
    rows = {row["row"]: row for row in preview["rows"]}
    refs = []
    for target in preview["targets"]:
        item = next(
            item
            for item in preview["payload"][TARGET_COLLECTIONS[target["target_kind"]]]
            if item["id"] == target["target_id"]
        )
        ref = {
            key: preview[key]
            for key in (
                "source_id",
                "source_sha256",
                "source_size_bytes",
                "original_filename",
                "document_sha256",
                "scan_sha256",
            )
        }
        ref.update(
            source_kind="xlsx",
            target_kind=target["target_kind"],
            target_id=target["target_id"],
            target_sha256=observation_hash(item),
            row=rows[target["row"]],
            images=[preview["selected_images"][image_id] for image_id in target["image_ids"]],
            reviewed_by=preview["actor_id"],
            reviewed_at=reviewed_at,
            method="human_xlsx_row_entity_review",
            origin="local_retained",
        )
        refs.append(ref)
    return refs


def save_review(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    payload: dict[str, Any],
    plan: dict[str, Any],
    targets: list[dict[str, Any]],
    expected_document_hash: str,
    expected_review_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    preview = preview_review(
        db,
        actor,
        draft_id,
        source_id,
        expected_revision,
        payload,
        plan,
        targets,
        expected_document_hash,
        settings=settings,
    )
    if not _valid_hash(expected_review_hash) or not hmac.compare_digest(
        preview["review_sha256"], expected_review_hash
    ):
        raise DraftScopeError("SCOPE_XLSX_PREVIEW_CHANGED", 409)
    refs = _review_refs(preview, datetime.now(UTC).isoformat())
    return _append_revision(
        db, actor, draft_id, expected_revision, preview["payload"], entity_evidence_refs=refs
    )


def image_preview(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    sheet_index: int,
    occurrence_id: str,
    *,
    settings: Settings,
) -> bytes:
    source, document, content = intake()._document(
        db, actor, draft_id, source_id, settings.storage_root
    )
    if type(sheet_index) is not int or not 1 <= sheet_index <= len(document["sheets"]):
        raise DraftScopeError("SCOPE_XLSX_IMAGE_NOT_FOUND", 404)
    descriptor = next(
        (
            image
            for image in document["sheets"][sheet_index - 1]["images"]
            if image["occurrence_id"] == occurrence_id
        ),
        None,
    )
    if descriptor is None:
        raise DraftScopeError("SCOPE_XLSX_IMAGE_NOT_FOUND", 404)
    preview = _run_worker(
        content.content, "--scope-image", str(sheet_index), occurrence_id, image=True
    )
    if hashlib.sha256(preview).hexdigest() != descriptor["preview_sha256"]:
        raise DraftScopeError("SCOPE_XLSX_IMAGE_CHANGED", 409)
    _actor(db, actor, "project:read")
    get_draft(db, actor, draft_id)
    return preview
