"""Adapt community_forum_crawler output into the enriched dashboard record shape.

Input:  ``community/data/community_forum_posts.jsonl``（每帖一条，含 replies）
Output: ``community/data/community_forum_enriched.json``/``.jsonl``，字段与
``community_beijing_enriched.json`` 对齐，可直接与既有北京样本合并后走
``community_dashboard_export.py``。

与既有 cleaner/enricher 的差异：

- 多城市：区县候选按记录 region 选择北京/上海/广州区县表。
- 论坛正文普遍短于资讯页：正文 ≥80 字或评论合计 ≥200 字即视为有内容；
  水木/篱笆仅列表元数据的记录，标题命中教育词也可作为标题级线索入选。
- 日期直接来自帖子页（Discuz/hlgnet 帖内时间），不需要 URL 推断。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

from community_content_cleaner import (
    ACCOUNT_TERMS,
    EXCLUDE_TERMS,
    HOUSING_TERMS,
    PARENT_TERMS,
    POLICY_TERMS,
    RESOURCE_TERMS,
    SCHOOL_TERMS,
)
from community_content_enricher import SCHOOL_RE, fingerprint


DISTRICTS_BY_REGION = {
    "北京": (
        "海淀", "西城", "东城", "朝阳", "丰台", "通州", "石景山", "昌平",
        "大兴", "顺义", "房山", "门头沟", "怀柔", "平谷", "密云", "延庆",
    ),
    "上海": (
        "浦东", "徐汇", "黄浦", "静安", "长宁", "普陀", "虹口", "杨浦",
        "闵行", "宝山", "嘉定", "金山", "松江", "青浦", "奉贤", "崇明",
    ),
    "广州": (
        "越秀", "天河", "海珠", "荔湾", "白云", "黄埔", "番禺", "花都",
        "南沙", "从化", "增城",
    ),
}

DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")

NOISE_TYPES = {"账号与导航", "资源与培训", "房产与生活"}

# 论坛版面常见的导流/营销词，资讯页词表（EXCLUDE_TERMS）未覆盖
FORUM_EXCLUDE_TERMS = (
    "扫码",
    "入群",
    "交流群",
    "微信群",
    "群二维码",
    "公众号",
    "免费领",
    "团购",
    "团课",
    "刷题班",
    "辅导班",
    "优惠券",
    "福利社",
    "抽奖",
    "征婚",
    "招聘",
)

# 老帖护栏：2024 年前的帖子只有标题命中明确升学词才保留
STALE_YEAR = 2024
STALE_TITLE_TERMS = POLICY_TERMS + SCHOOL_TERMS


def _hits(text: str, terms) -> list[str]:
    return [term for term in terms if term in text]


def _classify(title: str, signal_text: str) -> str:
    if _hits(title, ACCOUNT_TERMS):
        return "账号与导航"
    if _hits(title, HOUSING_TERMS) or _hits(title, RESOURCE_TERMS):
        return "噪声"
    if _hits(title, PARENT_TERMS) or _hits(signal_text[:400], PARENT_TERMS):
        return "家长经验"
    if _hits(title, SCHOOL_TERMS) or _hits(signal_text[:400], SCHOOL_TERMS):
        return "学校动态"
    if _hits(title, POLICY_TERMS) or _hits(signal_text[:400], POLICY_TERMS):
        return "政策与流程"
    if _hits(signal_text, PARENT_TERMS):
        return "家长经验"
    if _hits(signal_text, SCHOOL_TERMS):
        return "学校动态"
    if _hits(signal_text, POLICY_TERMS):
        return "政策与流程"
    return "其他"


def _normalize_date(raw: str) -> str:
    match = DATE_RE.search(raw or "")
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _district_candidates(text: str, region: str) -> list[str]:
    names = DISTRICTS_BY_REGION.get(region, ())
    return [f"{name}区" for name in names if name in text][:8]


def _school_candidates(text: str) -> list[str]:
    candidates = []
    for candidate in SCHOOL_RE.findall(text or ""):
        if candidate in {"学校", "校区"} or candidate in candidates:
            continue
        candidates.append(candidate)
    return candidates[:30]


def adapt_record(record: dict) -> dict:
    from community_stage import classify_stage, relevant_forum

    title = (record.get("title") or "").strip()
    main = (record.get("content_text") or "").strip()
    replies = record.get("replies") or []
    reply_text = "\n".join((reply.get("content_text") or "") for reply in replies)
    signal_text = f"{title}\n{main}\n{reply_text}"

    content_type = _classify(title, signal_text)
    exclude_hits = _hits(signal_text, EXCLUDE_TERMS + FORUM_EXCLUDE_TERMS)
    status = record.get("crawl_status", "")
    has_content = status == "success" and (len(main) >= 80 or len(reply_text) >= 200)
    # 相关性只看标题：正文出现一次"家长"不算教育信号（拦律师/生活杂帖）
    title_relevant = relevant_forum(title)
    # 水木/篱笆的列表级记录没有正文；标题命中教育词即标题级线索
    title_only_lead = status.startswith("list_only") and title_relevant
    year_match = DATE_RE.search(record.get("published_at", "") or "")
    stale = bool(year_match) and int(year_match.group(1)) < STALE_YEAR
    fresh_enough = not stale or bool(_hits(title, STALE_TITLE_TERMS))
    valid = (
        (has_content or title_only_lead)
        and title_relevant
        and fresh_enough
        and content_type not in NOISE_TYPES
        and content_type != "噪声"
        and not exclude_hits
    )

    stage = classify_stage(title, signal_text[:2500], board=record.get("board", ""))
    return {
        "title": title,
        "link": record.get("url", ""),
        "source": record.get("source", ""),
        "source_id": record.get("source_id", ""),
        "region": record.get("region", ""),
        "board": record.get("board", ""),
        "reply_count": record.get("reply_count", 0),
        "author": record.get("author", ""),
        "published_at_normalized": _normalize_date(record.get("published_at", "")),
        "date_confidence": "high" if status == "success" else "medium",
        "content_type": content_type if content_type != "噪声" else "资源与培训",
        "stage": stage,
        "event_type": _hits(signal_text, POLICY_TERMS + SCHOOL_TERMS)[:8],
        "district_candidates": _district_candidates(signal_text, record.get("region", "")),
        "school_candidates": _school_candidates(signal_text[:6000]),
        "content_fingerprint": fingerprint(f"{title}\n{main}"),
        "valid_result": valid,
        "analysis_eligible": valid,
        "crawl_status": status,
        "content_chars": record.get("content_chars", 0),
        "crawled_at": record.get("crawled_at", ""),
        "exclude_hits": exclude_hits,
        "list_only_lead": title_only_lead,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Adapt forum crawl output for the dashboard pipeline")
    parser.add_argument("--input", type=Path, default=Path("community/data/community_forum_posts.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("community/data/community_forum_enriched.jsonl"))
    parser.add_argument("--json-output", type=Path, default=Path("community/data/community_forum_enriched.json"))
    args = parser.parse_args()

    records = []
    with args.input.open(encoding="utf-8") as handle:
        for line in handle:
            records.append(adapt_record(json.loads(line)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    args.json_output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    eligible = sum(1 for record in records if record["analysis_eligible"])
    leads = sum(1 for record in records if record["list_only_lead"])
    print(f"adapted: {len(records)} records, eligible={eligible} (title-only leads={leads}) -> {args.output}")


if __name__ == "__main__":
    main()
