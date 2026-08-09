from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "src" / "classifire" / "models.py"
SOURCE_COMMIT = "a435236ea0883c34af57cc7d14729ec918b2fbf4"
SOURCE_PATH = "src/classifire/models.py"

AGENT_PRINCIPAL_BLOCK = '''\n\nclass AgentServicePrincipal(RecordMixin, Base):
    """Machine credential for one role-limited CLASSIFIRE OpenClaw agent.

    Only a SHA-256 digest of the high-entropy bearer token is persisted. Agent
    scopes are independent of human User roles so machine identities cannot
    inherit Human Release or other human approval authority.
    """

    __tablename__ = "agent_service_principals"

    agent_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
'''


def _git_show(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Unable to read the controlled pre-agent ORM from Git history. "
            f"git show failed: {result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return result.stdout.decode("utf-8")


def main() -> int:
    baseline = _git_show(SOURCE_PATH)

    user_to_audit = '''    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))\n\n\nclass AuditEvent(RecordMixin, Base):\n'''
    if user_to_audit not in baseline:
        raise RuntimeError("Controlled pre-agent User/AuditEvent boundary did not match expected source.")
    baseline = baseline.replace(
        user_to_audit,
        '    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))\n'
        + AGENT_PRINCIPAL_BLOCK
        + '\n\nclass AuditEvent(RecordMixin, Base):\n',
        1,
    )

    audit_event_old = '''    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)\n    actor_type: Mapped[str] = mapped_column(String(30), default="user", nullable=False)\n'''
    audit_event_new = '''    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)\n    audit_trail_id: Mapped[str | None] = mapped_column(ForeignKey("audit_trails.id"), index=True)\n    actor_type: Mapped[str] = mapped_column(String(30), default="user", nullable=False)\n'''
    if audit_event_old not in baseline:
        raise RuntimeError("Controlled pre-agent AuditEvent block did not match expected source.")
    baseline = baseline.replace(audit_event_old, audit_event_new, 1)

    MODELS.write_text(baseline, encoding="utf-8")
    print("Restored controlled CLASSIFIRE ORM from the pre-agent commit and applied only:")
    print(" - AgentServicePrincipal machine-credential mapping")
    print(" - AuditEvent.audit_trail_id mapping required by migration 0004")
    print(" - no duplicate AuditTrail mapping in classifire.models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
