#!/usr/bin/env python3
"""Run the Crawl4AI school homepage probe and write a JSON report."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from school_crawler import SCHOOL_PROBE_SPECS, probe_schools


def write_probe_report(report: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe public Beijing school websites with Crawl4AI.")
    parser.add_argument("--output", required=True, type=Path, help="JSON report output path")
    return parser


async def run(output: Path) -> int:
    report = await probe_schools(SCHOOL_PROBE_SPECS)
    write_probe_report(report, output)
    successes = sum(item["status"] == "success" for item in report)
    failures = len(report) - successes
    sections = sum(item["items_found"] for item in report)
    print(f"schools={len(report)} success={successes} failed={failures} candidate_sections={sections}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
