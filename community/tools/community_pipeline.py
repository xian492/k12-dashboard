"""Bounded community refresh orchestration and snapshot protection."""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


PAGE_CAPS = {
    "xschu": 100,
    "newsmth-child-education": 50,
    "xscxx": 120,
    "hlgnet": 50,
    "shaoyaojuwang": 100,
    "xiaoshengchu-index": 0,
}


def _exporter():
    path = Path(__file__).with_name("community_dashboard_export.py")
    spec = importlib.util.spec_from_file_location("community_dashboard_export", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cap_candidates(candidates: list[dict]) -> list[dict]:
    counts = {source_id: 0 for source_id in PAGE_CAPS}
    result = []
    for candidate in candidates:
        source_id = candidate.get("source_id", "")
        limit = PAGE_CAPS.get(source_id, 0)
        if counts.get(source_id, 0) >= limit:
            continue
        counts[source_id] = counts.get(source_id, 0) + 1
        result.append(candidate)
    return result


def write_capped_candidates(input_path: Path, output_path: Path) -> int:
    candidates = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise ValueError("candidate input must be a JSON array")
    limited = cap_candidates(candidates)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(limited, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(limited)


def run_source_jobs(source_jobs: dict[str, Callable[[], list[dict]]]) -> tuple[list[dict], list[dict]]:
    results = []
    errors = []
    for source_id, job in source_jobs.items():
        try:
            results.extend(job())
        except Exception as exc:
            errors.append({"source_id": source_id, "error": str(exc)})
    return results, errors


def run_community_pipeline(
    *, enriched_input: Path, output_path: Path, generated_at: str | None = None,
    entry_pages: int = 6, detail_pages_attempted: int | None = None,
) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    try:
        payload = _exporter().export_file(enriched_input, output_path, generated_at)
        return {
            "status": "success",
            "generated_at": generated_at,
            "entry_pages": entry_pages,
            "detail_pages_attempted": detail_pages_attempted or 0,
            "valid_records": payload["record_count"],
            "errors": [],
            "output_path": str(output_path),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "generated_at": generated_at,
            "entry_pages": entry_pages,
            "detail_pages_attempted": detail_pages_attempted or 0,
            "valid_records": 0,
            "errors": [{"error": str(exc)}],
            "output_path": str(output_path),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a protected community dashboard snapshot")
    parser.add_argument("--input", type=Path, default=Path("community/data/community_beijing_enriched.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/community-data.json"))
    parser.add_argument("--status-output", type=Path, default=Path("docs/community-status.json"))
    parser.add_argument("--cap-input", type=Path)
    parser.add_argument("--cap-output", type=Path)
    parser.add_argument("--entry-pages", type=int, default=6)
    parser.add_argument("--detail-pages-attempted", type=int, default=0)
    args = parser.parse_args()
    if args.cap_input or args.cap_output:
        if not args.cap_input or not args.cap_output:
            parser.error("--cap-input and --cap-output must be used together")
        print(f"capped candidates: {write_capped_candidates(args.cap_input, args.cap_output)}")
        return
    result = run_community_pipeline(
        enriched_input=args.input,
        output_path=args.output,
        entry_pages=args.entry_pages,
        detail_pages_attempted=args.detail_pages_attempted,
    )
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
