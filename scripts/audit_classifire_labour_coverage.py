from __future__ import annotations

from sqlalchemy import select

from classifire.db import SessionLocal
from classifire.models import LabourComponent, LibraryRelease, TechnicalVariant


def main() -> int:
    with SessionLocal() as db:
        labour = list(
            db.scalars(
                select(LabourComponent)
                .where(LabourComponent.status == "active")
                .order_by(LabourComponent.code)
            ).all()
        )

        print("LABOUR RECORDS:")
        for row in labour:
            print(
                "  "
                f"{row.code} | {row.name} | "
                f"default_hours={row.default_hours} | "
                f"base_rate={row.base_rate} | "
                f"source={row.productivity_source}"
            )

        release = db.scalar(
            select(LibraryRelease).where(
                LibraryRelease.library_type == "technical",
                LibraryRelease.version == "2.13-runtime",
                LibraryRelease.status == "active",
            )
        )
        if release is None:
            raise RuntimeError("Active technical 2.13-runtime release not found")

        record_ids = [
            str(row["id"])
            for row in ((release.source_manifest or {}).get("records") or [])
            if isinstance(row, dict) and row.get("id")
        ]
        if not record_ids:
            raise RuntimeError("Technical 2.13-runtime manifest contains no record IDs")

        variants = list(
            db.scalars(
                select(TechnicalVariant).where(TechnicalVariant.id.in_(record_ids))
            ).all()
        )

        activities: set[str] = set()
        for variant in variants:
            for value in variant.labour_requirements or []:
                text = str(value).strip()
                if text:
                    activities.add(text)

            source = variant.source_json or {}
            parsed = source.get("parsed_requirements") or {}
            for value in parsed.get("required_labour_activities") or []:
                text = str(value).strip()
                if text:
                    activities.add(text)

            components = variant.component_requirements
            if isinstance(components, dict):
                for value in components.get("required_labour_activities") or []:
                    text = str(value).strip()
                    if text:
                        activities.add(text)

        print()
        print(f"ACTIVE PACKAGE 15 VARIANTS CHECKED: {len(variants)}")
        print(f"UNIQUE REQUIRED LABOUR ACTIVITIES: {len(activities)}")
        for activity in sorted(activities):
            print(f"  {activity}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
