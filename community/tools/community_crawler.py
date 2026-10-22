"""Crawl4AI-backed collector for public Beijing K12 community sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse


BEIJING_SOURCES = [
    {
        "id": "xschu",
        "name": "北京小升初网",
        "url": "https://www.xschu.com/zhengcezixun/",
    },
    {
        "id": "newsmth-child-education",
        "name": "水木社区·儿童教育",
        "url": "https://www.newsmth.net/nForum/board/ChildEducation",
    },
    {
        "id": "xscxx",
        "name": "北京小升初信息网",
        "url": "https://www.xscxx.com/xiaoshengchu/",
    },
    {
        "id": "hlgnet",
        "name": "回龙观社区网",
        "url": "https://bbs.hlgnet.com/frame.php?bbscate=0&boardid=1",
    },
    {
        "id": "shaoyaojuwang",
        "name": "芍药居社区网",
        "url": "https://www.shaoyaojuwang.com/forum-6-1.html",
    },
    {
        "id": "xiaoshengchu-index",
        "name": "北京小升初升学索引",
        "url": "https://xiaoshengchu.org/",
    },
]

INCLUDE_TERMS = (
    "幼升小",
    "小升初",
    "初升高",
    "中考",
    "中招",
    "招生",
    "报名",
    "入学",
    "录取",
    "派位",
    "摇号",
    "划片",
    "学区",
    "转学",
    "学位",
    "开放日",
    "家长会",
    "分班",
    "住宿",
    "校额到校",
    "指标生",
    "新校区",
    "学校",
)

EXCLUDE_TERMS = (
    "资料领取",
    "免费资料",
    "加微信",
    "加好友",
    "群二维码",
    "交流群",
    "社群",
    "进群",
    "扫码",
    "课程包",
    "培训班",
    "补课",
    "家教",
    "房价",
    "卖房",
    "租房",
    "学区房",
    "招聘",
    "征婚",
    "联系我们",
    "网站首页",
    "学校简介",
    "学校概况",
    "学校首页",
    "友情链接",
)

_SPACE_RE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value or "").strip()


def _matches(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def normalize_link(link: dict, source: dict) -> dict:
    """Normalize one Crawl4AI internal-link record into dashboard-neutral JSON."""
    title = _clean_text(link.get("text") or link.get("title"))
    href = urljoin(source["url"], (link.get("href") or link.get("url") or "").strip())
    return {
        "title": title,
        "link": href,
        "source_id": source["id"],
        "source": source["name"],
        "region": "北京",
        "tags": _matches(title, INCLUDE_TERMS),
    }


def _is_public_internal_link(link: str, source: dict) -> bool:
    parsed = urlparse(link)
    source_host = urlparse(source["url"]).netloc
    return parsed.scheme in {"http", "https"} and parsed.netloc == source_host


def extract_candidate_links(links: list[dict], source: dict) -> list[dict]:
    """Keep public links unless they match explicit noise terms.

    INCLUDE_TERMS are intentionally advisory in this first pass. They are
    recorded as tags but do not decide whether a community link is retained.
    """
    results = []
    seen = set()
    for raw_link in links:
        item = normalize_link(raw_link, source)
        if not item["title"] or not _is_public_internal_link(item["link"], source):
            continue
        if _matches(item["title"], EXCLUDE_TERMS):
            continue
        if item["link"] in seen:
            continue
        seen.add(item["link"])
        results.append(item)
    return results


async def crawl_source(crawler, source: dict) -> list[dict]:
    """Crawl one public source page using an already-created Crawl4AI crawler."""
    from crawl4ai import CacheMode, CrawlerRunConfig

    result = await crawler.arun(
        url=source["url"],
        config=CrawlerRunConfig(
            cache_mode=CacheMode.ENABLED,
            exclude_external_links=True,
            exclude_social_media_links=True,
        ),
    )
    if not result.success:
        return []
    discovered_at = datetime.now(timezone.utc).isoformat()
    items = extract_candidate_links(result.links.get("internal", []), source)
    for item in items:
        item["discovered_at"] = discovered_at
    return items


async def crawl_beijing(output: Path) -> list[dict]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig
    except ImportError as exc:
        raise RuntimeError(
            "Crawl4AI is not installed in this Python environment. "
            "Install it with `pip install -U crawl4ai` and run `crawl4ai-setup`."
        ) from exc

    all_items = []
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        for source in BEIJING_SOURCES:
            try:
                all_items.extend(await crawl_source(crawler, source))
            except Exception as exc:
                print(f"source failed: {source['id']}: {exc}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl public Beijing K12 community sources")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("community/data/community_beijing.json"),
        help="output JSON path",
    )
    args = parser.parse_args()
    items = asyncio.run(crawl_beijing(args.output))
    print(f"crawled: Beijing community links {len(items)} -> {args.output}")


if __name__ == "__main__":
    main()
