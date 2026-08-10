from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_PATHS = (
    "README.md",
    "docs/CLASSIFIRE_ARCHITECTURE.md",
    "docs/CLASSIFIRE_ROADMAP.md",
    "knowledge/amendments/CLASSIFIRE_KNOWLEDGE_ALIGNMENT_AMENDMENT_v2.13.1.md",
    "knowledge/manifests/classifire-knowledge-source-v2.13.json",
    "knowledge/releases/v2.13/CLASSIFIRE_KNOWLEDGE_RELEASE_MANIFEST_v2.13.json",
    "scripts/run_classifire_real_uat_fireseals.py",
    "scripts/run_classifire_real_uat_fireseals_bounded.py",
    "src/classifire/services/frl_policy.py",
    "src/classifire/services/technical_registry.py",
)

SOURCE_PACK_RELATIVE = Path("knowledge/source/CLASSIFIRE_Knowledge_Source_Pack_v2.13.zip")


def _read_text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    return json.loads(_read_text(root, relative))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_project(root: Path, *, require_source_pack: bool = False) -> dict[str, Any]:
    root = root.resolve()
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    def check(name: str, condition: bool, detail: str, *, warning: bool = False) -> None:
        checks.append({"name": name, "ok": bool(condition), "detail": detail, "warning": warning})
        if condition:
            return
        if warning:
            warnings.append(f"{name}: {detail}")
        else:
            errors.append(f"{name}: {detail}")

    for relative in REQUIRED_PATHS:
        check(
            f"required:{relative}",
            (root / relative).is_file(),
            f"required repository file is missing: {relative}",
        )

    # Stop detailed parsing only if a required manifest/doc is absent.
    if errors:
        return {
            "schema": "CLASSIFIRE-PROJECT-ALIGNMENT-AUDIT-v1",
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
        }

    source_manifest = _read_json(root, "knowledge/manifests/classifire-knowledge-source-v2.13.json")
    release_manifest = _read_json(
        root,
        "knowledge/releases/v2.13/CLASSIFIRE_KNOWLEDGE_RELEASE_MANIFEST_v2.13.json",
    )
    architecture = _read_text(root, "docs/CLASSIFIRE_ARCHITECTURE.md")
    roadmap = _read_text(root, "docs/CLASSIFIRE_ROADMAP.md")
    amendment = _read_text(
        root,
        "knowledge/amendments/CLASSIFIRE_KNOWLEDGE_ALIGNMENT_AMENDMENT_v2.13.1.md",
    )
    bounded_runner = _read_text(root, "scripts/run_classifire_real_uat_fireseals_bounded.py")
    frl_policy = _read_text(root, "src/classifire/services/frl_policy.py")
    technical_registry = _read_text(root, "src/classifire/services/technical_registry.py")
    gitignore = _read_text(root, ".gitignore")
    readme = _read_text(root, "README.md")

    check("product-name", source_manifest.get("product") == "CLASSIFIRE", "source manifest product must be CLASSIFIRE")
    check(
        "reviewed-package-count",
        len(source_manifest.get("packages") or []) == 16,
        "reviewed source manifest must contain the 16 supplied v2.13 packages",
    )
    check(
        "package15-firefly-identity",
        any(
            item.get("filename") == "CLASSIFIRE_15_Technical_System_Library_v2.13.txt"
            and item.get("technical_library_id") == "TECHLIB-FIREFLY-P15"
            and item.get("manufacturer_coverage") == ["FIREFLY"]
            for item in source_manifest.get("packages") or []
        ),
        "Package 15 must be identified as the FIREFLY technical library",
    )
    check(
        "registry-architecture",
        "CLASSIFIRE Technical Authority Registry" in architecture
        and "Package 15 is therefore the **FIREFLY Technical System Library**" in architecture,
        "architecture must place Package 15/17 under the Technical Authority Registry",
    )
    check(
        "alignment-amendment-registry",
        "Package 15 is the current **FIREFLY Technical System Library**" in amendment,
        "alignment amendment must constrain legacy Package-15-global-authority wording",
    )
    check(
        "scope-sensitive-frl",
        "PENETRATION_DEFAULT_FRL = \"-/120/120\"" in frl_policy
        and "STRUCTURAL_STEEL_DEFAULT_FRL = \"120/-/-\"" in frl_policy
        and "FIRE_RATED_DUCT_RUN" in frl_policy,
        "FRL policy must distinguish penetration, structural-steel and whole duct-run scope",
    )
    check(
        "technical-registry-code",
        'technical_library_id="TECHLIB-FIREFLY-P15"' in technical_registry
        and 'library_name="FIREFLY Technical System Library"' in technical_registry,
        "technical registry code must use the same FIREFLY identity as manifests/docs",
    )
    check(
        "bounded-fireseal-runner",
        "BOUNDED_DEFECT_EVIDENCE_CHARS = 12_000" in bounded_runner
        and "_reduce_physical_evidence" not in bounded_runner,
        "real fire-seal UAT must use the measured deterministic 12,000-character path",
    )
    check(
        "roadmap-current-runner",
        "12,000-character Windows-safe defect budget" in roadmap,
        "roadmap must record the current measured UAT evidence budget",
    )
    check(
        "human-release-boundary",
        "Human Release" in architecture and "human-only" in architecture,
        "Human Release must remain human-only in the active architecture",
    )
    check(
        "preproduction-status",
        "pre-production" in readme.lower(),
        "README must not represent the current build as production-authorised",
    )
    check(
        "confidential-source-default-ignore",
        "knowledge/source/**" in gitignore and "private-data/**" in gitignore,
        "ordinary Git operations must ignore confidential controlled source",
    )
    check(
        "no-tool-probes",
        not (root / "docs/_tool_probe.tmp").exists() and not (root / "docs/_tool_probe2.tmp").exists(),
        "temporary repository probe files must not remain tracked",
    )

    release_source_pack = release_manifest.get("source_pack") or {}
    source_publication = source_manifest.get("publication") or {}
    check(
        "knowledge-release-manifest-valid",
        release_manifest.get("schema") == "CLASSIFIRE-KNOWLEDGE-RELEASE-MANIFEST-v1"
        and release_manifest.get("product") == "CLASSIFIRE",
        "knowledge release manifest must be a real JSON release manifest, not a placeholder",
    )
    check(
        "source-pack-metadata-aligned",
        release_source_pack.get("expected_sha256") == source_publication.get("source_pack_sha256")
        and release_source_pack.get("expected_size_bytes") == source_publication.get("source_pack_size_bytes"),
        "release and source manifests must agree on governed source-pack hash and size",
    )

    source_pack = root / SOURCE_PACK_RELATIVE
    if source_pack.is_file():
        actual_sha = _sha256(source_pack)
        actual_size = source_pack.stat().st_size
        check(
            "private-source-pack-sha256",
            actual_sha == source_publication.get("source_pack_sha256"),
            f"source pack hash mismatch: {actual_sha}",
        )
        check(
            "private-source-pack-size",
            actual_size == source_publication.get("source_pack_size_bytes"),
            f"source pack size mismatch: {actual_size}",
        )
    else:
        check(
            "private-source-pack-published",
            False,
            (
                "governed source pack is not present in the checkout; publish it through "
                "scripts/publish_classifire_knowledge_source_pack.ps1 when completing K1"
            ),
            warning=not require_source_pack,
        )

    # Known architectural migration items are warnings, not false PASSes.
    canonical_models = _read_text(root, "src/classifire/canonical_models.py")
    release_scope = _read_text(root, "src/classifire/services/release_scope.py")
    models = _read_text(root, "src/classifire/models.py")
    routing = _read_text(root, "knowledge/package-13/runtime-routing.yaml")

    check(
        "registry-neutral-db-fields",
        "package15_release_id" not in canonical_models,
        "legacy package15_release_id remains a compatibility field; migrate new records to registry-neutral technical-library provenance",
        warning=True,
    )
    check(
        "multi-library-estimate-pinning",
        '"technical": "technical_release_id"' not in release_scope,
        "estimate pinning is still singular technical-release compatibility logic; multi-library registry pinning remains a roadmap migration",
        warning=True,
    )
    check(
        "no-silent-service-quantity-default",
        'quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1"))' not in models,
        "Service ORM still has a database default quantity of 1; controlled API currently protects UAT but schema-level removal remains required",
        warning=True,
    )
    check(
        "package13-runtime-routing-rebrand",
        "owner: quantifire_domain_service" not in routing and "required_product: QUANTIFIRE" not in routing,
        "Package 13 runtime-routing file still carries legacy QUANTIFIRE implementation names and should be reissued as a CLASSIFIRE routing overlay",
        warning=True,
    )

    return {
        "schema": "CLASSIFIRE-PROJECT-ALIGNMENT-AUDIT-v1",
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit CLASSIFIRE project/knowledge alignment.")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--require-source-pack", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root or Path(__file__).resolve().parents[1]
    result = audit_project(root, require_source_pack=args.require_source_pack)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
