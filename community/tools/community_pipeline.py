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


def _llm_classify_inplace(enriched_input: Path, call_api: bool = True) -> str:
    """LLM 补充分类：只处理规则法低置信条目，就地更新 enriched 快照。

    API 未配置或调用失败时静默跳过，管线不受影响；结果按内容哈希缓存，
    重跑管线不重复计费。"""
    try:
        import json

        import importlib.util as _ilu

        _spec = _ilu.spec_from_file_location(
            "community_llm_classifier",
            Path(__file__).with_name("community_llm_classifier.py"),
        )
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        classify_records, needs_llm = _mod.classify_records, _mod.needs_llm

        records = json.loads(enriched_input.read_text(encoding="utf-8"))
        if isinstance(records, dict):
            records = records.get("records", [])
        targets = [r for r in records if needs_llm(r)]
        _, status = classify_records(targets, call_api=call_api)
        enriched_input.write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return f"llm: {status}"
    except Exception as exc:  # LLM 层任何失败都不阻断导出
        return f"llm: skipped ({type(exc).__name__}: {str(exc)[:60]})"


def run_community_pipeline(
    *, enriched_input: Path, output_path: Path, generated_at: str | None = None,
    entry_pages: int = 6, detail_pages_attempted: int | None = None,
    llm_classify: bool = True,
) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    # llm_classify=False 只关闭 API 调用；缓存中的历史/人工分类始终应用。
    llm_status = _llm_classify_inplace(enriched_input, call_api=llm_classify)
    print(llm_status)
    try:
        payload = _exporter().export_file(enriched_input, output_path, generated_at)
        return {
            "status": "success",
            "generated_at": generated_at,
            "entry_pages": entry_pages,
            "detail_pages_attempted": detail_pages_attempted or 0,
            "valid_records": payload["record_count"],
            "llm": llm_status,
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
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM 补充分类")
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
        llm_classify=not args.no_llm,
    )
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
