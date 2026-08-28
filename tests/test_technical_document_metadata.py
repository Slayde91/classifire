# ruff: noqa: S106
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from classifire import models, physical_models  # noqa: F401
from classifire.config import get_settings
from classifire.db import Base
from classifire.models import (
    Approval,
    AuditEvent,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalVariant,
    User,
)
from classifire.services.technical_document_metadata import (
    TECHNICAL_CURRENT_STANDARD_REFERENCES,
    TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
    TechnicalDocumentMetadataError,
    normalize_technical_source_registration,
    technical_current_standards_advisory,
    update_technical_document_draft_metadata,
)
from classifire.services.technical_document_review import (
    TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
    TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
    TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
    TechnicalDocumentReviewError,
    approve_technical_document_review,
    latest_technical_document_review,
    submit_technical_document_review,
    technical_document_review_snapshot,
    technical_document_review_snapshot_hash,
)
from classifire.services.technical_governance import (
    GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    TechnicalGovernanceError,
    require_technical_source_binding,
    technical_document_snapshot,
)


@pytest.fixture(autouse=True)
def governed_storage_root(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    monkeypatch.setenv("CLASSIFIRE_STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    try:
        yield get_settings().storage_root
    finally:
        get_settings.cache_clear()


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db: Session, email: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="unused",
        role="technical_reviewer",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _document(
    db: Session,
    *,
    document_id: str,
    policy: str = TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
    document_type: str = "test_report",
    declared_source_role: str = "primary_test",
    evidence_scope: str = "full_source",
    uploaded_by: User | None = None,
    status: str = "draft",
    approved_by: User | None = None,
) -> TechnicalDocument:
    content = f"retained source for {document_id}".encode()
    digest = hashlib.sha256(content).hexdigest()
    source = (
        get_settings().storage_root
        / digest[:2]
        / digest[2:4]
        / f"{digest}.pdf"
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    stored_file = StoredFile(
        original_filename=f"{document_id}.pdf",
        media_type="application/pdf",
        storage_path=str(source),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=uploaded_by.id if uploaded_by else None,
        immutable=True,
    )
    db.add(stored_file)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored_file.id,
        document_type=document_type,
        declared_source_role=declared_source_role,
        manufacturer="Example Manufacturer",
        sponsor_organisation="Example Sponsor",
        title=f"Source {document_id}",
        reference=document_id,
        revision="R1",
        issuing_organisation="Example Laboratory",
        artifact_provenance_status="issuer_copy",
        artifact_provenance_note="Provided by the issuing laboratory.",
        jurisdiction="AU",
        standards=["AS 1530.4"],
        evidence_scope=evidence_scope,
        evidence_limitations="Use only for the reviewed configuration.",
        status=status,
        metadata_json={
            "human_review_required": True,
            "source_review_policy": policy,
            **(
                {
                    "source_registration_schema": (
                        TECHNICAL_SOURCE_REGISTRATION_SCHEMA
                    )
                }
                if policy == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
                else {}
            ),
            "uploaded_by_id": uploaded_by.id if uploaded_by else None,
        },
        reviewed_by_id=approved_by.id if approved_by else None,
        approved_by_id=approved_by.id if approved_by else None,
        approved_at=datetime.now(UTC) if approved_by else None,
    )
    db.add(document)
    db.flush()
    return document


def _review_document(
    db: Session,
    document: TechnicalDocument,
    *,
    requester: User,
    reviewer: User,
) -> Approval:
    approval = submit_technical_document_review(
        db,
        actor=requester,
        document_id=document.id,
        reason="Ready for independent source review.",
    )
    db.flush()
    approve_technical_document_review(
        db,
        actor=reviewer,
        document_id=document.id,
        reason="Source identity, evidence and lineage reviewed.",
    )
    db.flush()
    db.refresh(document)
    db.refresh(approval)
    return approval


def _variant(db: Session, document: TechnicalDocument) -> TechnicalVariant:
    variant = TechnicalVariant(
        variant_id=f"VAR-{document.document_id}",
        system_id=f"SYS-{document.document_id}",
        technical_document_id=document.id,
        source_document_reference=document.document_id,
        source_page="1",
        service_type="pipe",
        service_material="steel",
        frl="-/120/120",
        search_eligibility="EXCLUDE_PENDING_TECHNICAL_REVIEW",
        expert_review_required=True,
        status="draft",
        source_hash=hashlib.sha256(document.document_id.encode()).hexdigest(),
        source_json={"test": True},
    )
    db.add(variant)
    db.flush()
    return variant


def test_current_standards_advisory_is_declaration_only_and_never_compliance():
    advisory = technical_current_standards_advisory(
        ["NCC2022", "AS1530.4:2014"]
    )

    assert advisory.declared_current_references == (
        "NCC 2022",
        "AS 1530.4:2014",
    )
    assert advisory.missing_references == ("AS 4072.1:2005",)
    assert advisory.evidence_attention_required is True
    assert advisory.independent_evidence_review_required is True
    manifest = advisory.manifest()
    assert manifest["basis"] == "declared_standards_metadata_only"
    assert "compliant" not in manifest
    assert "applicable" not in manifest


def test_current_standards_advisory_remains_unverified_when_all_are_declared():
    advisory = technical_current_standards_advisory(
        ["ncc 2022", "AS 1530.4:2014", "AS4072.1:2005"]
    )

    assert advisory.declared_current_references == (
        TECHNICAL_CURRENT_STANDARD_REFERENCES
    )
    assert advisory.missing_references == ()
    assert advisory.evidence_attention_required is False
    assert advisory.independent_evidence_review_required is True
    assert "compliant" not in advisory.manifest()


@pytest.mark.parametrize(
    "standards",
    [
        None,
        "NCC 2022",
        ["NCC 2022 Volume One", "AS 1530.4:2005", 4072],
    ],
)
def test_current_standards_advisory_fails_closed_on_absent_or_inexact_metadata(
    standards: object,
) -> None:
    advisory = technical_current_standards_advisory(standards)

    assert advisory.declared_current_references == ()
    assert advisory.missing_references == TECHNICAL_CURRENT_STANDARD_REFERENCES
    assert advisory.evidence_attention_required is True


def test_registration_normalizes_declared_metadata_and_requires_derivative_note():
    registration = normalize_technical_source_registration(
        document_type="regulatory_information_report",
        declared_source_role=" regulatory_summary ",
        sponsor_organisation=" Sponsor ",
        artifact_provenance_status=" transformed_derivative ",
        artifact_provenance_note=" Converted from an issuer-supplied PDF. ",
        evidence_scope=" summary_only ",
        evidence_limitations=" Refer to the primary reports. ",
    )

    assert registration.model_values() == {
        "declared_source_role": "regulatory_summary",
        "sponsor_organisation": "Sponsor",
        "artifact_provenance_status": "transformed_derivative",
        "artifact_provenance_note": "Converted from an issuer-supplied PDF.",
        "evidence_scope": "summary_only",
        "evidence_limitations": "Refer to the primary reports.",
    }
    assert registration.manifest()["schema"] == "technical-source-registration-v1"

    with pytest.raises(
        TechnicalDocumentMetadataError,
        match="ARTIFACT_PROVENANCE_NOTE_REQUIRED",
    ):
        normalize_technical_source_registration(
            document_type="test_report",
            declared_source_role="primary_test",
            sponsor_organisation=None,
            artifact_provenance_status="transformed_derivative",
            artifact_provenance_note=" ",
            evidence_scope="full_source",
            evidence_limitations=None,
        )


def test_registration_canonicalizes_multiline_newlines_to_lf() -> None:
    registration = normalize_technical_source_registration(
        document_type="regulatory_information_report",
        declared_source_role="regulatory_summary",
        sponsor_organisation=None,
        artifact_provenance_status="transformed_derivative",
        artifact_provenance_note=" First\r\nSecond\rThird\nFourth ",
        evidence_scope="summary_only",
        evidence_limitations=" Limit one\r\nLimit two\rLimit three ",
    )

    assert registration.artifact_provenance_note == (
        "First\nSecond\nThird\nFourth"
    )
    assert registration.evidence_limitations == (
        "Limit one\nLimit two\nLimit three"
    )


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"declared_source_role": "other"}, "SOURCE_ROLE_INVALID"),
        ({"artifact_provenance_status": "other"}, "ARTIFACT_PROVENANCE_INVALID"),
        ({"evidence_scope": "other"}, "EVIDENCE_SCOPE_INVALID"),
        (
            {
                "document_type": "regulatory_information_report",
                "declared_source_role": "assessment",
                "evidence_scope": "summary_only",
            },
            "SOURCE_CLASSIFICATION_INVALID",
        ),
        ({"sponsor_organisation": object()}, "SOURCE_METADATA_FIELD_INVALID"),
    ],
)
def test_registration_rejects_invalid_source_metadata(override, code):
    values = {
        "document_type": "test_report",
        "declared_source_role": "primary_test",
        "sponsor_organisation": None,
        "artifact_provenance_status": "issuer_original",
        "artifact_provenance_note": None,
        "evidence_scope": "full_source",
        "evidence_limitations": None,
    }
    values.update(override)

    with pytest.raises(TechnicalDocumentMetadataError, match=code):
        normalize_technical_source_registration(**values)


def test_draft_metadata_update_is_optimistic_audited_and_does_not_rebind_file(db):
    actor = _user(db, "editor@example.test")
    document = _document(db, document_id="EDIT-001", uploaded_by=actor)
    stored_file = db.get(StoredFile, document.stored_file_id)
    assert stored_file is not None
    original_stored_file_id = document.stored_file_id
    original_stored_file_version = stored_file.record_version
    expected_version = document.record_version
    registration = normalize_technical_source_registration(
        document_type=document.document_type,
        declared_source_role="assessment",
        sponsor_organisation="Updated Sponsor",
        artifact_provenance_status="transformed_derivative",
        artifact_provenance_note="OCR text layer added; retained bytes are unchanged.",
        evidence_scope="bibliographic_only",
        evidence_limitations="Not direct configuration evidence.",
    )

    updated = update_technical_document_draft_metadata(
        db,
        actor=actor,
        document_id=document.id,
        expected_record_version=expected_version,
        registration=registration,
        reason="Correct declared source metadata before review.",
    )
    db.flush()

    assert updated.record_version == expected_version + 1
    assert updated.status == "draft"
    assert updated.stored_file_id == original_stored_file_id
    assert updated.reviewed_by_id is None
    assert updated.approved_by_id is None
    assert updated.approved_at is None
    assert updated.declared_source_role == "assessment"
    assert updated.artifact_provenance_status == "transformed_derivative"
    db.refresh(stored_file)
    assert stored_file.record_version == original_stored_file_version
    audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "update_draft_source_metadata",
            AuditEvent.entity_id == document.id,
        )
    )
    assert audit is not None
    assert audit.previous_value["stored_file_id"] == original_stored_file_id
    assert audit.new_value["stored_file_id"] == original_stored_file_id
    assert audit.new_value["runtime_eligible"] is False

    with pytest.raises(TechnicalDocumentMetadataError, match="SOURCE_METADATA_STALE"):
        update_technical_document_draft_metadata(
            db,
            actor=actor,
            document_id=document.id,
            expected_record_version=expected_version,
            registration=registration,
            reason="Repeat a stale form submission.",
        )

    document.status = "approved"
    db.flush()
    with pytest.raises(
        TechnicalDocumentMetadataError,
        match="SOURCE_DOCUMENT_NOT_EDITABLE",
    ):
        update_technical_document_draft_metadata(
            db,
            actor=actor,
            document_id=document.id,
            expected_record_version=document.record_version,
            registration=registration,
            reason="Attempt an edit after approval.",
        )


def test_rejected_legacy_source_can_register_v2_metadata_before_resubmission(db):
    actor = _user(db, "rejected-editor@example.test")
    document = _document(
        db,
        document_id="LEGACY-REJECTED-EDIT",
        policy=TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
        uploaded_by=actor,
        status="rejected",
    )
    registration = normalize_technical_source_registration(
        document_type=document.document_type,
        declared_source_role="primary_test",
        sponsor_organisation=None,
        artifact_provenance_status="issuer_copy",
        artifact_provenance_note=None,
        evidence_scope="full_source",
        evidence_limitations=None,
    )

    update_technical_document_draft_metadata(
        db,
        actor=actor,
        document_id=document.id,
        expected_record_version=document.record_version,
        registration=registration,
        reason="Register the rejected legacy source before resubmission.",
    )
    db.flush()
    db.refresh(document)

    assert document.status == "rejected"
    assert document.metadata_json["source_review_policy"] == (
        TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
    )
    approval = submit_technical_document_review(
        db,
        actor=actor,
        document_id=document.id,
        reason="Resubmit after correcting the source registration.",
    )
    db.flush()
    db.refresh(document)
    assert document.status == "in_review"
    assert approval.status == "pending"


def test_legacy_draft_metadata_correction_upgrades_review_policy_without_rewriting_history(db):
    actor = _user(db, "legacy-editor@example.test")
    document = _document(
        db,
        document_id="LEGACY-DRAFT-EDIT",
        policy=TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
        uploaded_by=actor,
    )
    document.metadata_json["legacy_marker"] = "preserved"
    db.flush()
    registration = normalize_technical_source_registration(
        document_type=document.document_type,
        declared_source_role="assessment",
        sponsor_organisation="Updated Sponsor",
        artifact_provenance_status="issuer_copy",
        artifact_provenance_note="Retained issuer-provided copy.",
        evidence_scope="full_source",
        evidence_limitations="Configuration review remains required.",
    )

    update_technical_document_draft_metadata(
        db,
        actor=actor,
        document_id=document.id,
        expected_record_version=document.record_version,
        registration=registration,
        reason="Register legacy Draft metadata under the current review contract.",
    )
    db.flush()
    db.refresh(document)

    assert document.metadata_json["source_review_policy"] == (
        TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
    )
    assert document.metadata_json["source_registration_schema"] == (
        "technical-source-registration-v1"
    )
    assert document.metadata_json["human_review_required"] is True
    assert document.metadata_json["legacy_marker"] == "preserved"
    snapshot = technical_document_review_snapshot(db, document.id)
    assert snapshot["policy"] == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
    assert snapshot["document"]["declared_source_role"] == "assessment"
    assert snapshot["document"]["artifact_provenance_status"] == "issuer_copy"
    assert snapshot["document"]["evidence_scope"] == "full_source"


def test_v1_review_snapshot_and_hash_keep_the_exact_legacy_document_shape(db):
    uploader = _user(db, "legacy-uploader@example.test")
    document = _document(
        db,
        document_id="LEGACY-V1",
        policy=TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
        uploaded_by=uploader,
    )
    stored_file = db.get(StoredFile, document.stored_file_id)
    assert stored_file is not None

    expected = {
        "policy": TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
        "document": {
            "id": document.id,
            "document_id": document.document_id,
            "stored_file_id": document.stored_file_id,
            "document_type": document.document_type,
            "manufacturer": document.manufacturer,
            "title": document.title,
            "reference": document.reference,
            "revision": document.revision,
            "issuing_organisation": document.issuing_organisation,
            "publication_date": None,
            "review_date": None,
            "expiry_date": None,
            "jurisdiction": document.jurisdiction,
            "standards": document.standards,
            "metadata_json": document.metadata_json,
            "supersedes_document_id": None,
        },
        "stored_file": {
            "id": stored_file.id,
            "original_filename": stored_file.original_filename,
            "media_type": stored_file.media_type,
            "sha256": stored_file.sha256,
            "size_bytes": stored_file.size_bytes,
            "suffix": ".pdf",
            "purpose": stored_file.purpose,
            "malware_scan_status": stored_file.malware_scan_status,
            "immutable": stored_file.immutable,
        },
        "outgoing_relationships": [],
    }

    assert technical_document_review_snapshot(db, document.id) == expected
    expected_hash = hashlib.sha256(
        json.dumps(
            expected,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert technical_document_review_snapshot_hash(db, document.id) == expected_hash
    release_snapshot = technical_document_snapshot(document)
    assert "declared_source_role" not in release_snapshot
    assert "evidence_scope" not in release_snapshot


def test_v2_snapshot_binds_declared_metadata_and_reports_its_policy(db):
    uploader = _user(db, "v2-uploader@example.test")
    document = _document(db, document_id="SOURCE-V2", uploaded_by=uploader)

    snapshot = technical_document_review_snapshot(db, document.id)

    assert snapshot["policy"] == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
    assert snapshot["document"]["declared_source_role"] == "primary_test"
    assert snapshot["document"]["artifact_provenance_status"] == "issuer_copy"
    assert snapshot["document"]["evidence_scope"] == "full_source"
    assert technical_document_snapshot(document)["evidence_limitations"] == (
        "Use only for the reviewed configuration."
    )


def test_legacy_v1_draft_cannot_be_newly_submitted_without_v2_registration(db):
    requester = _user(db, "legacy-submit@example.test")
    document = _document(
        db,
        document_id="LEGACY-V1-DRAFT",
        policy=TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
        uploaded_by=requester,
    )

    with pytest.raises(
        TechnicalDocumentReviewError,
        match="SOURCE_DOCUMENT_REGISTRATION_REQUIRED",
    ):
        submit_technical_document_review(
            db,
            actor=requester,
            document_id=document.id,
            reason="Attempt a new review under the legacy contract.",
        )

    db.refresh(document)
    assert document.status == "draft"
    assert latest_technical_document_review(db, document.id) is None


def test_pending_review_cannot_be_approved_after_registration_policy_downgrade(db):
    requester = _user(db, "policy-requester@example.test")
    reviewer = _user(db, "policy-reviewer@example.test")
    document = _document(db, document_id="POLICY-DOWNGRADE", uploaded_by=requester)
    approval = submit_technical_document_review(
        db,
        actor=requester,
        document_id=document.id,
        reason="Submit a complete v2 registration.",
    )
    db.flush()
    document.metadata_json = {
        **document.metadata_json,
        "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
    }
    db.flush()

    with pytest.raises(
        TechnicalDocumentReviewError,
        match="SOURCE_DOCUMENT_REGISTRATION_REQUIRED",
    ):
        approve_technical_document_review(
            db,
            actor=reviewer,
            document_id=document.id,
            reason="Do not approve a downgraded registration.",
        )

    db.refresh(document)
    db.refresh(approval)
    assert document.status == "in_review"
    assert approval.status == "pending"


def test_bibliographic_source_can_be_reviewed_but_cannot_bind_a_variant(db):
    requester = _user(db, "bibliographic-uploader@example.test")
    reviewer = _user(db, "bibliographic-reviewer@example.test")
    document = _document(
        db,
        document_id="BIBLIOGRAPHIC-ONLY",
        evidence_scope="bibliographic_only",
        uploaded_by=requester,
    )
    _review_document(db, document, requester=requester, reviewer=reviewer)
    variant = _variant(db, document)

    with pytest.raises(
        TechnicalGovernanceError,
        match="bibliographic_source_not_runtime_eligible",
    ):
        require_technical_source_binding(
            db,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        )


@pytest.mark.parametrize(
    "declared_source_role",
    [
        "administrative_notice",
        "manufacturer_information",
        "supporting_reference",
    ],
)
def test_v2_runtime_source_roles_are_fail_closed(
    db,
    declared_source_role,
):
    requester = _user(db, f"{declared_source_role}-uploader@example.test")
    reviewer = _user(db, f"{declared_source_role}-reviewer@example.test")
    document = _document(
        db,
        document_id=f"ROLE-{declared_source_role}",
        declared_source_role=declared_source_role,
        uploaded_by=requester,
    )
    _review_document(db, document, requester=requester, reviewer=reviewer)
    variant = _variant(db, document)

    with pytest.raises(
        TechnicalGovernanceError,
        match="source_role_not_runtime_eligible",
    ):
        require_technical_source_binding(
            db,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        )


def test_summary_review_rejects_a_legacy_v1_target_without_v2_full_source_scope(db):
    requester = _user(db, "legacy-target-uploader@example.test")
    reviewer = _user(db, "legacy-target-reviewer@example.test")
    target = _document(
        db,
        document_id="LEGACY-V1-TARGET",
        policy=TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
        uploaded_by=requester,
        status="approved",
        approved_by=reviewer,
    )
    summary = _document(
        db,
        document_id="SUMMARY-WITH-LEGACY-TARGET",
        document_type="regulatory_information_report",
        declared_source_role="regulatory_summary",
        evidence_scope="summary_only",
        uploaded_by=requester,
    )
    db.add(
        TechnicalDocumentRelationship(
            document_id=summary.id,
            related_document_id=target.id,
            relationship_type="summary_of",
            reason="Attempt to rely on an unclassified legacy review.",
            created_by_id=requester.id,
        )
    )
    db.flush()

    with pytest.raises(
        TechnicalDocumentReviewError,
        match="SUMMARY_SOURCE_TARGET_INVALID",
    ):
        submit_technical_document_review(
            db,
            actor=requester,
            document_id=summary.id,
            reason="Attempt to submit with a legacy target.",
        )


def test_summary_source_cannot_enter_review_or_binding_without_summary_of(db):
    requester = _user(db, "summary-uploader@example.test")
    reviewer = _user(db, "summary-reviewer@example.test")
    document = _document(
        db,
        document_id="RIR-UNLINKED",
        document_type="regulatory_information_report",
        declared_source_role="regulatory_summary",
        evidence_scope="summary_only",
        uploaded_by=requester,
    )

    with pytest.raises(
        TechnicalDocumentReviewError,
        match="SUMMARY_SOURCE_RELATIONSHIP_REQUIRED",
    ):
        submit_technical_document_review(
            db,
            actor=requester,
            document_id=document.id,
            reason="Submit unlinked summary.",
        )
    db.refresh(document)
    assert document.status == "draft"
    assert (
        db.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document.id,
                Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
            )
        )
        is None
    )

    document.status = "approved"
    document.reviewed_by_id = reviewer.id
    document.approved_by_id = reviewer.id
    document.approved_at = datetime.now(UTC)
    variant = _variant(db, document)
    db.flush()
    with pytest.raises(
        TechnicalGovernanceError,
        match="summary_source_not_runtime_eligible",
    ):
        require_technical_source_binding(
            db,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        )


def test_v2_summary_can_be_reviewed_but_cannot_directly_bind_a_variant(db):
    requester = _user(db, "mixed-uploader@example.test")
    reviewer = _user(db, "mixed-reviewer@example.test")
    target = _document(
        db,
        document_id="PRIMARY-V2",
        policy=TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
        uploaded_by=requester,
    )
    _review_document(db, target, requester=requester, reviewer=reviewer)
    summary = _document(
        db,
        document_id="RIR-V2",
        document_type="regulatory_information_report",
        declared_source_role="regulatory_summary",
        evidence_scope="summary_only",
        uploaded_by=requester,
    )
    relationship = TechnicalDocumentRelationship(
        document_id=summary.id,
        related_document_id=target.id,
        relationship_type="summary_of",
        reason="The RIR summarises the independently reviewed primary report.",
        created_by_id=requester.id,
    )
    db.add(relationship)
    db.flush()

    _review_document(db, summary, requester=requester, reviewer=reviewer)
    snapshot = technical_document_review_snapshot(db, summary.id)
    edge = snapshot["outgoing_relationships"][0]

    assert snapshot["policy"] == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
    assert edge["relationship_type"] == "summary_of"
    assert edge["target_review_receipt"]["policy"] == (
        TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
    )
    assert edge["target_document"]["declared_source_role"] == "primary_test"

    variant = _variant(db, summary)
    with pytest.raises(
        TechnicalGovernanceError,
        match="summary_source_not_runtime_eligible",
    ):
        require_technical_source_binding(
            db,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        )


@pytest.mark.parametrize(
    ("target_expiry", "relationship_effective", "expected"),
    [
        (date.today() - timedelta(days=1), None, "source_graph_document_expired"),
        (None, date.today() + timedelta(days=30), "source_relationship_not_yet_effective"),
    ],
)
def test_v3_binding_rechecks_transitive_source_dates(
    db,
    target_expiry,
    relationship_effective,
    expected,
):
    requester = _user(db, f"{expected}-uploader@example.test")
    reviewer = _user(db, f"{expected}-reviewer@example.test")
    target = _document(
        db,
        document_id=f"{expected}-TARGET",
        uploaded_by=requester,
    )
    target.expiry_date = target_expiry
    db.flush()
    _review_document(db, target, requester=requester, reviewer=reviewer)
    source = _document(
        db,
        document_id=f"{expected}-SOURCE",
        declared_source_role="assessment",
        uploaded_by=requester,
    )
    db.add(
        TechnicalDocumentRelationship(
            document_id=source.id,
            related_document_id=target.id,
            relationship_type="assessment_of",
            reason="Assessment source dependency.",
            effective_date=relationship_effective,
            created_by_id=requester.id,
        )
    )
    db.flush()
    _review_document(db, source, requester=requester, reviewer=reviewer)
    variant = _variant(db, source)

    with pytest.raises(TechnicalGovernanceError, match=expected):
        require_technical_source_binding(
            db,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        )
