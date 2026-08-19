from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLASSIFIRE_",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/classifire.db"
    secret_key: str = "development-only-change-me"
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me-immediately"
    host: str = "127.0.0.1"
    port: int = 8787
    storage_root: Path = Path("./data/storage")
    max_upload_mb: int = 100
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8787", "http://localhost:8787"]
    )
    trusted_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])
    session_https_only: bool = False
    clamav_host: str | None = None
    clamav_port: int = 3310
    mission_control_url: str = "http://127.0.0.1:3000"
    mission_control_api_key: str | None = None
    openclaw_config_path: Path | None = None
    openclaw_state_dir: Path | None = None
    # The adjudicated canonical writer is disabled unless an operator explicitly
    # enables it and pins governance P-256 public keys. Private signing keys
    # are never read by CLASSIFIRE.
    adjudicated_initial_submission_enabled: bool = False
    adjudicated_admission_public_keys: dict[str, str] = Field(default_factory=dict)
    # Every trusted issuer must be explicitly bound to one or more of the
    # pinned public-key IDs.  A global issuer list would permit a key trusted
    # for one issuer to impersonate another trusted issuer.
    adjudicated_admission_issuer_key_ids: dict[str, list[str]] = Field(default_factory=dict)
    adjudicated_admission_max_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    currency: str = "AUD"
    tax_name: str = "GST"
    tax_rate: str = "0.10"
    jurisdiction: str = "NSW/ACT, Australia"
    default_length_unit: str = "mm"
    default_area_unit: str = "m2"

    @field_validator(
        "allowed_origins",
        "trusted_hosts",
        mode="before",
    )
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("storage_root", mode="after")
    @classmethod
    def ensure_storage_root(cls, value: Path) -> Path:
        value.mkdir(parents=True, exist_ok=True)
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def validate_production(self) -> list[str]:
        findings: list[str] = []
        if self.env == "production":
            if (
                self.secret_key in {"development-only-change-me", "change-me"}
                or len(self.secret_key) < 32
            ):
                findings.append(
                    "CLASSIFIRE_SECRET_KEY must be a random value of at least 32 characters"
                )
            if self.admin_password == "change-me-immediately":
                findings.append("Default administrator password must be replaced")
            if not self.session_https_only:
                findings.append(
                    "CLASSIFIRE_SESSION_HTTPS_ONLY should be true behind production TLS"
                )
            if self.database_url.startswith("sqlite"):
                findings.append("PostgreSQL is recommended for multi-user production deployment")
            if self.adjudicated_initial_submission_enabled:
                if not self.adjudicated_admission_public_keys:
                    findings.append(
                        "CLASSIFIRE_ADJUDICATED_ADMISSION_PUBLIC_KEYS must pin "
                        "governance public keys"
                    )
                if not self.adjudicated_admission_issuer_key_ids:
                    findings.append(
                        "CLASSIFIRE_ADJUDICATED_ADMISSION_ISSUER_KEY_IDS must bind each "
                        "trusted issuer to its pinned key ID(s)"
                    )
        return findings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
