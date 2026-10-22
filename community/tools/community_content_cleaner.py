"""Rule-based normalization for the first Beijing community content sample."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SOURCE_IDS = {"xscxx", "xschu", "shaoyaojuwang"}
EXCLUDE_TERMS = (
    "课程",
    "课程包",
    "培训",
    "补课",
    "家教",
    "试卷",
    "答案",
    "资料下载",
    "免费资料",
    "网盘",
    "加微信",
    "进群",
    "群二维码",
    "房价",
    "卖房",
    "租房",
    "招聘",
    "征婚",
)
ACCOUNT_TERMS = ("登录", "注册", "用户查询", "论坛规则", "网站首页", "友情链接")
RESOURCE_TERMS = ("课程", "培训", "补课", "家教", "试卷", "答案", "资料", "下载")
HOUSING_TERMS = ("房价", "卖房", "租房", "学区房", "装修", "楼盘")
PARENT_TERMS = ("家长", "家长反馈", "经验", "分享", "报到", "住宿", "分班", "校服", "食堂")
SCHOOL_TERMS = ("新校区", "校区", "学校建设", "开放日", "校园", "招生", "录取", "校额到校")
POLICY_TERMS = (
    "报名",
    "入学",
    "派位",
    "摇号",
    "划片",
    "学区",
    "转学",
    "学位",
    "招生",
    "录取",
    "小升初",
    "幼升小",
    "中考",
    "中招",
)
EVENT_TERMS = {
    "报名": "报名",
    "入学": "入学",
    "派位": "派位",
    "摇号": "摇号",
    "划片": "划片",
    "学区": "学区",
    "转学": "转学",
    "学位": "学位",
    "招生": "招生",
    "录取": "录取",
    "分班": "分班",
    "住宿": "校园生活",
    "开放日": "校园活动",
    "新校区": "学校建设",
    "校额到校": "校额到校",
}
IMAGE_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
SPACE_RE = re.compile(r"\s+")


def _text(record: dict) -> str:
    return f"{record.get('title', '')}\n{record.get('content_text', '')}"


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _clean_body(text: str) -> str:
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or IMAGE_LINE_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _content_type(record: dict, text: str) -> str:
    title = record.get("title", "")
    status = record.get("crawl_status", "")
    if status != "success" or _hits(title, ACCOUNT_TERMS):
        return "账号与导航"
    if (
        record.get("source_id") == "xscxx"
        and not re.search(r"/\d{8,}\.html(?:$|[?#])", record.get("link", ""))
    ):
        return "账号与导航"
    signal_text = f"{title}\n{text[:1200]}"
    if _hits(title, HOUSING_TERMS):
        return "房产与生活"
    if _hits(title, RESOURCE_TERMS):
        return "资源与培训"
    if _hits(title, PARENT_TERMS):
        return "家长经验"
    if _hits(title, SCHOOL_TERMS):
        return "学校动态"
    if _hits(title, POLICY_TERMS):
        return "政策与流程"
    if _hits(signal_text, HOUSING_TERMS):
        return "房产与生活"
    if _hits(signal_text, PARENT_TERMS):
        return "家长经验"
    if _hits(signal_text, SCHOOL_TERMS):
        return "学校动态"
    if _hits(signal_text, POLICY_TERMS):
        return "政策与流程"
    return "其他"


def clean_record(record: dict) -> dict:
    text = _text(record)
    content_type = _content_type(record, text)
    body = _clean_body(record.get("content_text", ""))
    title = record.get("title", "")
    signal_text = f"{title}\n{body[:1200]}"
    exclude_hits = _hits(signal_text, EXCLUDE_TERMS)
    education_hits = _hits(signal_text, POLICY_TERMS + SCHOOL_TERMS + PARENT_TERMS)
    section_page = (
        record.get("source_id") == "xscxx"
        and not re.search(r"/\d{8,}\.html(?:$|[?#])", record.get("link", ""))
    )
    shaoyao_section_page = (
        record.get("source_id") == "shaoyaojuwang"
        and not re.search(r"/thread-\d+-\d+-\d+\.html(?:$|[?#])", record.get("link", ""))
    )
    valid = (
        record.get("crawl_status") == "success"
        and len(body) >= 200
        and bool(education_hits)
        and content_type not in {"账号与导航", "资源与培训", "房产与生活"}
        and not section_page
        and not shaoyao_section_page
    )
    event_type = [label for term, label in EVENT_TERMS.items() if term in text]
    region = record.get("region", "")
    return {
        **record,
        "content_text_clean": body,
        "content_type": content_type,
        "exclude_hits": exclude_hits,
        "valid_result": valid,
        "region_confidence": "high" if region == "北京" else "low",
        "stage": [term for term in ("幼升小", "小升初", "中考", "中招") if term in text],
        "event_type": list(dict.fromkeys(event_type)),
        "needs_official_verification": valid and content_type in {"政策与流程", "学校动态", "家长经验"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean the first Beijing community content sample")
    parser.add_argument("--input", type=Path, default=Path("community/data/community_beijing_content.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("community/data/community_beijing_clean.jsonl"))
    parser.add_argument("--json-output", type=Path, default=Path("community/data/community_beijing_clean.json"))
    args = parser.parse_args()

    records = []
    with args.input.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("source_id") in SOURCE_IDS:
                records.append(clean_record(record))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    args.json_output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    valid = sum(1 for record in records if record["valid_result"])
    print(f"cleaned: {len(records)} records, valid={valid} -> {args.output}")


if __name__ == "__main__":
    main()
