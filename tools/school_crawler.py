"""Crawl4AI-based probing for public Beijing school websites."""

from __future__ import annotations

import re
import asyncio
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse


SCHOOL_PROBE_SPECS = [
    {
        "school": "人大附中",
        "district": "海淀区",
        "homepage": "https://www.rdfz.cn/",
        "allowed_hosts": {"www.rdfz.cn", "rdfz.cn"},
    },
    {
        "school": "清华附中",
        "district": "海淀区",
        "homepage": "https://www.qhfz.edu.cn/",
        "allowed_hosts": {"www.qhfz.edu.cn", "qhfz.edu.cn"},
    },
    {
        "school": "首师大附中",
        "district": "海淀区",
        "homepage": "https://www.cnuhs.cn/",
        "allowed_hosts": {"www.cnuhs.cn", "cnuhs.cn"},
    },
    {
        "school": "一零一中学",
        "district": "海淀区",
        "homepage": "https://www.beijing101.com/",
        "allowed_hosts": {"www.beijing101.com", "beijing101.com"},
    },
    {
        "school": "八一学校",
        "district": "海淀区",
        "homepage": "https://byxx.bjhdedu.cn/",
        "allowed_hosts": {"byxx.bjhdedu.cn"},
    },
    {
        "school": "交大附中",
        "district": "海淀区",
        "homepage": "https://jdfz.bjhdedu.cn/",
        "allowed_hosts": {"jdfz.bjhdedu.cn"},
    },
]

SECTION_TERMS = (
    "新闻",
    "通知",
    "公告",
    "招生",
    "校园动态",
    "校园新闻",
    "学校新闻",
    "信息公开",
)

EXCLUDED_TERMS = (
    "首页",
    "学校简介",
    "学校概况",
    "联系我们",
    "友情链接",
    "备案",
    "登录",
    "招聘",
    "版权",
)

_SPACE_RE = re.compile(r"\s+")
_DETAIL_PATH_RE = re.compile(
    r"(?:^|/)\d{6,8}(?:/|$)|(?:^|/)t?\d{8}(?:_|\.|/)|/\d{1,4}/\d{3,6}\.(?:html?|shtml)$"
)


def _clean_text(value: str | None) -> str:
    return _SPACE_RE.sub(" ", value or "").strip()


def normalize_url(raw_url: str, base_url: str) -> str:
    """Resolve a link and remove fragments while retaining query parameters."""
    resolved = urljoin(base_url, (raw_url or "").strip())
    resolved, _ = urldefrag(resolved)
    parsed = urlparse(resolved)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _is_allowed_host(url: str, allowed_hosts: set[str]) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in allowed_hosts


def _is_excluded_title(title: str) -> bool:
    return any(term in title for term in EXCLUDED_TERMS)


def _looks_like_detail_url(url: str, title: str) -> bool:
    path = urlparse(url).path.lower()
    if len(title) >= 28:
        return True
    return bool(_DETAIL_PATH_RE.search(path))


def extract_internal_links(
    links: list[dict], base_url: str, allowed_hosts: set[str]
) -> list[dict]:
    """Return unique, public, same-site links with usable titles."""
    results = []
    seen = set()
    normalized_hosts = {host.lower() for host in allowed_hosts}
    for link in links:
        title = _clean_text(link.get("text") or link.get("title"))
        url = normalize_url(link.get("href") or link.get("url") or "", base_url)
        if not title or not _is_allowed_host(url, normalized_hosts):
            continue
        if _is_excluded_title(title) or url in seen:
            continue
        seen.add(url)
        results.append({"title": title, "url": url})
    return results


def rank_section_candidates(links: list[dict]) -> list[dict]:
    """Keep likely content sections and order stronger keyword matches first."""
    candidates = []
    for index, link in enumerate(links):
        title = _clean_text(link.get("title") or link.get("text"))
        if not title or _is_excluded_title(title):
            continue
        if _looks_like_detail_url(link["url"], title):
            continue
        score = sum(1 for term in SECTION_TERMS if term in title)
        if score:
            candidates.append((score, index, {"title": title, "url": link["url"]}))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in candidates]


def _make_crawler():
    from crawl4ai import AsyncWebCrawler

    return AsyncWebCrawler()


async def probe_school(crawler, spec: dict) -> dict:
    """Probe one school homepage and return a failure-safe health report."""
    checked_at = datetime.now(timezone.utc).isoformat()
    result = {
        "school": spec["school"],
        "district": spec["district"],
        "homepage": spec["homepage"],
        "final_url": spec["homepage"],
        "status": "failed",
        "candidate_sections": [],
        "items_found": 0,
        "error": "",
        "checked_at": checked_at,
    }
    try:
        from crawl4ai import CacheMode, CrawlerRunConfig

        crawl_result = await crawler.arun(
            url=spec["homepage"],
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                exclude_external_links=True,
                exclude_social_media_links=True,
                page_timeout=30000,
            ),
        )
        result["final_url"] = getattr(crawl_result, "url", None) or spec["homepage"]
        if not getattr(crawl_result, "success", False):
            result["error"] = getattr(crawl_result, "error_message", "crawl failed") or "crawl failed"
            return result
        raw_links = getattr(crawl_result, "links", {}) or {}
        if isinstance(raw_links, dict):
            raw_links = raw_links.get("internal", [])
        links = extract_internal_links(
            raw_links,
            result["final_url"],
            set(spec.get("allowed_hosts", set())),
        )
        result["candidate_sections"] = rank_section_candidates(links)[:5]
        result["items_found"] = len(result["candidate_sections"])
        result["status"] = "success"
    except Exception as exc:  # noqa: BLE001 - one bad site must not stop the batch
        result["error"] = str(exc)
    return result


async def probe_schools(specs: list[dict]) -> list[dict]:
    """Probe a batch with bounded concurrency and per-school isolation."""
    semaphore = asyncio.Semaphore(3)

    async with _make_crawler() as crawler:
        async def run_one(spec: dict) -> dict:
            async with semaphore:
                return await probe_school(crawler, spec)

        return await asyncio.gather(*(run_one(spec) for spec in specs))
