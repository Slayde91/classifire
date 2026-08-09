from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "src" / "classifire" / "models.py"


def main() -> int:
    text = MODELS.read_text(encoding="utf-8")

    audit_event_old = '''class AuditEvent(RecordMixin, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
'''
    audit_event_new = '''class AuditEvent(RecordMixin, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    audit_trail_id: Mapped[str | None] = mapped_column(ForeignKey("audit_trails.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
'''

    stale_audit_trail = '''\n\nclass AuditTrail(RecordMixin, Base):
    __tablename__ = "audit_trails"

    project_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    event_ids: Mapped[list[str] | None] = mapped_column(JSON)
    source_receipt_ids: Mapped[list[str] | None] = mapped_column(JSON)
    validation_receipt_ids: Mapped[list[str] | None] = mapped_column(JSON)
    summary_hash: Mapped[str | None] = mapped_column(String(64))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
'''

    if audit_event_old not in text and audit_event_new not in text:
        raise RuntimeError("AuditEvent source block did not match the controlled repair precondition.")
    if stale_audit_trail not in text and "class AuditTrail(RecordMixin, Base):" in text:
        raise RuntimeError("Legacy AuditTrail source block did not match the controlled repair precondition.")

    changed = False
    if audit_event_old in text:
        text = text.replace(audit_event_old, audit_event_new, 1)
        changed = True

    if stale_audit_trail in text:
        text = text.replace(stale_audit_trail, "\n", 1)
        changed = True

    if not changed:
        print("Audit-trail ORM repair is already applied.")
        return 0

    MODELS.write_text(text, encoding="utf-8")
    print("Applied controlled audit-trail ORM repair:")
    print(" - removed stale classifire.models.AuditTrail mapping")
    print(" - mapped AuditEvent.audit_trail_id to audit_trails.id")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
