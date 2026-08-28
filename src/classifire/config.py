from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True, slots=True)
class ProductionConfigurationFinding:
    code: str
    message: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLASSIFIRE_",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/classifire.db"
    secret_key: str = "development-only-change-me"  # noqa: S105 - explicit local-only default
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me-immediately"  # noqa: S105 - explicit local-only default
    host: str = "127.0.0.1"
    port: int = 8787
    storage_root: Path = Path("./data/storage")
    max_upload_mb: int = 100
    upload_ingress_ceiling_mb: int | None = None
    technical_pdf_preview_enabled: bool = False
    technical_extraction_executor_enabled: bool = False
    technical_parser_orphan_reconciliation_enabled: bool = False
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8787", "http://localhost:8787"]
    )
    trusted_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])
    session_https_only: bool = False
    clamav_host: str | None = None
    clamav_port: int = 3310
    clamav_stream_max_mb: int | None = None
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

    @field_validator("allowed_origins", "trusted_hosts", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
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

    @field_validator("storage_root", mode="after")
    @classmethod
    def ensure_storage_root(cls, value: Path, info: ValidationInfo) -> Path:
        # Local installs retain their convenient bootstrap behavior. Production
        # must validate an operator-provisioned mount without creating through
        # an absent or redirected path during settings construction.
        if info.data.get("env") != "production":
            value.mkdir(parents=True, exist_ok=True)
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def upload_ingress_ceiling_bytes(self) -> int:
        ceiling_mb = (
            self.max_upload_mb
            if self.upload_ingress_ceiling_mb is None
            else self.upload_ingress_ceiling_mb
        )
        return ceiling_mb * 1024 * 1024

    @property
    def technical_pdf_preview_runtime_allowed(self) -> bool:
        return self.technical_pdf_preview_enabled and self.env != "production"

    @property
    def technical_extraction_executor_runtime_allowed(self) -> bool:
        """Permit only injected test runners until a bounded runtime is implemented."""

        return self.technical_extraction_executor_enabled and self.env == "test"

    @property
    def technical_parser_orphan_reconciliation_runtime_allowed(self) -> bool:
        """Permit cleanup-only reconciliation tests without enabling parser execution."""

        return self.technical_parser_orphan_reconciliation_enabled and self.env == "test"

    @staticmethod
    def _is_exact_https_origin(origin: str) -> bool:
        if (
            origin != origin.strip()
            or "*" in origin
            or "\\" in origin
            or "?" in origin
            or "#" in origin
        ):
            return False
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        if (
            parsed.scheme.casefold() != "https"
            or not parsed.netloc
            or parsed.netloc.endswith(":")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return False
        try:
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError:
            return False
        return hostname is not None and not any(character.isspace() for character in parsed.netloc)

    def production_configuration_findings(self) -> tuple[ProductionConfigurationFinding, ...]:
        findings: list[ProductionConfigurationFinding] = []
        if self.env == "production":
            if (
                self.secret_key in {"development-only-change-me", "change-me"}
                or len(self.secret_key) < 32
            ):
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_SECRET_KEY_INVALID",
                        "CLASSIFIRE_SECRET_KEY must be a random value of at least 32 characters",
                    )
                )
            if self.admin_password == "change-me-immediately":  # noqa: S105  # nosec B105
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_ADMIN_PASSWORD_DEFAULT",
                        "Default administrator password must be replaced",
                    )
                )
            if not self.session_https_only:
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_SECURE_SESSION_REQUIRED",
                        "CLASSIFIRE_SESSION_HTTPS_ONLY must be true behind production TLS",
                    )
                )
            if not self.trusted_hosts or any(
                not host.strip() or "*" in host for host in self.trusted_hosts
            ):
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_TRUSTED_HOSTS_INVALID",
                        "CLASSIFIRE_TRUSTED_HOSTS must contain explicit production host names",
                    )
                )
            if any(not self._is_exact_https_origin(origin) for origin in self.allowed_origins):
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_ALLOWED_ORIGINS_INVALID",
                        "CLASSIFIRE_ALLOWED_ORIGINS must contain exact HTTPS origins only",
                    )
                )
            if (
                not isinstance(self.max_upload_mb, int)
                or isinstance(self.max_upload_mb, bool)
                or not 1 <= self.max_upload_mb <= 1024
            ):
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_UPLOAD_LIMIT_INVALID",
                        "CLASSIFIRE_MAX_UPLOAD_MB must be an integer between 1 and 1024",
                    )
                )
            effective_ingress_ceiling_mb = (
                self.max_upload_mb
                if self.upload_ingress_ceiling_mb is None
                else self.upload_ingress_ceiling_mb
            )
            if (
                not isinstance(effective_ingress_ceiling_mb, int)
                or isinstance(effective_ingress_ceiling_mb, bool)
                or not 1 <= effective_ingress_ceiling_mb <= 1024
            ):
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_UPLOAD_INGRESS_CEILING_INVALID",
                        "CLASSIFIRE_UPLOAD_INGRESS_CEILING_MB must resolve to an "
                        "integer between 1 and 1024",
                    )
                )
            elif effective_ingress_ceiling_mb < self.max_upload_mb:
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_UPLOAD_INGRESS_CEILING_BELOW_ADMISSION_LIMIT",
                        "CLASSIFIRE_UPLOAD_INGRESS_CEILING_MB must be at least "
                        "CLASSIFIRE_MAX_UPLOAD_MB",
                    )
                )
            database_scheme = self.database_url.partition(":")[0].casefold()
            if database_scheme != "postgresql" and not database_scheme.startswith("postgresql+"):
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_DATABASE_NOT_POSTGRESQL",
                        "CLASSIFIRE_DATABASE_URL must use PostgreSQL in production",
                    )
                )
            if not self.storage_root.is_absolute():
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_STORAGE_ROOT_NOT_ABSOLUTE",
                        "CLASSIFIRE_STORAGE_ROOT must be an absolute path in production",
                    )
                )
            if self.clamav_host is None or not self.clamav_host.strip():
                findings.append(
                    ProductionConfigurationFinding(
                        "MALWARE_SCANNER_REQUIRED",
                        "CLASSIFIRE_CLAMAV_HOST is required for fail-closed evidence uploads",
                    )
                )
            if (
                not isinstance(self.clamav_port, int)
                or isinstance(self.clamav_port, bool)
                or not 1 <= self.clamav_port <= 65535
            ):
                findings.append(
                    ProductionConfigurationFinding(
                        "MALWARE_SCANNER_CONFIGURATION_INVALID",
                        "CLASSIFIRE_CLAMAV_PORT must be between 1 and 65535",
                    )
                )
            if self.clamav_stream_max_mb is None:
                findings.append(
                    ProductionConfigurationFinding(
                        "MALWARE_SCANNER_STREAM_LIMIT_REQUIRED",
                        "CLASSIFIRE_CLAMAV_STREAM_MAX_MB is required in production",
                    )
                )
            elif (
                not isinstance(self.clamav_stream_max_mb, int)
                or isinstance(self.clamav_stream_max_mb, bool)
                or self.clamav_stream_max_mb <= 0
                or self.clamav_stream_max_mb < effective_ingress_ceiling_mb
            ):
                findings.append(
                    ProductionConfigurationFinding(
                        "MALWARE_SCANNER_STREAM_LIMIT_TOO_SMALL",
                        "CLASSIFIRE_CLAMAV_STREAM_MAX_MB must be positive and at least "
                        "the effective CLASSIFIRE_UPLOAD_INGRESS_CEILING_MB",
                    )
                )
            if self.technical_pdf_preview_enabled:
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_PDF_PREVIEW_SANDBOX_REQUIRED",
                        "CLASSIFIRE_TECHNICAL_PDF_PREVIEW_ENABLED must remain false in "
                        "production until the renderer has an enforced OS/container sandbox",
                    )
                )
            if self.technical_extraction_executor_enabled:
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_TECHNICAL_EXTRACTION_SANDBOX_REQUIRED",
                        "CLASSIFIRE_TECHNICAL_EXTRACTION_EXECUTOR_ENABLED must remain false "
                        "in production until the parser has an enforced digest-pinned "
                        "OS/container sandbox",
                    )
                )
            if self.technical_parser_orphan_reconciliation_enabled:
                findings.append(
                    ProductionConfigurationFinding(
                        "PRODUCTION_TECHNICAL_PARSER_ORPHAN_RECONCILIATION_FORBIDDEN",
                        "CLASSIFIRE_TECHNICAL_PARSER_ORPHAN_RECONCILIATION_ENABLED must "
                        "remain false in production until cleanup-only reconciliation has "
                        "an approved singleton ownership boundary",
                    )
                )
        return tuple(findings)

    def validate_production(self) -> list[str]:
        return [finding.message for finding in self.production_configuration_findings()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
