from __future__ import annotations

import re
import secrets
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DDL,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_auth_generation() -> str:
    return secrets.token_hex(32)


class RecordMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False
    )
    record_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class User(RecordMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="estimator", index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auth_generation: Mapped[str] = mapped_column(
        String(64), default=new_auth_generation, nullable=False
    )


class HumanSession(RecordMixin, Base):
    __tablename__ = "human_sessions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_hint: Mapped[str] = mapped_column(String(12), nullable=False)
    auth_generation: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)


class AuditEvent(RecordMixin, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
    actor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AgentServicePrincipal(RecordMixin, Base):
    """A least-privilege, non-human service identity for a CLASSIFIRE agent.

    Plaintext credentials are never stored.  The server-side scope map remains
    authoritative; the persisted scope list provides an auditable second gate.
    """

    __tablename__ = "agent_service_principals"

    agent_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LibraryRelease(RecordMixin, Base):
    __tablename__ = "library_releases"
    __table_args__ = (UniqueConstraint("library_type", "version", name="uq_library_release_type_version"),)

    library_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    release_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    source_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))


class MarkupProfile(RecordMixin, Base):
    __tablename__ = "markup_profiles"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(100), index=True)
    product_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Product(RecordMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("sku", "revision", name="uq_product_sku_revision"),)

    sku: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    item_type: Mapped[str] = mapped_column(String(30), default="product", index=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(150), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    supplier: Mapped[str | None] = mapped_column(String(200), index=True)
    unit: Mapped[str] = mapped_column(String(30), default="each", nullable=False)
    pack_size: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"), nullable=False)
    minimum_order_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("1"), nullable=False
    )
    base_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    tax_treatment: Mapped[str] = mapped_column(String(30), default="exclusive", nullable=False)
    waste_factor: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"), nullable=False)
    default_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    regional_pricing: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_reference: Mapped[str | None] = mapped_column(Text)
    supporting_attachment_id: Mapped[str | None] = mapped_column(String(36))
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))


class LabourComponent(RecordMixin, Base):
    __tablename__ = "labour_components"
    __table_args__ = (UniqueConstraint("code", "revision", name="uq_labour_code_revision"),)

    code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    trade_or_grade: Mapped[str | None] = mapped_column(String(150), index=True)
    category: Mapped[str | None] = mapped_column(String(150), index=True)
    unit: Mapped[str] = mapped_column(String(30), default="person_hour", nullable=False)
    base_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    default_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    crew_size: Mapped[Decimal] = mapped_column(Numeric(9, 3), default=Decimal("1"), nullable=False)
    default_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    productivity_source: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("labour_components.id"))


class PricingLibraryRecord(RecordMixin, Base):
    __tablename__ = "pricing_library_records"

    pkb_entry_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entry_version: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(100), default="each", nullable=False)
    rate_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    direct_labour_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    direct_material_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    material_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    tax_basis: Mapped[str] = mapped_column(String(50), default="GST Exclusive", nullable=False)
    service_type: Mapped[str | None] = mapped_column(String(200), index=True)
    service_class: Mapped[str | None] = mapped_column(String(200), index=True)
    service_material: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate_plane: Mapped[str | None] = mapped_column(String(100), index=True)
    orientation: Mapped[str | None] = mapped_column(String(100), index=True)
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    repair_family: Mapped[str | None] = mapped_column(String(300), index=True)
    rate_inclusions: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rate_exclusions: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    applicability: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    commercial_confidence: Mapped[str | None] = mapped_column(String(100))
    technical_status: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("pricing_library_records.id"))

    __table_args__ = (
        UniqueConstraint("pkb_entry_id", "entry_version", "release_id", name="uq_pkb_entry_release"),
        Index("ix_pricing_search", "service_type", "service_material", "substrate", "frl"),
    )


class StoredFile(RecordMixin, Base):
    __tablename__ = "stored_files"

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(200))
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    malware_scan_status: Mapped[str] = mapped_column(String(30), default="not_configured")
    uploaded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


_SHA256_PATTERN = re.compile(r"^[0-9A-Fa-f]{64}$")
_CLAMAV_CTIME_PATTERN = re.compile(
    r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"( [1-9]|[12][0-9]|3[01]) "
    r"([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9]) ([0-9]{4})$"
)
_CLAMAV_MONTHS = dict(
    zip(
        "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
        range(1, 13),
        strict=True,
    )
)
_CLAMAV_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _sql_sha256_check(column_name: str) -> str:
    stripped = f"lower({column_name})"
    for character in "0123456789abcdef":
        stripped = f"replace({stripped}, '{character}', '')"
    return f"length({column_name}) = 64 AND length({stripped}) = 0"


def _sql_clamav_timestamp_shape(column_name: str) -> str:
    return (
        f"length({column_name}) = 24 "
        f"AND substr({column_name}, 1, 3) "
        "IN ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat') "
        f"AND substr({column_name}, 4, 1) = ' ' "
        f"AND substr({column_name}, 5, 3) "
        "IN ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', "
        "'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec') "
        f"AND substr({column_name}, 8, 1) = ' ' "
        f"AND substr({column_name}, 11, 1) = ' ' "
        f"AND substr({column_name}, 14, 1) = ':' "
        f"AND substr({column_name}, 17, 1) = ':' "
        f"AND substr({column_name}, 20, 1) = ' '"
    )


class MalwareScanAttestation(Base):
    """Append-only, content-bound evidence of one malware scan verdict."""

    __tablename__ = "malware_scan_attestations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, nullable=False
    )
    stored_file_id: Mapped[str] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    scan_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_receipt_sha256: Mapped[str | None] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    scan_source: Mapped[str] = mapped_column(String(40), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    scanner_engine: Mapped[str] = mapped_column(String(50), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    definition_timestamp: Mapped[str] = mapped_column(String(24), nullable=False)
    protocol: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_status: Mapped[str] = mapped_column(String(20), nullable=False)
    post_scan_engine_version: Mapped[str | None] = mapped_column(String(64))
    post_scan_definition_version: Mapped[int | None] = mapped_column(BigInteger)
    post_scan_definition_timestamp: Mapped[str | None] = mapped_column(String(24))
    receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "scan_sequence > 0",
            name="ck_malware_scan_attestation_positive_sequence",
        ),
        CheckConstraint(
            "(scan_sequence = 1 AND previous_receipt_sha256 IS NULL) "
            "OR (scan_sequence > 1 AND previous_receipt_sha256 IS NOT NULL)",
            name="ck_malware_scan_attestation_previous_receipt",
        ),
        CheckConstraint(
            "previous_receipt_sha256 IS NULL OR "
            f"({_sql_sha256_check('previous_receipt_sha256')})",
            name="ck_malware_scan_attestation_previous_receipt_sha256",
        ),
        CheckConstraint(
            "verdict IN ('clean', 'infected')",
            name="ck_malware_scan_attestation_verdict",
        ),
        CheckConstraint(
            "scanner_engine = 'clamav' "
            "AND protocol = 'clamd-idsession-instream-v1'",
            name="ck_malware_scan_attestation_scanner_contract",
        ),
        CheckConstraint(
            "length(engine_version) BETWEEN 1 AND 64 "
            "AND (post_scan_engine_version IS NULL "
            "OR length(post_scan_engine_version) BETWEEN 1 AND 64)",
            name="ck_malware_scan_attestation_engine_version_length",
        ),
        CheckConstraint(
            "scan_source IN ('upload', 'linked_image_retention', 'governed_rescan')",
            name="ck_malware_scan_attestation_scan_source",
        ),
        CheckConstraint(
            "content_size_bytes >= 0",
            name="ck_malware_scan_attestation_nonnegative_size",
        ),
        CheckConstraint(
            "definition_version BETWEEN 1 AND 4294967295",
            name="ck_malware_scan_attestation_positive_definition_version",
        ),
        CheckConstraint(
            "post_scan_definition_version IS NULL OR "
            "post_scan_definition_version BETWEEN 1 AND 4294967295",
            name="ck_malware_scan_attestation_post_definition_version",
        ),
        CheckConstraint(
            "metadata_status IN ('stable', 'changed', 'unavailable')",
            name="ck_malware_scan_attestation_metadata_status",
        ),
        CheckConstraint(
            "(metadata_status = 'stable' "
            "AND post_scan_engine_version IS NOT NULL "
            "AND post_scan_definition_version IS NOT NULL "
            "AND post_scan_definition_timestamp IS NOT NULL "
            "AND post_scan_engine_version = engine_version "
            "AND post_scan_definition_version = definition_version "
            "AND post_scan_definition_timestamp = definition_timestamp) "
            "OR (metadata_status = 'changed' AND verdict = 'infected' "
            "AND post_scan_engine_version IS NOT NULL "
            "AND post_scan_definition_version IS NOT NULL "
            "AND post_scan_definition_timestamp IS NOT NULL "
            "AND (post_scan_engine_version != engine_version "
            "OR post_scan_definition_version != definition_version "
            "OR post_scan_definition_timestamp != definition_timestamp)) "
            "OR (metadata_status = 'unavailable' AND verdict = 'infected' "
            "AND post_scan_engine_version IS NULL "
            "AND post_scan_definition_version IS NULL "
            "AND post_scan_definition_timestamp IS NULL)",
            name="ck_malware_scan_attestation_metadata_consistency",
        ),
        CheckConstraint(
            _sql_sha256_check("content_sha256"),
            name="ck_malware_scan_attestation_content_sha256",
        ),
        CheckConstraint(
            _sql_sha256_check("receipt_sha256"),
            name="ck_malware_scan_attestation_receipt_sha256",
        ),
        CheckConstraint(
            _sql_clamav_timestamp_shape("definition_timestamp"),
            name="ck_malware_scan_attestation_definition_timestamp_shape",
        ),
        CheckConstraint(
            "post_scan_definition_timestamp IS NULL OR "
            f"({_sql_clamav_timestamp_shape('post_scan_definition_timestamp')})",
            name="ck_malware_scan_attestation_post_definition_timestamp_shape",
        ),
        UniqueConstraint(
            "stored_file_id",
            "scan_sequence",
            name="uq_malware_scan_attestation_file_sequence",
        ),
        UniqueConstraint(
            "receipt_sha256",
            name="uq_malware_scan_attestation_receipt_sha256",
        ),
    )

    @validates("content_sha256", "receipt_sha256")
    def _validate_sha256(self, field_name: str, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError(f"{field_name} must be exactly 64 hexadecimal characters")
        return value

    @validates("previous_receipt_sha256")
    def _validate_previous_receipt_sha256(
        self, _field_name: str, value: str | None
    ) -> str | None:
        if value is not None and not _SHA256_PATTERN.fullmatch(value):
            raise ValueError(
                "previous_receipt_sha256 must be null or exactly 64 hexadecimal characters"
            )
        return value

    @validates("definition_timestamp")
    def _validate_definition_timestamp(self, _field_name: str, value: str) -> str:
        match = _CLAMAV_CTIME_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError("definition_timestamp must be an exact ClamAV ctime value")
        weekday, month, day, hour, minute, second, year = match.groups()
        parsed = datetime(
            int(year),
            _CLAMAV_MONTHS[month],
            int(day),
            int(hour),
            int(minute),
            int(second),
        )
        if _CLAMAV_WEEKDAYS[parsed.weekday()] != weekday:
            raise ValueError("definition_timestamp weekday does not match its calendar date")
        return value

    @validates("post_scan_definition_timestamp")
    def _validate_post_scan_definition_timestamp(
        self, _field_name: str, value: str | None
    ) -> str | None:
        if value is None:
            return None
        return self._validate_definition_timestamp(_field_name, value)


@event.listens_for(MalwareScanAttestation, "before_update")
def _reject_malware_scan_attestation_update(
    _mapper: Any, _connection: Any, _target: MalwareScanAttestation
) -> None:
    raise RuntimeError("Malware scan attestations are append-only and cannot be updated")


@event.listens_for(MalwareScanAttestation, "before_delete")
def _reject_malware_scan_attestation_delete(
    _mapper: Any, _connection: Any, _target: MalwareScanAttestation
) -> None:
    raise RuntimeError("Malware scan attestations are append-only and cannot be deleted")


event.listen(
    MalwareScanAttestation.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER trg_malware_scan_attestations_no_update "
        "BEFORE UPDATE ON malware_scan_attestations "
        "BEGIN SELECT RAISE(ABORT, "
        "'Malware scan attestations are append-only and cannot be updated'); END"
    ).execute_if(dialect="sqlite"),
)
event.listen(
    MalwareScanAttestation.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER trg_malware_scan_attestations_no_delete "
        "BEFORE DELETE ON malware_scan_attestations "
        "BEGIN SELECT RAISE(ABORT, "
        "'Malware scan attestations are append-only and cannot be deleted'); END"
    ).execute_if(dialect="sqlite"),
)
event.listen(
    MalwareScanAttestation.__table__,
    "after_create",
    DDL(
        "CREATE OR REPLACE FUNCTION "
        "classifire_reject_malware_scan_attestation_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION "
        "'Malware scan attestations are append-only and cannot be mutated' "
        "USING ERRCODE = '55000'; END; $$"
    ).execute_if(dialect="postgresql"),
)
event.listen(
    MalwareScanAttestation.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER trg_malware_scan_attestations_no_truncate "
        "BEFORE TRUNCATE ON malware_scan_attestations "
        "FOR EACH STATEMENT EXECUTE FUNCTION "
        "classifire_reject_malware_scan_attestation_mutation()"
    ).execute_if(dialect="postgresql"),
)
event.listen(
    MalwareScanAttestation.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER trg_malware_scan_attestations_no_mutation "
        "BEFORE UPDATE OR DELETE ON malware_scan_attestations "
        "FOR EACH ROW EXECUTE FUNCTION "
        "classifire_reject_malware_scan_attestation_mutation()"
    ).execute_if(dialect="postgresql"),
)


class TechnicalDocument(RecordMixin, Base):
    __tablename__ = "technical_documents"

    document_id: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    stored_file_id: Mapped[str] = mapped_column(ForeignKey("stored_files.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(300), index=True)
    revision: Mapped[str | None] = mapped_column(String(100))
    issuing_organisation: Mapped[str | None] = mapped_column(String(300))
    publication_date: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    jurisdiction: Mapped[str | None] = mapped_column(String(200), index=True)
    standards: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    extraction_status: Mapped[str] = mapped_column(String(50), default="not_started")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    supersedes_document_id: Mapped[str | None] = mapped_column(ForeignKey("technical_documents.id"))
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TechnicalVariant(RecordMixin, Base):
    __tablename__ = "technical_variants"

    variant_id: Mapped[str] = mapped_column(String(300), unique=True, index=True, nullable=False)
    system_id: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    technical_document_id: Mapped[str | None] = mapped_column(ForeignKey("technical_documents.id"))
    source_document_reference: Mapped[str | None] = mapped_column(String(300), index=True)
    source_page: Mapped[str | None] = mapped_column(String(100))
    source_table: Mapped[str | None] = mapped_column(String(300))
    source_figure: Mapped[str | None] = mapped_column(String(300))
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    product_family: Mapped[str | None] = mapped_column(String(300), index=True)
    service_type: Mapped[str | None] = mapped_column(String(300), index=True)
    service_material: Mapped[str | None] = mapped_column(String(300), index=True)
    minimum_service_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    maximum_service_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    permitted_service_quantity: Mapped[str | None] = mapped_column(String(100))
    insulation_type: Mapped[str | None] = mapped_column(Text)
    insulation_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    substrate_type: Mapped[str | None] = mapped_column(Text, index=True)
    minimum_substrate_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    maximum_substrate_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    orientation: Mapped[str | None] = mapped_column(Text, index=True)
    installation_face: Mapped[str | None] = mapped_column(Text)
    opening_type: Mapped[str | None] = mapped_column(Text, index=True)
    opening_dimensions: Mapped[str | None] = mapped_column(Text)
    annular_gap_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    annular_gap_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    service_spacing_rules: Mapped[str | None] = mapped_column(Text)
    edge_distance_rules: Mapped[str | None] = mapped_column(Text)
    support_rules: Mapped[str | None] = mapped_column(Text)
    fixing_rules: Mapped[str | None] = mapped_column(Text)
    component_requirements: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    labour_requirements: Mapped[list[str] | None] = mapped_column(JSON)
    hard_exclusions: Mapped[str | None] = mapped_column(Text)
    dependencies: Mapped[str | None] = mapped_column(Text)
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(200), index=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    confidence_cap: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    search_eligibility: Mapped[str | None] = mapped_column(String(100), index=True)
    expert_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("technical_variants.id"))

    __table_args__ = (
        Index("ix_technical_search", "service_type", "service_material", "frl", "status"),
    )


class EstimatingRule(RecordMixin, Base):
    __tablename__ = "estimating_rules"
    __table_args__ = (UniqueConstraint("rule_code", "version", name="uq_rule_code_version"),)

    rule_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    actions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), default="warning", index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(200), index=True)
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_page: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    conflict_resolution: Mapped[str] = mapped_column(String(100), default="higher_priority_wins")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    test_cases: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("estimating_rules.id"))


class ChangeProposal(RecordMixin, Base):
    __tablename__ = "change_proposals"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True)
    proposal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    proposed_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="user", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    submitted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_notes: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Customer(RecordMixin, Base):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    tax_identifier: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    billing_address: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)

    contacts: Mapped[list[Contact]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    projects: Mapped[list[Project]] = relationship(back_populates="customer")


class Contact(RecordMixin, Base):
    __tablename__ = "contacts"

    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class Project(RecordMixin, Base):
    __tablename__ = "projects"

    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), index=True)
    reference: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    site_address: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str] = mapped_column(String(200), default="NSW/ACT, Australia")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    product_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    notes: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship(back_populates="projects")
    estimates: Mapped[list[Estimate]] = relationship(back_populates="project")


class Estimate(RecordMixin, Base):
    __tablename__ = "estimates"
    __table_args__ = (UniqueConstraint("project_id", "revision", name="uq_project_estimate_revision"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reference: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), default="AUD")
    tax_name: Mapped[str] = mapped_column(String(30), default="GST")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0.10"))
    product_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    assumptions: Mapped[list[str] | None] = mapped_column(JSON)
    exclusions: Mapped[list[str] | None] = mapped_column(JSON)
    qualifications: Mapped[list[str] | None] = mapped_column(JSON)
    pricing_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    technical_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    rules_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    products_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    labour_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    markups_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    formula_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    brand_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    subtotal_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_incl_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    project: Mapped[Project] = relationship(back_populates="estimates")
    openings: Mapped[list[Opening]] = relationship(
        back_populates="estimate", cascade="all, delete-orphan", order_by="Opening.created_at"
    )
    lines: Mapped[list[EstimateLine]] = relationship(
        back_populates="estimate", cascade="all, delete-orphan", order_by="EstimateLine.created_at"
    )


class Opening(RecordMixin, Base):
    __tablename__ = "openings"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    defect_id: Mapped[str | None] = mapped_column(String(100), index=True)
    canonical_defect_id: Mapped[str | None] = mapped_column(ForeignKey("defects.id"), index=True)
    opening_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    substrate_type: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate_plane: Mapped[str | None] = mapped_column(String(50), index=True)
    substrate_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    orientation: Mapped[str | None] = mapped_column(String(100), index=True)
    opening_type: Mapped[str | None] = mapped_column(String(100))
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    physical_model_status: Mapped[str] = mapped_column(String(30), default="draft")
    technical_status: Mapped[str] = mapped_column(String(50), default="not_assessed")
    selected_technical_variant_id: Mapped[str | None] = mapped_column(ForeignKey("technical_variants.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    estimate: Mapped[Estimate] = relationship(back_populates="openings")
    services: Mapped[list[Service]] = relationship(
        back_populates="opening", cascade="all, delete-orphan", order_by="Service.created_at"
    )

    __table_args__ = (UniqueConstraint("estimate_id", "opening_code", name="uq_estimate_opening_code"),)


class Service(RecordMixin, Base):
    __tablename__ = "services"

    opening_id: Mapped[str] = mapped_column(ForeignKey("openings.id"), index=True, nullable=False)
    primary_opening_legacy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    service_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    service_type: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    material: Mapped[str | None] = mapped_column(String(200), index=True)
    nominal_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    outside_diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    insulation_type: Mapped[str | None] = mapped_column(String(200))
    insulation_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1"))
    centre_x_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    centre_y_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    evidence_status: Mapped[str] = mapped_column(String(30), default="provisional")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    notes: Mapped[str | None] = mapped_column(Text)

    opening: Mapped[Opening] = relationship(back_populates="services")

    __table_args__ = (UniqueConstraint("opening_id", "service_code", name="uq_opening_service_code"),)


class EstimateLine(RecordMixin, Base):
    __tablename__ = "estimate_lines"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    component_reference: Mapped[str | None] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"))
    unit: Mapped[str] = mapped_column(String(50), default="each")
    base_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    waste_factor: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"))
    markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    applied_markup: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"))
    markup_source: Mapped[str] = mapped_column(String(100), default="global_default")
    unit_sell: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    subtotal_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_incl_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    pricing_method: Mapped[str] = mapped_column(String(80), default="component_built")
    commercial_recovery_status: Mapped[str] = mapped_column(String(80), default="separately_priced")
    rate_source: Mapped[str | None] = mapped_column(String(300))
    formula_version: Mapped[str] = mapped_column(String(50), default="QF-CALC-1")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    notes: Mapped[str | None] = mapped_column(Text)

    estimate: Mapped[Estimate] = relationship(back_populates="lines")

    __table_args__ = (UniqueConstraint("estimate_id", "line_number", name="uq_estimate_line_number"),)


class RuleEvaluation(RecordMixin, Base):
    __tablename__ = "rule_evaluations"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"), index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("estimating_rules.id"), index=True, nullable=False)
    result: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)


class Approval(RecordMixin, Base):
    __tablename__ = "approvals"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    approval_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))


class BackgroundJob(RecordMixin, Base):
    __tablename__ = "background_jobs"

    job_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
