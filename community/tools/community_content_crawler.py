"""Collect public community detail-page text into JSONL."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path


BLOCKED_MARKERS = (
    "anti-bot",
    "blocked",
    "captcha",
    "cloudflare",
    "access denied",
    "需要登录",
    "请登录",
)
LOGIN_MARKERS = ("请登录", "登录后查看", "登录后才能", "注册后查看")
DATE_RE = re.compile(r"(?:20\d{2}[年./-]\s*\d{1,2}[月./-]\s*\d{1,2}(?:日)?)")


def _markdown_text(markdown) -> str:
    if markdown is None:
        return ""
    raw = getattr(markdown, "raw_markdown", None)
    return str(raw if raw is not None else markdown).strip()


def classify_content(
    *, success: bool, markdown: str, error: str, candidate_title: str = ""
) -> str:
    error_lower = (error or "").lower()
    text = (markdown or "").strip()
    text_lower = text.lower()
    if candidate_title.strip() in {"登录", "注册", "登录页", "注册页"}:
        return "login_required"
    if any(marker in error_lower for marker in BLOCKED_MARKERS):
        return "blocked"
    if "404 not found" in text_lower or "page not found" in text_lower:
        return "not_found"
    if any(marker in text for marker in LOGIN_MARKERS):
        return "login_required"
    if not success:
        return "failed"
    if len(text) < 80:
        return "empty"
    return "success"


def _published_at_hint(markdown: str) -> str:
    match = DATE_RE.search(markdown or "")
    return match.group(0) if match else ""


def normalize_content_result(
    candidate: dict,
    *,
    status: str,
    markdown: str,
    error: str,
    crawled_at: str,
) -> dict:
    content_text = markdown if status == "success" else ""
    return {
        "title": candidate.get("title", ""),
        "link": candidate.get("link", ""),
        "source_id": candidate.get("source_id", ""),
        "source": candidate.get("source", ""),
        "region": candidate.get("region", ""),
        "tags": candidate.get("tags", []),
        "published_at_hint": _published_at_hint(markdown),
        "crawled_at": crawled_at,
        "crawl_status": status,
        "content_chars": len(content_text),
        "content_text": content_text,
        "error": (error or "")[:500],
    }


async def crawl_one(crawler, candidate: dict, semaphore: asyncio.Semaphore) -> dict:
    from crawl4ai import CacheMode, CrawlerRunConfig

    started = time.monotonic()
    crawled_at = datetime.now(timezone.utc).isoformat()
    try:
        async with semaphore:
            result = await crawler.arun(
                url=candidate["link"],
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    page_timeout=30000,
                    exclude_external_links=True,
                    exclude_social_media_links=True,
                ),
            )
        markdown = _markdown_text(getattr(result, "markdown", ""))
        error = str(getattr(result, "error_message", "") or "")
        status = classify_content(
            success=bool(getattr(result, "success", False)),
            markdown=markdown,
            error=error,
            candidate_title=candidate.get("title", ""),
        )
        item = normalize_content_result(
            candidate,
            status=status,
            markdown=markdown,
            error=error,
            crawled_at=crawled_at,
        )
        item["seconds"] = round(time.monotonic() - started, 2)
        return item
    except Exception as exc:
        item = normalize_content_result(
            candidate,
            status=classify_content(success=False, markdown="", error=str(exc)),
            markdown="",
            error=str(exc),
            crawled_at=crawled_at,
        )
        item["seconds"] = round(time.monotonic() - started, 2)
        return item


async def crawl_content(candidates: list[dict], concurrency: int = 8) -> list[dict]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig
    except ImportError as exc:
        raise RuntimeError("Crawl4AI is not installed in the active Python environment.") from exc

    semaphore = asyncio.Semaphore(max(1, concurrency))
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        return await asyncio.gather(
            *(crawl_one(crawler, candidate, semaphore) for candidate in candidates)
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public community page text into JSONL")
    parser.add_argument("--input", type=Path, default=Path("community/data/community_beijing.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("community/data/community_beijing_content.jsonl"),
    )
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    candidates = json.loads(args.input.read_text(encoding="utf-8"))
    results = asyncio.run(crawl_content(candidates, concurrency=args.concurrency))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    counts = {}
    for result in results:
        counts[result["crawl_status"]] = counts.get(result["crawl_status"], 0) + 1
    print(f"content crawled: {len(results)} -> {args.output}; statuses={counts}")


if __name__ == "__main__":
    main()
