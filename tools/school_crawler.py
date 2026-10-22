"""Crawl4AI-based probing for public Beijing school websites."""

from __future__ import annotations

import re
import asyncio
import hashlib
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


def _allowed_hosts_for_homepage(homepage: str) -> set[str]:
    parsed = urlparse(homepage)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return set()
    host = parsed.netloc.lower()
    hosts = {host}
    if host.startswith("www."):
        hosts.add(host[4:])
    elif "." in host and host.count(".") == 1:
        hosts.add(f"www.{host}")
    return hosts


def build_school_probe_specs(catalog: dict, homepages: dict) -> list[dict]:
    """Build one Crawl4AI spec per district/school catalog entry."""
    specs = []
    seen = set()
    for district, schools in catalog.items():
        for school in schools:
            key = (district, school)
            if key in seen:
                continue
            seen.add(key)
            homepage = (homepages.get(school) or "").strip()
            enabled = bool(
                homepage
                and not homepage.lower().startswith("javascript:")
                and urlparse(homepage).scheme in {"http", "https"}
                and bool(urlparse(homepage).netloc)
            )
            specs.append(
                {
                    "school": school,
                    "district": district,
                    "homepage": homepage,
                    "allowed_hosts": _allowed_hosts_for_homepage(homepage),
                    "enabled": enabled,
                }
            )
    return specs

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
_DATE_RE = re.compile(r"(?P<year>20\d{2})[-/.年]?(?P<month>\d{1,2})[-/.月]?(?P<day>\d{1,2})日?")
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


def extract_article_links(links: list[dict], section_url: str, limit: int = 10) -> list[dict]:
    """Select a bounded set of same-site detail links from a section page."""
    host = urlparse(section_url).netloc.lower()
    candidates = extract_internal_links(links, section_url, {host})
    results = []
    seen = set()
    for item in candidates:
        title = item["title"]
        if title in {"下一页", "上一页", "更多", "查看详情"}:
            continue
        if not _looks_like_detail_url(item["url"], title):
            continue
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _normalize_date(value: str) -> str | None:
    match = _DATE_RE.search(value or "")
    if not match:
        return None
    return f"{int(match['year']):04d}-{int(match['month']):02d}-{int(match['day']):02d}"


def normalize_school_item(item: dict, spec: dict, source_url: str) -> dict | None:
    """Normalize one detail result without retaining full article text."""
    title = _clean_text(item.get("title") or item.get("text"))
    url = normalize_url(item.get("url") or item.get("href") or "", source_url)
    if not title or not url:
        return None
    date_value = _normalize_date(item.get("date") or item.get("published_at") or "")
    date_source = "page"
    if not date_value:
        date_value = _normalize_date(url)
        date_source = "url"
    if not date_value:
        date_value = datetime.now(timezone.utc).date().isoformat()
        date_source = "crawl"
    summary = _clean_text(item.get("summary") or item.get("markdown") or "")
    return {
        "school": spec["school"],
        "district": spec["district"],
        "category": item.get("category") or "学校动态",
        "title": title,
        "url": url,
        "published_at": date_value,
        "date_source": date_source,
        "source_homepage": spec["homepage"],
        "source_method": "crawl4ai",
        "summary": summary[:240],
        "content_hash": hashlib.sha256(f"{title}\n{url}".encode("utf-8")).hexdigest(),
    }


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
        allowed_hosts = {host.lower() for host in spec.get("allowed_hosts", set())}
        final_host = urlparse(result["final_url"]).netloc.lower()
        if final_host:
            allowed_hosts.add(final_host)
        links = extract_internal_links(
            raw_links,
            result["final_url"],
            allowed_hosts,
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


async def crawl_school_updates(crawler, spec: dict) -> dict:
    """Probe a school, then crawl bounded section and detail pages."""
    health = await probe_school(crawler, spec)
    result = {**health, "updates": []}
    if health["status"] != "success":
        return result
    section_items = []
    for section in health["candidate_sections"][:5]:
        try:
            from crawl4ai import CacheMode, CrawlerRunConfig

            section_result = await crawler.arun(
                url=section["url"],
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    exclude_external_links=True,
                    exclude_social_media_links=True,
                    page_timeout=30000,
                ),
            )
            if not getattr(section_result, "success", False):
                continue
            raw_links = getattr(section_result, "links", {}) or {}
            if isinstance(raw_links, dict):
                raw_links = raw_links.get("internal", [])
            section_items.extend(
                (item, section["title"])
                for item in extract_article_links(raw_links, section["url"], limit=10)
            )
        except Exception:
            continue

    async def crawl_detail(item: dict, category: str) -> dict | None:
        try:
            from crawl4ai import CacheMode, CrawlerRunConfig

            detail_result = await crawler.arun(
                url=item["url"],
                config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=30000),
            )
            if not getattr(detail_result, "success", False):
                return normalize_school_item({**item, "category": category}, spec, item["url"])
            detail_item = {
                **item,
                "category": category,
                "title": getattr(detail_result, "title", "") or item["title"],
                "date": getattr(detail_result, "date", ""),
                "markdown": getattr(detail_result, "markdown", ""),
            }
            return normalize_school_item(detail_item, spec, item["url"])
        except Exception:
            return normalize_school_item({**item, "category": category}, spec, item["url"])

    updates = await asyncio.gather(
        *(crawl_detail(item, category) for item, category in section_items)
    )
    seen = set()
    for update in updates:
        if update and update["url"] not in seen:
            seen.add(update["url"])
            result["updates"].append(update)
    return result
