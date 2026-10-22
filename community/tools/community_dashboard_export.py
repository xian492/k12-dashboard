"""Export a minimal public projection for the community dashboard."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DISPLAY_FIELDS = (
    "title",
    "link",
    "source",
    "region",
    "district_candidates",
    "school_candidates",
    "published_at_normalized",
    "content_type",
    "stage",
    "event_type",
)


class ExportError(ValueError):
    """Raised when a dashboard snapshot cannot be safely exported."""


def _display_record(record: dict) -> dict:
    result = {field: record.get(field) for field in DISPLAY_FIELDS}
    result["published_at"] = result.pop("published_at_normalized") or ""
    result["verification_status"] = "待官方核验"
    result["community_notice"] = True
    return result


def export_dashboard_data(records: list[dict], generated_at: str) -> dict:
    eligible = [record for record in records if record.get("analysis_eligible")]
    if not eligible:
        raise ExportError("community sample has no analysis-eligible records")
    projected = [_display_record(record) for record in eligible]
    return {
        "status": "success",
        "generated_at": generated_at,
        "region": "北京",
        "record_count": len(projected),
        "records": projected,
    }


def export_file(input_path: Path, output_path: Path, generated_at: str | None = None) -> dict:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ExportError("community input must be a JSON array")
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    payload = export_dashboard_data(raw, generated_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, output_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Export community dashboard display data")
    parser.add_argument("--input", type=Path, default=Path("community/data/community_beijing_enriched.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/community-data.json"))
    args = parser.parse_args()
    payload = export_file(args.input, args.output)
    print(f"exported: {payload['record_count']} community records -> {args.output}")


if __name__ == "__main__":
    main()
