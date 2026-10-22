"""One-pass Crawl4AI audit report for public community sources."""

from __future__ import annotations

import argparse
import asyncio
import re
import time
from datetime import datetime, timezone
from pathlib import Path


MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
BLOCKED_MARKERS = (
    "anti-bot",
    "blocked",
    "captcha",
    "cloudflare",
    "access denied",
    "需要登录",
    "请登录",
)


def extract_sources(markdown: str) -> list[dict]:
    """Extract unique HTTP(S) Markdown links while preserving document order."""
    sources = []
    seen = set()
    major_section = ""
    minor_section = ""
    for line in markdown.splitlines():
        heading = re.match(r"^(#{2,3})\s+(.+?)\s*$", line.strip())
        if heading:
            if len(heading.group(1)) == 2:
                major_section = heading.group(2)
                minor_section = ""
            else:
                minor_section = heading.group(2)
            continue
        for label, url in MARKDOWN_LINK_RE.findall(line):
            if url in seen:
                continue
            seen.add(url)
            source = {"label": label.strip(), "url": url}
            category = " / ".join(part for part in (major_section, minor_section) if part)
            if category:
                source["category"] = category
            sources.append(source)
    return sources


def classify_result(*, success: bool, markdown: str, links: int, error: str) -> str:
    error_lower = (error or "").lower()
    markdown_lower = (markdown or "").lower()
    if "404 not found" in markdown_lower or "page not found" in markdown_lower:
        return "failed"
    if any(marker in error_lower for marker in BLOCKED_MARKERS):
        return "blocked"
    if not success:
        return "failed"
    if not markdown.strip() and not links:
        return "empty"
    return "success"


def _markdown_text(markdown) -> str:
    if markdown is None:
        return ""
    raw = getattr(markdown, "raw_markdown", None)
    if raw is not None:
        return str(raw)
    return str(markdown)


async def inspect_source(crawler, source: dict, semaphore: asyncio.Semaphore) -> dict:
    from crawl4ai import CacheMode, CrawlerRunConfig

    started = time.monotonic()
    try:
        async with semaphore:
            result = await crawler.arun(
                url=source["url"],
                config=CrawlerRunConfig(
                    # This is an audit report: each run must reflect the current
                    # public response, not a previous cached page or error.
                    cache_mode=CacheMode.BYPASS,
                    exclude_external_links=True,
                    exclude_social_media_links=True,
                ),
            )
        markdown = _markdown_text(getattr(result, "markdown", ""))
        links = len((getattr(result, "links", {}) or {}).get("internal", []))
        error = str(getattr(result, "error_message", "") or "")
        status = classify_result(
            success=bool(getattr(result, "success", False)),
            markdown=markdown,
            links=links,
            error=error,
        )
        return {
            **source,
            "status": status,
            "http_status": getattr(result, "status_code", None),
            "markdown_chars": len(markdown),
            "internal_links": links,
            "preview": " ".join(markdown.split())[:180],
            "error": error[:240],
            "seconds": round(time.monotonic() - started, 2),
        }
    except Exception as exc:
        error = str(exc)
        return {
            **source,
            "status": classify_result(success=False, markdown="", links=0, error=error),
            "http_status": None,
            "markdown_chars": 0,
            "internal_links": 0,
            "preview": "",
            "error": error[:240],
            "seconds": round(time.monotonic() - started, 2),
        }


async def crawl_sources(sources: list[dict], concurrency: int = 4) -> list[dict]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig
    except ImportError as exc:
        raise RuntimeError(
            "Crawl4AI is not installed in this Python environment. "
            "Activate .venv or install Crawl4AI before running the report."
        ) from exc

    semaphore = asyncio.Semaphore(concurrency)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        return await asyncio.gather(
            *(inspect_source(crawler, source, semaphore) for source in sources)
        )


def _cell(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _source_link(result: dict) -> str:
    return f"[{_cell(result['label'])}]({result['url']})"


def _url_link(result: dict) -> str:
    return f"[{result['url']}]({result['url']})"


STATUS_LABELS = {
    "success": "成功",
    "empty": "空页面",
    "blocked": "受限/反爬",
    "failed": "请求失败",
}


def _percentage(value: int, total: int) -> str:
    return f"{value / total:.1%}" if total else "0.0%"


def _result_reason(result: dict) -> str:
    if result.get("error"):
        return result["error"]
    if result.get("status") == "success":
        return "入口有可见正文或内部链接，可继续做分页/详情页抓取。"
    if result.get("status") == "empty":
        return "请求成功，但当前页面没有提取到正文和内部链接。"
    return "未提供具体原因。"


def render_report(results: list[dict], source_doc: str, generated_at: str) -> str:
    counts = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    total = len(results)
    successful = [result for result in results if result["status"] == "success"]
    high_value = sorted(
        successful,
        key=lambda result: (result.get("internal_links", 0), result.get("markdown_chars", 0)),
        reverse=True,
    )[:8]
    special_parse = [
        result
        for result in successful
        if result.get("internal_links", 0) == 0 or result.get("markdown_chars", 0) < 500
    ]
    blocked = [result for result in results if result["status"] == "blocked"]
    failed = [result for result in results if result["status"] == "failed"]

    lines = [
        "# 社区信源一次性巡检报告",
        "",
        f"> 生成时间：{generated_at}。本报告对《{source_doc}》中的公开入口各抓取一次，重点判断入口是否可访问、页面是否有可读内容、是否暴露内部链接，以及后续是否值得继续做分页和详情页抓取。",
        "",
        "## 一、结论摘要",
        "",
        f"本次共检查 **{total}** 个去重入口，其中 **{counts.get('success', 0)} 个（{_percentage(counts.get('success', 0), total)}）可以继续抓取**，**{counts.get('blocked', 0)} 个（{_percentage(counts.get('blocked', 0), total)}）受到访问限制**，**{counts.get('failed', 0)} 个（{_percentage(counts.get('failed', 0), total)}）请求失败**。",
        "",
        "> 注意：入口巡检成功不等于内容质量已验证，也不等于已经抓完该社区的全部历史帖子、分页和回复。",
        "",
        "### 主要判断",
        "",
        f"- **可继续深挖**：有正文或内部链接的入口共 {len(successful)} 个；其中内部链接较多的来源适合优先配置分页和详情页抓取。",
        f"- **需要专用解析**：有 {len(special_parse)} 个入口虽然返回成功，但链接很少或页面更像结构化导航，不能直接套用论坛列表解析。",
        f"- **访问受限**：有 {len(blocked)} 个入口触发反爬、验证码、登录或页面内容不足提示。",
        f"- **请求失败**：有 {len(failed)} 个入口发生超时或浏览器导航错误，需要单独复查网络和站点状态。",
        "",
        "## 二、结果分组",
        "",
        "### 优先继续抓取的入口",
        "",
        "| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 适合的下一步 |",
        "|---|---|---|---:|---:|---|",
    ]
    for result in high_value:
        lines.append(
            "| " + " | ".join(
                _cell(value)
                for value in (
                    result["label"],
                    _url_link(result),
                    STATUS_LABELS.get(result["status"], result["status"]),
                    result.get("markdown_chars", 0),
                    result.get("internal_links", 0),
                    "配置分页和帖子详情页抓取",
                )
            ) + " |"
        )
    lines.extend(
        [
            "",
            "### 需要专用解析的入口",
            "",
            "| 社区/名称 | 原始链接 | 页面特征 | 建议 |",
            "|---|---|---|---|",
        ]
    )
    for result in special_parse:
        suggestion = "解析页面内嵌数据或正文结构" if result.get("internal_links", 0) == 0 else "检查页面结构后配置专用选择器"
        lines.append(
            f"| {_cell(result['label'])} | {_url_link(result)} | {_cell(result.get('markdown_chars', 0))} 字符、{_cell(result.get('internal_links', 0))} 个内部链接 | {suggestion} |"
        )
    if not special_parse:
        lines.append("| 无 | — | — |")
    lines.extend(
        [
            "",
            "### 受限或失败的入口",
            "",
            "| 社区/名称 | 原始链接 | 状态 | 原因 |",
            "|---|---|---|---|",
        ]
    )
    for result in blocked + failed:
        lines.append(
            f"| {_cell(result['label'])} | {_url_link(result)} | {STATUS_LABELS.get(result['status'], result['status'])} | {_cell(_result_reason(result)[:240])} |"
        )
    if not blocked and not failed:
        lines.append("| 无 | — | — |")
    lines.extend(
        [
            "",
            "### 状态定义",
            "",
            "| 状态 | 含义 |",
            "|---|---|",
            "| success | 入口成功返回可见内容或内部链接 |",
            "| empty | 请求成功但没有可提取正文和内部链接 |",
            "| blocked | 命中反爬、验证码、登录或访问拒绝提示 |",
            "| failed | 请求或浏览器执行失败 |",
            "",
            "## 三、来源明细",
            "",
            "以下按原信源文档的章节归类。名称本身就是可点击的原始入口，便于直接回到社区页面。",
            "",
        ]
    )
    grouped = {}
    for result in results:
        grouped.setdefault(result.get("category", "未分类"), []).append(result)
    for category, category_results in grouped.items():
        lines.extend(
            [
                f"### {_cell(category)}",
                "",
                "| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |",
                "|---|---|---|---:|---:|---:|---|",
            ]
        )
        for result in category_results:
            lines.append(
                "| " + " | ".join(
                    _cell(value)
                    for value in (
                        result["label"],
                        _url_link(result),
                        STATUS_LABELS.get(result["status"], result["status"]),
                        result.get("markdown_chars", 0),
                        result.get("internal_links", 0),
                        f"{result.get('seconds', 0):.2f}s",
                        _result_reason(result)[:160],
                    )
                ) + " |"
            )
        lines.append("")
    lines.extend(
        [
            "## 四、后续建议",
            "",
            "1. 先对“优先继续抓取”的入口增加分页和详情页抓取，形成统一的帖子记录。",
            "2. 对水木社区、升学索引等结构特殊的来源单独编写解析器，不用通用论坛规则硬套。",
            "3. 对受限来源保留人工入口，不尝试绕过验证码、登录或反爬。",
            "4. 对成功入口增加发布时间、标题、正文、作者、回复数和原始链接字段，再进行去重和增量更新。",
            "",
            "## 五、范围说明",
            "",
            "本次只巡检文档中明确列出的公开入口，不自动登录、不绕过验证码、不抓取私密群组，也没有递归抓取每个入口下的全部分页和文章详情。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit all public community links in a Markdown source document")
    parser.add_argument("--source", type=Path, default=Path("docs/论坛与社区信源.md"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/community-source-report-2026-10-22.md"),
    )
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    sources = extract_sources(args.source.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    results = asyncio.run(crawl_sources(sources, concurrency=max(1, args.concurrency)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_report(results, str(args.source), generated_at), encoding="utf-8"
    )
    print(f"reported: {len(results)} sources -> {args.output}")


if __name__ == "__main__":
    main()
