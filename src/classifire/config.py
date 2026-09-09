from __future__ import annotations

import json
import re
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ProductionConfigurationError(RuntimeError):
    """Production startup was refused before any application mutation."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("Unsafe production configuration: " + "; ".join(findings))


def _canonical_host(value: str) -> str | None:
    """Return one exact hostname/IP spelling, rejecting wildcard-like aliases."""

    if not value or value != value.strip() or any(character in value for character in "/*"):
        return None
    candidate = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    try:
        return ip_address(candidate).compressed
    except ValueError:
        pass

    numeric_labels = candidate.split(".")
    if all(re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", label) for label in numeric_labels):
        return None
    if ":" in candidate or len(candidate) > 253 or candidate.endswith("."):
        return None
    try:
        ascii_host = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    labels = ascii_host.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(character.isalnum() or character == "-" for character in label)
        for label in labels
    ):
        return None
    return ascii_host


def _canonical_https_origin(value: str) -> tuple[str, str] | None:
    """Return an exact HTTPS origin and its host for production CORS checks."""

    if value != value.strip():
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    host = _canonical_host(parsed.hostname)
    if host is None:
        return None
    display_host = f"[{host}]" if ":" in host else host
    canonical = f"https://{display_host}"
    if port not in {None, 443}:
        canonical = f"{canonical}:{port}"
    if value != canonical:
        return None
    return canonical, host


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLASSIFIRE_",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/classifire.db"
    secret_key: str = "development-only-change-me"  # noqa: S105
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me-immediately"  # noqa: S105
    host: str = "127.0.0.1"
    port: int = 8787
    draft_client_config: Path | None = None
    draft_client_file_download_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    draft_pdf_suggestions_enabled: bool = False
    draft_pdf_suggestions_model: str | None = None
    draft_pdf_suggestions_api_key: SecretStr | None = Field(default=None, exclude=True)
    storage_root: Path = Path("./data/storage")
    max_upload_mb: int = 100
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://127.0.0.1:8787", "http://localhost:8787"]
    )
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost"]
    )
    session_https_only: bool = False
    clamav_host: str | None = None
    clamav_port: int = 3310
    mission_control_url: str = "http://127.0.0.1:3000"
    mission_control_api_key: str | None = None
    openclaw_config_path: Path | None = None
    openclaw_state_dir: Path | None = None
    adjudicated_initial_submission_enabled: bool = False
    adjudicated_admission_public_keys: dict[str, str] = Field(default_factory=dict)
    adjudicated_admission_issuer_key_ids: dict[str, list[str]] = Field(default_factory=dict)
    currency: str = "AUD"
    tax_name: str = "GST"
    tax_rate: str = "0.10"
    jurisdiction: str = "NSW/ACT, Australia"
    default_length_unit: str = "mm"
    default_area_unit: str = "m2"

    @field_validator(
        "allowed_origins", "trusted_hosts", "draft_client_file_download_hosts", mode="before"
    )
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "adjudicated_admission_public_keys",
        "adjudicated_admission_issuer_key_ids",
        mode="before",
    )
    @classmethod
    def require_mapping_configuration(cls, value: object) -> object:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("must be a JSON object")
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
            if self.admin_password == "change-me-immediately":  # noqa: S105  # nosec B105
                findings.append("Default administrator password must be replaced")
            if not self.session_https_only:
                findings.append(
                    "CLASSIFIRE_SESSION_HTTPS_ONLY should be true behind production TLS"
                )
            if not self.database_url.startswith("postgresql"):
                findings.append("PostgreSQL is required for multi-user production deployment")
            canonical_trusted_hosts: set[str] = set()
            if not self.trusted_hosts:
                findings.append("CLASSIFIRE_TRUSTED_HOSTS must contain at least one explicit host")
            for configured_host in self.trusted_hosts:
                if "*" in configured_host:
                    findings.append("CLASSIFIRE_TRUSTED_HOSTS may not contain wildcards")
                    continue
                canonical_host = _canonical_host(configured_host)
                if canonical_host is None or canonical_host != configured_host:
                    findings.append(
                        "CLASSIFIRE_TRUSTED_HOSTS must contain canonical host names or IP addresses"
                    )
                    continue
                canonical_trusted_hosts.add(canonical_host)

            if not self.allowed_origins:
                findings.append(
                    "CLASSIFIRE_ALLOWED_ORIGINS must contain at least one exact HTTPS origin"
                )
            for configured_origin in self.allowed_origins:
                if "*" in configured_origin:
                    findings.append("CLASSIFIRE_ALLOWED_ORIGINS may not contain wildcards")
                    continue
                canonical_origin = _canonical_https_origin(configured_origin)
                if canonical_origin is None:
                    findings.append("CLASSIFIRE_ALLOWED_ORIGINS must contain exact HTTPS origins")
                    continue
                if canonical_origin[1] not in canonical_trusted_hosts:
                    findings.append(
                        "Each allowed origin host must also appear in CLASSIFIRE_TRUSTED_HOSTS"
                    )
        return findings


def require_production_configuration(settings: Settings) -> None:
    """Refuse a production server with unsafe settings before it touches state."""

    if settings.env != "production":
        return
    findings = settings.validate_production()
    if findings:
        raise ProductionConfigurationError(findings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
