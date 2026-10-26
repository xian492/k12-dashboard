"""LLM 辅助分类：对规则法低置信的社区条目补充分类。

设计约束（见 docs/设计方案-信息置信度与时效性.md §0）：
- 看板构建（tools/build.py）保持零外部依赖，LLM 不进入构建链路；
- LLM 只跑在本地社区管线（community_pipeline 导出前）；
- 结果按内容哈希缓存（community/data/llm_classify_cache.json），
  重跑管线不重复计费；
- API 不可用/请求失败时，条目回落到规则分类，管线永不因 LLM 失败而中断。

接入：设置环境变量（OpenAI 兼容协议，DashScope/DeepSeek/OpenAI 均可）：
  LLM_CLASSIFY_API_BASE   如 https://api.deepseek.com/v1
  LLM_CLASSIFY_API_KEY
  LLM_CLASSIFY_MODEL      如 deepseek-chat / qwen-plus / gpt-4o-mini
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "llm_classify_cache.json"

# 分类标签空间与规则层保持一致
CONTENT_TYPES = ("政策与流程", "学校动态", "家长经验", "亲子生活", "其他")
STAGES = ("幼儿园", "幼升小", "小学", "小升初", "中学", "初升高", "高中", "高考", "综合")
EVENT_TYPES = (
    "报名", "入学", "派位", "摇号", "划片", "学区", "转学", "招生",
    "录取", "分班", "考试", "竞赛", "培训", "升学", "家庭教育", "",
)

PROMPT = """你是北京K12升学信息看板的分类助手。给社区帖子打分类标签。

分类标准：
- content_type 选一: 政策与流程(升学政策/报名流程/学区规则) | 学校动态(具体学校新闻/招生动作) | 家长经验(升学决策/备考/择校经验) | 亲子生活(日常育儿/阅读/习惯/心理,与升学无直接关系) | 其他(广告/无关)
- stage 选一: 幼儿园 | 幼升小 | 小学 | 小升初 | 中学 | 初升高 | 高中 | 高考 | 综合(跨学段或无学段)
- events 选0-2个: 报名/入学/派位/摇号/划片/学区/转学/招生/录取/分班/考试/竞赛/培训/升学/家庭教育

按标题判断为主，正文为辅。只输出 JSON 数组，每项 {"id":..., "content_type":..., "stage":..., "events":[...]}，不加解释。

帖子列表：
"""

BATCH_SIZE = 20


def _content_hash(record: dict) -> str:
    key = f"{record.get('link', '')}|{record.get('title', '')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )


def _api_config() -> tuple[str, str, str] | None:
    base = os.environ.get("LLM_CLASSIFY_API_BASE", "").rstrip("/")
    key = os.environ.get("LLM_CLASSIFY_API_KEY", "")
    model = os.environ.get("LLM_CLASSIFY_MODEL", "")
    if not (base and key and model):
        return None
    return base, key, model


def _call_llm(base: str, key: str, model: str, prompt: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read())
    return payload["choices"][0]["message"]["content"]


def _parse_response(text: str, expected_ids: list[str]) -> dict[str, dict]:
    """容错解析：剥 markdown 围栏，取 JSON 数组或 {results:[...]}。"""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        data = data.get("results") or data.get("items") or []
    out = {}
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or str(item.get("id")) not in expected_ids:
            continue
        content_type = item.get("content_type")
        stage = item.get("stage")
        events = item.get("events") or []
        if content_type not in CONTENT_TYPES:
            continue
        if stage not in STAGES:
            stage = "综合"
        events = [e for e in events if e in EVENT_TYPES][:2] if isinstance(events, list) else []
        out[str(item["id"])] = {
            "content_type": content_type,
            "stage": stage,
            "events": events,
        }
    return out


def classify_records(records: list[dict]) -> tuple[list[dict], str]:
    """LLM 补充分类。

    只处理调用方传入的低置信条目；每条注入 llm_classified 标记与
    llm_reason 字段（可解释性要求，见设计方案 §4）。
    返回 (更新后的记录列表, 状态描述)。
    """
    config = _api_config()
    if not config:
        return records, "skipped: LLM_CLASSIFY_* 环境变量未设置"
    base, key, model = config
    cache = _load_cache()
    # 只分类低置信且未命中缓存的条目；调用方传全量列表也安全。
    pending = [
        r for r in records
        if needs_llm(r) and _content_hash(r) not in cache
    ]
    newly = {}
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        lines = []
        for index, record in enumerate(batch):
            title = str(record.get("title", ""))[:80]
            body = str(record.get("content_text", "") or "")[:200].replace("\n", " ")
            lines.append(f'{{"id": "{start + index}", "title": "{title}", "body": "{body}"}}')
        prompt = PROMPT + "\n".join(lines)
        expected = [str(start + i) for i in range(len(batch))]
        for attempt in range(2):
            try:
                raw = _call_llm(base, key, model, prompt)
                parsed = _parse_response(raw, expected)
                if parsed:
                    newly.update(parsed)
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError) as e:
                if attempt == 0:
                    time.sleep(2)
                else:
                    print(f"  llm batch failed: {type(e).__name__}: {str(e)[:80]}")
        time.sleep(0.5)
    # 写缓存（含未返回结果的：负面缓存防止反复重试同批噪声）
    for record in pending:
        cache[_content_hash(record)] = newly.get(
            _pending_index(pending, record), {"content_type": None}
        )
    _save_cache(cache)
    # 应用到记录
    applied = 0
    for record in records:
        hit = cache.get(_content_hash(record))
        if not hit or not hit.get("content_type"):
            continue
        record["content_type"] = hit["content_type"]
        if hit.get("stage"):
            record["stage"] = [hit["stage"]]
        if hit.get("events") is not None:
            record["event_type"] = hit["events"]
        record["llm_classified"] = True
        applied += 1
    return records, f"applied {applied}/{len(records)} (cache {len(cache)})"


def _pending_index(pending: list[dict], record: dict) -> str:
    for index, item in enumerate(pending):
        if item is record:
            return str(index)
    return "-1"


def needs_llm(record: dict) -> bool:
    """低置信判定：规则法落在“其他/亲子生活”或无学段的条目交给 LLM。"""
    return (
        record.get("content_type") in ("其他", "亲子生活")
        or not (record.get("stage") or [])
        or record.get("content_type") is None
    )


if __name__ == "__main__":
    import sys

    data_path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "community_enriched.json")
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", [])
    targets = [r for r in records if needs_llm(r)]
    print(f"total {len(records)}, llm targets {len(targets)}")
    updated, status = classify_records(targets)
    print(status)
