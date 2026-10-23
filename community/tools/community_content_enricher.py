"""Add conservative analysis fields to the first cleaned Beijing sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


IMAGE_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
MD_LINK_RE = re.compile(r"\[+\s*([^\[\]]*)\]+\s*\([^)]*\)")
HEADING_LINK_RE = re.compile(r"^#+\s*\[+\s*([^\[\]]+)\]+\s*\([^)]*\)\s*")
BOARD_TAGS = ("幼儿园", "小学", "初中", "高中", "政策")
STAGE_TERMS = ("幼升小", "小升初", "中考", "中招")
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
URL_DATE_RE = re.compile(r"/(20\d{2})(\d{2})(\d{2})\d*\.html(?:$|[?#])")
SCHOOL_RE = re.compile(r"([一-龥]{2,12}(?:小学|中学|附中|附小|学校|校区))")
DISTRICT_NAMES = (
    "海淀",
    "西城",
    "东城",
    "朝阳",
    "丰台",
    "通州",
    "石景山",
    "昌平",
    "大兴",
    "顺义",
    "房山",
    "门头沟",
    "怀柔",
    "平谷",
    "密云",
    "延庆",
    "经开",
)
GLOBAL_NAV_TERMS = ("热门专题", "试卷下载", "网站首页", "首页", "友情链接", "登录", "注册")
BODY_MARKERS = ("摘要", "正文", "来源", "发布时间")
PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _lines(text: str) -> list[str]:
    result = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line and not IMAGE_LINE_RE.match(line):
            result.append(line)
    return result


def recover_forum_subject(record: dict) -> tuple[str, str]:
    """Recover the real thread subject and board tag from a Discuz detail page.

    List pages label thread rows with icon anchors such as
    "有新回复 - 新窗口打开"; the actual subject only appears on the detail
    page as the single top-level heading: a board-type link (小学、初中、
    幼儿园、高中、政策) followed by the subject text. Returns
    (subject, board_tag); the tag classifies the record into a school phase
    when keyword extraction found no stage, and is stripped from the title.
    """
    if record.get("source_id") != "shaoyaojuwang":
        return "", ""
    title = (record.get("title") or "").strip()
    if title and not title.endswith("新窗口打开"):
        return "", ""
    for line in _lines(record.get("content_text_clean", "")):
        if line.startswith("# ") and not line.startswith("## "):
            match = HEADING_LINK_RE.match(line)
            rest = line[match.end():] if match else line
            board_tag = match.group(1).strip() if match else ""
            if board_tag not in BOARD_TAGS:
                board_tag = ""
            subject = MD_LINK_RE.sub(r"\1", rest)
            subject = subject.replace("[", "").replace("]", "").strip()
            if len(subject) >= 6:
                return subject, board_tag
    return "", ""


def extract_body_text(record: dict) -> tuple[str, str, str]:
    """Return body, method and confidence without pretending extraction is perfect."""
    title = (record.get("title") or "").strip()
    lines = _lines(record.get("content_text_clean", ""))
    if not lines:
        return "", "fallback", "low"

    if record.get("source_id") == "xschu":
        summary_indexes = [i for i, line in enumerate(lines) if line == "摘要"]
        if summary_indexes:
            body_lines = lines[summary_indexes[0] + 1 :]
            body_lines = [
                line for line in body_lines
                if sum(term in line for term in GLOBAL_NAV_TERMS) < 2
            ]
            body = "\n".join(body_lines).strip()
            if len(body) >= 30:
                return body, "summary_anchor", "high"

    if record.get("source_id") == "shaoyaojuwang":
        raw = record.get("content_text_clean", "")
        if "发表于" in raw:
            body = raw.split("发表于", 1)[1]
            body = body.split("返回列表", 1)[0]
            body = "\n".join(_lines(body)).strip()
            if len(body) >= 30:
                return body, "forum_post_anchor", "medium"

    title_indexes = [i for i, line in enumerate(lines) if title and title in line]
    if title_indexes:
        article_index = next(
            (
                i for i in title_indexes
                if any(
                    DATE_RE.search(candidate) or "摘要" in candidate or "阅读" in candidate
                    for candidate in lines[i + 1 : i + 6]
                )
            ),
            title_indexes[0],
        )
        start = article_index + 1
        next_title = next((i for i in title_indexes if i > article_index), len(lines))
        body_lines = lines[start:next_title]
        body_lines = [
            line for line in body_lines
            if sum(term in line for term in GLOBAL_NAV_TERMS) < 2
        ]
        # Strip the common article metadata row; keep the summary and article text.
        while body_lines and (body_lines[0] in {"热搜", "摘要", "正文"} or "编辑:" in body_lines[0]):
            body_lines.pop(0)
        body = "\n".join(body_lines).strip()
        if len(body) >= 30:
            return body, "title_anchor", "high"

    # A conservative fallback is preferable to silently deleting the article.
    body = "\n".join(lines).strip()
    nav_count = sum(1 for term in GLOBAL_NAV_TERMS if term in body[:1200])
    confidence = "low" if nav_count >= 2 else "medium"
    return body, "fallback", confidence


def normalize_published_date(record: dict) -> tuple[str, str]:
    link = record.get("link", "")
    match = URL_DATE_RE.search(link)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}", "high"
    hint = str(record.get("published_at_hint") or "")
    match = DATE_RE.search(hint)
    if match and hint not in {"2024/10/08", "2024-10-08"}:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}", "medium"
    return "", "none"


def school_candidates(text: str) -> list[str]:
    candidates = []
    for candidate in SCHOOL_RE.findall(text or ""):
        for district in DISTRICT_NAMES:
            candidate = re.sub(rf"^{re.escape(district)}区", "", candidate)
        if candidate in {"学校", "校区"} or candidate not in candidates:
            if candidate not in {"学校", "校区"}:
                candidates.append(candidate)
    return candidates[:30]


def district_candidates(text: str) -> list[str]:
    result = []
    for name in DISTRICT_NAMES:
        label = f"{name}区" if name != "经开" else "经开区"
        if name in (text or "") and label not in result:
            result.append(label)
    return result


def fingerprint(text: str) -> str:
    normalized = PUNCT_RE.sub("", text or "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


SIDEBAR_MARKERS = ("关键词", "相关推荐", "上一篇", "友情链接")


def stage_candidates(title: str, body: str, previous: list) -> list:
    """学段标签：标题优先，其次正文核心段，最后保留原标签。

    清洗层用"标题 + 整页文本"匹配学段词，而资讯页尾部的相关推荐、
    关键词和友情链接会带来大量跨学段噪声（例如中考分析页的侧栏全是
    小升初链接）。三级取舍：

    1. 标题命中学段词——作者明确锚定了学段，只信标题；
    2. 正文核心段（截掉侧栏标记之后的部分的前 2500 字）命中——
       正文确实在讨论该学段；
    3. 都没有时保留清洗层标签（论坛版块标签等可靠来源）。
    """
    title_hits = [term for term in STAGE_TERMS if term in (title or "")]
    if title_hits:
        return title_hits
    core = body or ""
    for marker in SIDEBAR_MARKERS:
        core = core.split(marker, 1)[0]
    core_hits = [term for term in STAGE_TERMS if term in core[:2500]]
    if core_hits:
        return core_hits
    return list(previous or [])


def enrich_record(record: dict) -> dict:
    recovered_title, board_tag = recover_forum_subject(record)
    if recovered_title:
        record = {**record, "title": recovered_title, "title_recovered": True}
        if board_tag and board_tag != "政策" and not record.get("stage"):
            record = {**record, "stage": [board_tag]}
    body, method, confidence = extract_body_text(record)
    published_at, date_confidence = normalize_published_date(record)
    stage = stage_candidates(record.get("title", ""), body, record.get("stage") or [])
    searchable = f"{record.get('title', '')}\n{body[:6000]}"
    return {
        **record,
        "body_text": body,
        "body_extraction_method": method,
        "body_extraction_confidence": confidence,
        "published_at_normalized": published_at,
        "date_confidence": date_confidence,
        "stage": stage,
        "school_candidates": school_candidates(searchable),
        "district_candidates": district_candidates(searchable),
        "content_fingerprint": fingerprint(f"{record.get('title', '')}\n{body}"),
        "analysis_eligible": bool(record.get("valid_result")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich cleaned Beijing community content")
    parser.add_argument("--input", type=Path, default=Path("community/data/community_beijing_clean.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("community/data/community_beijing_enriched.jsonl"))
    parser.add_argument("--json-output", type=Path, default=Path("community/data/community_beijing_enriched.json"))
    args = parser.parse_args()

    records = []
    with args.input.open(encoding="utf-8") as handle:
        for line in handle:
            records.append(enrich_record(json.loads(line)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    args.json_output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    eligible = sum(record["analysis_eligible"] for record in records)
    unique = len({record["content_fingerprint"] for record in records if record["analysis_eligible"]})
    print(f"enriched: {len(records)} records, eligible={eligible}, unique={unique} -> {args.output}")


if __name__ == "__main__":
    main()
