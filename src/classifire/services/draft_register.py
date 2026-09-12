"""Read-only register projections from explicit saved Draft artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import User
from ..security import has_permission
from . import draft_estimates as estimates
from . import draft_system_matches as matches
from .draft_scope import DraftScopeError, get_draft, read_revision
from .draft_scope_evidence import reference_changed, reference_label, reference_status


def hierarchy_review(content: dict[str, Any]) -> dict[str, list[str]]:
    """Classify intake without rewriting identities, links or historical evidence."""
    defects = {item["id"] for item in content["defects"]}
    openings = {item["id"]: item for item in content["openings"]}
    result: dict[str, list[str]] = {}
    used: set[str] = set()
    for service in content["services"]:
        links = service["opening_ids"]
        reasons = []
        if len(links) != 1:
            reasons.append("Select one parent Opening; existing links are preserved for review.")
        for identity in links:
            opening = openings.get(identity)
            if opening is None:
                reasons.append("The linked Opening is unavailable.")
                continue
            used.add(identity)
            if opening["defect_id"] not in defects:
                reasons.append("The parent Opening needs a Defect.")
            if opening["blank"]:
                reasons.append("A blank Opening cannot contain a Service.")
        result[service["id"]] = list(dict.fromkeys(reasons))
    for identity, opening in openings.items():
        reasons = []
        if opening["defect_id"] not in defects:
            reasons.append("Select a parent Defect.")
        if not opening["blank"] and identity not in used:
            reasons.append("Confirm whether this Opening is blank or identify its Services.")
        result[identity] = reasons
    return result


def _selection(value: str) -> tuple[str, int]:
    try:
        identity, number = value.rsplit(":", 1)
        UUID(identity)
        revision = int(number)
        if str(revision) != number or not 1 <= revision <= 2_147_483_647:
            raise ValueError
        return identity, revision
    except (ValueError, AttributeError) as exc:
        raise DraftScopeError("REGISTER_SELECTION_INVALID", 422) from exc


def register_context(
    db: Session,
    actor: User,
    draft_id: str,
    scope_revision: int,
    *,
    storage_root: Path,
    match_selection: str = "",
    match_selections: list[str] | None = None,
    estimate_selection: str = "",
) -> dict[str, Any]:
    """No matching, rate calculation, history writes or implicit artifact selection."""
    get_draft(db, actor, draft_id)
    scope = read_revision(db, actor, draft_id, scope_revision)
    selections = (
        match_selections
        if match_selections is not None
        else ([match_selection] if match_selection else [])
    )
    if (
        (match_selection and match_selections is not None)
        or len(selections) > 30
        or len(set(selections)) != len(selections)
        or any(not value for value in selections)
    ):
        raise DraftScopeError("REGISTER_SELECTION_INVALID", 422)
    result: dict[str, Any] = {
        "targets": {},
        "row_targets": {},
        "match_choices": [],
        "estimate_choices": [],
        "match_selection": match_selection,
        "match_selections": selections,
        "estimate_selection": estimate_selection,
        "warnings": [],
        "evidence_refs": [
            dict(ref, status=reference_status(ref, scope["content"]))
            for ref in scope.get("evidence_refs", [])
        ],
        "readiness": hierarchy_review(scope["content"]),
    }
    if has_permission(actor, "technical:read"):
        result["match_choices"] = [
            {
                "value": f"{item.id}:{item.latest_revision}",
                "label": (
                    f"Review {item.id[:8]} / revision {item.latest_revision}"
                    f" / Scope {item.scope_revision}"
                ),
            }
            for item in matches.list_matches(db, actor, draft_id)
        ]
    if has_permission(actor, "estimate:read"):
        result["estimate_choices"] = [
            {
                "value": f"{item.id}:{item.latest_revision}",
                "label": (
                    f"Estimate {item.id[:8]} / revision {item.latest_revision}"
                    f" / Scope {item.scope_revision}"
                ),
            }
            for item in estimates.list_estimates(db, actor, draft_id)
        ]
    selected_matches = []
    legacy_targets: dict[str, list[dict[str, Any]]] = {}
    for match_selection in selections:
        identity, revision = _selection(match_selection)
        selected_match = matches.read_match_revision(db, actor, draft_id, identity, revision)
        selected_matches.append(selected_match)
        if not any(item["value"] == match_selection for item in result["match_choices"]):
            result["match_choices"].append(
                {
                    "value": match_selection,
                    "label": f"Selected historical review {identity[:8]} / revision {revision}",
                }
            )
        stale = matches.match_staleness(
            db, actor, draft_id, identity, revision, storage_root=storage_root
        )
        if selected_match["scope"]["sha256"] != scope["sha256"]:
            stale.append("Selected review uses a different Scope revision.")
        target = selected_match["target"]
        key = (
            ("service:" + target["service_id"])
            if target["service_id"]
            else ("blank_opening:" + target["opening_id"] if target["blank_opening"] else "")
        )
        decisions = {item["candidate_id"]: item["decision"] for item in selected_match["decisions"]}
        labels = {"keep": "kept for review", "reject": "rejected", "unreviewed": "awaiting review"}
        candidates = [
            f"{item['system_id']} / {item['variant_id']} "
            f"({labels[decisions[item['candidate_id']]]})"
            for item in selected_match["candidates"]
        ]
        blockers = sorted(
            {code for item in selected_match["candidates"] for code in item["blockers"]}
        )
        if key:
            row_key = (
                f"opening:{target['opening_id']}:service:{target['service_id']}"
                if target["service_id"]
                else key
            )
            if row_key in result["row_targets"]:
                raise DraftScopeError("REGISTER_REVIEW_TARGET_CONFLICT", 422)
            projection = dict(
                match_selection=match_selection,
                system_opening_id=target["opening_id"],
                system_text="; ".join(candidates) or "No candidates retained",
                system_status="Stale" if stale else "Unapproved candidate review",
                system_warnings=stale + blockers,
                system_url=f"/scopes/{draft_id}/system-matches/{identity}?revision={revision}",
                status="Stale" if stale else "Unapproved",
            )
            result["row_targets"][row_key] = projection
            legacy_targets.setdefault(key, []).append(projection)
        result["warnings"].extend(stale)
    for key, projections in legacy_targets.items():
        if len(projections) == 1:
            result["targets"][key] = projections[0].copy()
    if estimate_selection:
        identity, revision = _selection(estimate_selection)
        estimate = estimates.read_estimate_revision(db, actor, draft_id, identity, revision)
        if not any(item["value"] == estimate_selection for item in result["estimate_choices"]):
            result["estimate_choices"].append(
                {
                    "value": estimate_selection,
                    "label": f"Selected historical estimate {identity[:8]} / revision {revision}",
                }
            )
        stale = estimates.estimate_staleness(
            db, actor, draft_id, identity, revision, storage_root=storage_root
        )
        if estimate["scope"]["sha256"] != scope["sha256"]:
            stale.append("Selected estimate uses a different Scope revision.")
        if selected_matches and (
            estimate["system_match"] is None
            or not any(
                estimate["system_match"]["sha256"] == selected["sha256"]
                for selected in selected_matches
            )
        ):
            stale.append("The selected estimate is not bound to the displayed system review.")
        for line in estimate["lines"]:
            amount = line["subtotal_ex_tax"]
            price = (
                "Omitted"
                if line["status"] == "omitted"
                else "Not priced"
                if amount is None
                else f"{estimate['currency']} {amount} ex tax"
            )
            result["targets"].setdefault(line["recovery_key"], {}).update(
                price_text=price,
                price_status="Stale" if stale else "Saved Draft amount",
                price_warnings=stale,
                rate_method=estimate["provenance"],
                price_url=f"/scopes/{draft_id}/estimates/{identity}?revision={revision}",
            )
        result["warnings"].extend(stale)
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    return result


def _evidence_selection(
    scope: dict[str, Any],
    opening_id: str | None,
    service_id: str | None,
    *,
    defect_id: str | None = None,
) -> dict[str, Any]:
    content = scope["content"]
    if defect_id is not None:
        defect = next((item for item in content["defects"] if item["id"] == defect_id), None)
        if opening_id is not None or service_id is not None or defect is None:
            raise DraftScopeError("REGISTER_EVIDENCE_SELECTION_INVALID", 422)
        linked = any(item["defect_id"] == defect_id for item in content["openings"])
        return {
            "opening_id": None,
            "service_id": None,
            "defect_id": defect_id,
            "opening_label": None,
            "service_label": None,
            "defect_label": defect["label"],
            "opening_ids": [],
            "blank": None,
            "relationship_warnings": []
            if linked
            else [
                "No Opening is linked to this Defect; its physical relationships remain unresolved."
            ],
        }
    opening = next((item for item in content["openings"] if item["id"] == opening_id), None)
    service = next((item for item in content["services"] if item["id"] == service_id), None)
    if (
        (opening_id is None and service_id is None)
        or (opening_id is not None and opening is None)
        or (service_id is not None and service is None)
        or (service is not None and opening_id is None and service["opening_ids"])
        or (
            service is not None
            and opening_id is not None
            and opening_id not in service["opening_ids"]
        )
    ):
        raise DraftScopeError("REGISTER_EVIDENCE_SELECTION_INVALID", 422)
    defect_id = opening["defect_id"] if opening else None
    defect = next((item for item in content["defects"] if item["id"] == defect_id), None)
    readiness = hierarchy_review(content)
    return {
        "opening_id": opening_id,
        "service_id": service_id,
        "defect_id": defect_id,
        "opening_label": opening["label"] if opening else None,
        "service_label": service["label"] if service else None,
        "defect_label": defect["label"] if defect else None,
        "opening_ids": list(service["opening_ids"]) if service else [],
        "blank": opening["blank"] if opening else None,
        "relationship_warnings": list(
            dict.fromkeys(readiness.get(opening_id or "", []) + readiness.get(service_id or "", []))
        ),
    }


def _evidence_role(ref: dict[str, Any], selection: dict[str, Any]) -> str | None:
    kind = ref.get("target_kind")
    if kind in ("service", "opening", "defect") and ref["target_id"] == selection[kind + "_id"]:
        if kind == "defect" and selection["opening_id"] is None and selection["service_id"] is None:
            return "selected_defect"
        return "selected_service" if kind == "service" else kind + "_context"
    return None


def _evidence_metadata(ref: dict[str, Any]) -> dict[str, Any]:
    # Do not expose saved text, mapped values, AI quotes or arbitrary nested source data
    # when current source access or the exact historical binding cannot be verified.
    metadata = {
        key: ref[key]
        for key in (
            "source_id",
            "source_sha256",
            "source_size_bytes",
            "original_filename",
            "document_sha256",
            "scan_sha256",
            "reviewed_by",
            "reviewed_at",
            "method",
            "origin",
            "target_kind",
            "target_id",
            "target_sha256",
        )
    }
    kind = ref.get("source_kind", "pdf")
    metadata["source_kind"] = kind
    if kind == "docx":
        metadata.update(locator=ref["block"]["locator"], text_sha256=ref["block"]["text_sha256"])
    elif kind == "xlsx":
        row = ref["row"]
        metadata.update(
            locator=f"{row['sheet']} / row {row['row']}",
            sheet=row["sheet"],
            sheet_index=row["sheet_index"],
            row=row["row"],
            row_sha256=row["sha256"],
            header_row=row["header_row"],
        )
        for field, cell in row["fields"].items():
            metadata[field + "_mapped_column"] = row["mapping"][field]
            metadata[field + "_cell"] = cell["address"] if cell else None
    else:
        metadata.update(
            locator=ref["locator_key"],
            page_number=ref["page_number"],
            text_sha256=ref["page_text_sha256"],
        )
    for picture in ref.get("images", []):
        identity = picture.get("id", picture.get("occurrence_id"))
        for key, value in picture.items():
            if key in ("id", "occurrence_id"):
                continue
            metadata[f"{identity}_{key}"] = (
                json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
            )
    if "suggestion" in ref:
        for key in (
            "schema",
            "suggestion_id",
            "provider",
            "model",
            "prompt_version",
            "input_sha256",
            "response_sha256",
            "page_image_sha256",
            "generated_at",
            "basis",
        ):
            metadata["suggestion_" + key] = ref["suggestion"][key]
    return metadata


def _evidence_body(ref: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    """Bind the selected saved text/cells and image claims to the verified document."""
    kind = ref.get("source_kind", "pdf")
    text_value, fields, images = None, [], []
    if kind == "docx":
        block = next(
            item for item in document["blocks"] if item["locator"] == ref["block"]["locator"]
        )
        if {key: block[key] for key in ref["block"]} != ref["block"]:
            raise ValueError("Word claim changed")
        pictures = {item["id"]: item for item in document["pictures"]}
        for picture in ref["images"]:
            if pictures.get(picture["id"]) != picture:
                raise ValueError("Word picture changed")
            images.append(
                {"id": picture["id"], "label": f"{picture['id']} at {picture['locator']}"}
            )
        text_value = block["text"]
    elif kind == "xlsx":
        from .draft_scope_xlsx_contract import selected_rows

        row = ref["row"]
        _plan, rows = selected_rows(
            document,
            {
                "sheet_index": row["sheet_index"],
                "header_row": row["header_row"],
                "mapping": row["mapping"],
                "selections": [{"row": row["row"], "kinds": [ref["target_kind"]]}],
            },
        )
        if rows != [row]:
            raise ValueError("Workbook row changed")
        sheet = document["sheets"][row["sheet_index"] - 1]
        pictures = {item["occurrence_id"]: item for item in sheet["images"]}
        for picture in ref["images"]:
            if pictures.get(picture["occurrence_id"]) != picture:
                raise ValueError("Workbook picture changed")
            identity = picture["occurrence_id"]
            images.append({"id": identity, "label": f"{row['sheet']} / {identity}"})
        for name, cell in row["fields"].items():
            fields.append(
                {
                    "label": name.replace("_", " "),
                    "value": cell["value"] if cell else None,
                    "address": cell["address"] if cell else None,
                    "kind": cell["kind"] if cell else None,
                    "mapped": row["mapping"][name] is not None,
                }
            )
    else:
        page = next(item for item in document["pages"] if item["page_number"] == ref["page_number"])
        if any(page[key] != ref[key] for key in ("locator_key", "page_text_sha256")):
            raise ValueError("PDF page changed")
        text_value = page["text"]
        images = [{"id": "page", "label": f"Page {ref['page_number']}"}]
    return {"text": text_value, "fields": fields, "images": images}


def _verified_evidence(
    db: Session,
    actor: User,
    draft_id: str,
    scope: dict[str, Any],
    ref: dict[str, Any],
    settings: Settings,
    cache: dict[tuple[str, str], Any],
) -> dict[str, Any]:
    empty: dict[str, Any] = {"text": None, "fields": [], "images": []}
    if ref["origin"] != "local_retained":
        # Import mappings retain original bytes, but neither their foreign IDs nor their
        # foreign document/scan claims are current local source authority.
        return empty | {"availability": "imported_unverified"}
    kind = ref.get("source_kind", "pdf")
    key = (kind, ref["source_id"])
    try:
        if key not in cache:
            from . import draft_pdf_intake, draft_scope_docx, draft_scope_xlsx

            reader = {
                "pdf": draft_pdf_intake._intake,
                "docx": draft_scope_docx.intake,
                "xlsx": draft_scope_xlsx.intake,
            }[kind]()
            try:
                cache[key] = reader._document(
                    db, actor, draft_id, ref["source_id"], settings.storage_root
                )
            except DraftScopeError as exc:
                cache[key] = exc
        verified = cache[key]
        if isinstance(verified, DraftScopeError):
            raise verified
        source, document, content = verified
        if (
            content.sha256 != ref["source_sha256"]
            or content.size_bytes != ref["source_size_bytes"]
            or source.document_sha256 != ref["document_sha256"]
            or hashlib.sha256(source.scan_json.encode("utf-8")).hexdigest() != ref["scan_sha256"]
        ):
            return empty | {"availability": "source_changed"}
        return _evidence_body(ref, document) | {"availability": "verified"}
    except DraftScopeError as exc:
        if exc.status_code == 403:
            raise
        return empty | {"availability": "unavailable"}
    except (ValueError, KeyError, TypeError, StopIteration):
        return empty | {"availability": "source_changed"}


def _imported_evidence_links(
    db: Session,
    actor: User,
    draft_id: str,
    scope: dict[str, Any],
    refs: dict[int, dict[str, Any]],
) -> dict[int, str]:
    """Locate retained foreign claims, without reading or approving a local source."""
    if not refs:
        return {}
    from .draft_package_materialization import read_import

    try:
        _row, original, mapping = read_import(db, actor, draft_id)
        candidates: dict[int, list[str]] = {index: [] for index in refs}
        for member in mapping.get("evidence", []):
            path = member["path"]
            owner = original
            parts = path.split("!")
            for ancestor in parts[:-1]:
                owner = owner.origins[ancestor]
            # A later raw Scope import can carry the same source ID and bytes but a
            # different review. Require the exact retained ancestor and full claim.
            lineage = {
                key: owner.scope[key]
                for key in (
                    "schema_version",
                    "artifact_id",
                    "project_id",
                    "revision",
                    "created_by",
                    "created_at",
                    "sha256",
                )
            } | {"file_sha256": hashlib.sha256(owner.members["artifacts/scope.json"]).hexdigest()}
            if lineage not in scope.get("import_lineage", []):
                continue
            content = original.resolve(path)
            for index, ref in refs.items():
                kind = ref.get("source_kind", "pdf")
                if (
                    parts[-1] != f"evidence/{ref['source_id']}.{kind}"
                    or member["original_source_id"] != ref["source_id"]
                    or member["sha256"] != ref["source_sha256"]
                    or len(content) != ref["source_size_bytes"]
                    or not any(
                        dict(claim, origin="imported_unverified") == ref
                        for claim in owner.scope.get("evidence_refs", [])
                    )
                ):
                    continue
                candidates[index].append(path)
        return {
            index: f"/scopes/{draft_id}/imported-package#evidence-"
            + hashlib.sha256(paths[0].encode("utf-8")).hexdigest()
            for index, paths in candidates.items()
            if len(paths) == 1
        }
    except (DraftScopeError, ValueError, KeyError, TypeError):
        # Missing/invalid imports and broader package permissions cannot grant a
        # link. The final Draft check still propagates revoked project access.
        return {}


def evidence_context(
    db: Session,
    actor: User,
    draft_id: str,
    scope_revision: int,
    opening_id: str | None,
    service_id: str | None = None,
    *,
    defect_id: str | None = None,
    settings: Settings,
) -> dict[str, Any]:
    """Read one exact register row's source context; never infer relationships or write."""
    with db.no_autoflush:
        if type(scope_revision) is not int or not 1 <= scope_revision <= 2147483647:
            raise DraftScopeError("REGISTER_EVIDENCE_SELECTION_INVALID", 422)
        scope = read_revision(db, actor, draft_id, scope_revision)
        selection = _evidence_selection(scope, opening_id, service_id, defect_id=defect_id)
        refs: list[dict[str, Any]] = []
        imported_refs: dict[int, dict[str, Any]] = {}
        cache: dict[tuple[str, str], Any] = {}
        for index, ref in enumerate(scope.get("evidence_refs", [])):
            role = _evidence_role(ref, selection)
            if role is None:
                continue
            if ref["origin"] == "imported_unverified":
                imported_refs[index] = ref
            refs.append(
                {
                    "index": index,
                    "role": role,
                    "label": reference_label(ref, scope["content"]),
                    "status": reference_status(ref, scope["content"]),
                    "claim_changed": reference_changed(ref, scope["content"]),
                    "metadata": _evidence_metadata(ref),
                    **_verified_evidence(db, actor, draft_id, scope, ref, settings, cache),
                }
            )
        imported_links = _imported_evidence_links(db, actor, draft_id, scope, imported_refs)
        for ref in refs:
            if ref["index"] in imported_links:
                ref["imported_review_url"] = imported_links[ref["index"]]
        get_draft(db, actor, draft_id)
        notices = ["Draft evidence context; no technical or physical approval."]
        if any(ref["role"] in ("opening_context", "defect_context") for ref in refs):
            notices.append(
                "Defect and Opening references are inherited context, not proof of this Service."
            )
        if not refs:
            notices.append(
                "No source references are saved for this row; missing evidence remains unknown."
            )
        return {
            "scope": {key: value for key, value in scope.items() if key != "evidence_refs"},
            "selection": selection,
            "refs": refs,
            "notices": notices,
        }


def evidence_image(
    db: Session,
    actor: User,
    draft_id: str,
    scope_revision: int,
    opening_id: str | None,
    service_id: str | None = None,
    *,
    ref_index: int,
    image_id: str,
    defect_id: str | None = None,
    settings: Settings,
) -> tuple[bytes, str]:
    """Recheck the saved reference before an existing bounded image reader runs."""
    with db.no_autoflush:
        context = evidence_context(
            db,
            actor,
            draft_id,
            scope_revision,
            opening_id,
            service_id,
            defect_id=defect_id,
            settings=settings,
        )
        selected = next((ref for ref in context["refs"] if ref["index"] == ref_index), None)
        if type(ref_index) is not int or selected is None:
            raise DraftScopeError("REGISTER_EVIDENCE_IMAGE_NOT_FOUND", 404)
        if selected["availability"] != "verified":
            raise DraftScopeError("REGISTER_EVIDENCE_SOURCE_UNAVAILABLE", 409)
        if type(image_id) is not str or not any(
            image["id"] == image_id for image in selected["images"]
        ):
            raise DraftScopeError("REGISTER_EVIDENCE_IMAGE_NOT_FOUND", 404)
        from . import draft_pdf_intake, draft_scope_docx, draft_scope_xlsx

        metadata = selected["metadata"]
        source_id = metadata["source_id"]
        if metadata["source_kind"] == "docx":
            value = draft_scope_docx.image_preview(
                db, actor, draft_id, source_id, image_id, settings=settings
            )
        elif metadata["source_kind"] == "xlsx":
            value = draft_scope_xlsx.image_preview(
                db,
                actor,
                draft_id,
                source_id,
                metadata["sheet_index"],
                image_id,
                settings=settings,
            )
        else:
            value = draft_pdf_intake.page_preview(
                db, actor, draft_id, source_id, metadata["page_number"], settings=settings
            )
        final = evidence_context(
            db,
            actor,
            draft_id,
            scope_revision,
            opening_id,
            service_id,
            defect_id=defect_id,
            settings=settings,
        )
        if selected not in final["refs"]:
            raise DraftScopeError("REGISTER_EVIDENCE_SOURCE_UNAVAILABLE", 409)
        return value, "image/png"
