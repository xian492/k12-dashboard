#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K12 官方信源看板构建脚本 v2。

信源（25 路）：
1. yjrx 18 区招生政策 JSON 接口
2. 北京市教委通知公告（官网列表页解析）
3. 教育部公告公示（官网列表页解析）
4. 校级：人大附中通知公告 + 招生资讯、清华附中招生专栏（官网解析）

v2 升级（解决 v1 纯链接平铺问题）：
- 每条信息自动打标签（入学政策/招生简章/审核细则/通知公告/其他）并生成一句话要点
- 布局改为摘要优先：每路信源卡片显示「最新动态」摘要行，旧条目折叠
- data.json 与上次快照 diff，新增条目打 NEW 徽章

用法：python3 build.py（无第三方依赖）
"""
import json
import re
import ssl
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

DISTRICTS = {
    "东城区": "e84eb33d8d5062933ab3bf3e7a37acb5",
    "西城区": "de2599415bc9f2a48110859f4e973e96",
    "朝阳区": "e8cc3c21eb88fbde7781fb5f21e436e4",
    "海淀区": "74e3d283b5f295df7647561e2df7b583",
    "丰台区": "e7db49a3850de47674a9bf7f71c8c69d",
    "石景山区": "85d3d957639fe5e4a6facb8dad0d3430",
    "门头沟区": "190ce81f6e5d6ebeb7b0b39181c22f49",
    "房山区": "84b1313554b883c852e6486b5cde3ed8",
    "通州区": "14b10256a87dc2435b7941aa5bc26f60",
    "顺义区": "52a020fcec213bb8cfc12de6c599b126",
    "昌平区": "fe1ada1cac784a209e8718f521c97afb",
    "大兴区": "bdf89e0651429eda155421d6ce98f5d2",
    "平谷区": "f54e9a0d0b90724a1ec7b47b0ea8fe28",
    "怀柔区": "befcfdf69d43807b4919a79c25d11a52",
    "密云区": "2422496aa8597ab6585f95b01d529602",
    "延庆区": "68583790ba5e15b072902e3e57297242",
    "燕山地区": "e835141af2396c12c563620073f4c25b",
    "经济技术开发区": "779cf55da96380347589642668fc439a",
}

YJRX_JSON = "https://yjrx.bjedu.cn/uploads/json/{}.json"
YJRX_ITEM_URL = "https://yjrx.bjedu.cn{}"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CTX = ssl.create_default_context()


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


# ---------- 要点提炼 ----------

TAG_RULES = [
    ("入学政策", [r"入学工作", r"入学.{0,4}意见", r"实施细则", r"入学方案", r"招生办法"]),
    ("招生简章", [r"招生简章", r"特长生", r"报名通知", r"信息采集", r"采集通知"]),
    ("审核细则", [r"审核细则", r"审核办法", r"材料审核"]),
    ("入学问答", [r"问答", r"答疑"]),
    ("通知公告", [r"通知", r"公告", r"公示", r"名单", r"方案", r"启事"]),
]

KEY_POINT_PATTERNS = [
    (r"(\d{4})年?", "【{y}年度】"),
    (r"(海淀区|西城区|东城区|朝阳区|丰台区|石景山区|通州区|大兴区|昌平区|顺义区|房山区|门头沟区|平谷区|怀柔区|密云区|延庆区|经开区)", "【{d}】"),
]


def tag_of(title: str) -> str:
    for tag, patterns in TAG_RULES:
        if any(re.search(p, title) for p in patterns):
            return tag
    return "其他"


def key_point(title: str) -> str:
    """从标题提炼要点：年份 + 区名 + 类型标签。"""
    parts = []
    m = re.search(r"(20\d{2})", title)
    if m:
        parts.append(m.group(1) + "年")
    for tag, patterns in TAG_RULES:
        if any(re.search(p, title) for p in patterns):
            parts.append(tag)
            break
    return " · ".join(parts) if parts else "常规通知"


# ---------- 信源拉取 ----------

def fetch_yjrx() -> dict:
    result = {}
    for name, fid in DISTRICTS.items():
        try:
            data = json.loads(fetch(YJRX_JSON.format(fid)).decode("utf-8"))
            items = [
                {
                    "title": it["name"],
                    "link": YJRX_ITEM_URL.format(it["accessPath"]),
                    "id": it["id"],
                    "tag": tag_of(it["name"]),
                    "kp": key_point(it["name"]),
                }
                for it in data
            ]
            result[name] = {"items": items, "ok": True}
        except Exception as e:
            result[name] = {"items": [], "ok": False, "error": str(e)[:100]}
    return result


def fetch_jw_notice() -> list:
    url = "https://jw.beijing.gov.cn/tzgg/"
    try:
        html = fetch(url).decode("utf-8", errors="ignore")
        items = []
        for m in re.finditer(
            r'<a href="(\./\d{6}/t\d{8}_\d+\.html)">([^<]{6,100})</a>\s*(?:</li>|<)',
            html,
        ):
            items.append({
                "title": m.group(2).strip(),
                "link": "https://jw.beijing.gov.cn/tzgg/" + m.group(1)[2:],
                "tag": tag_of(m.group(2)),
                "kp": key_point(m.group(2)),
            })
        return items[:15]
    except Exception:
        return []


def fetch_moe_notice() -> list:
    url = "http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/A01/"
    try:
        html = fetch(url).decode("utf-8", errors="ignore")
        items = []
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*title="([^"]{6,80})"', html):
            items.append({
                "title": m.group(2),
                "link": m.group(1),
                "tag": tag_of(m.group(2)),
                "kp": key_point(m.group(2)),
            })
        return items[:15]
    except Exception:
        return []


def fetch_rdfz() -> dict:
    """人大附中：通知公告 + 招生资讯。"""
    out = {}
    sections = {
        "通知公告": "https://www.rdfz.cn/xwzx/tzgg.htm",
        "招生资讯": "https://www.rdfz.cn/zszp/zszx1/zsdt.htm",
    }
    for sec, url in sections.items():
        try:
            html = fetch(url).decode("utf-8", errors="ignore")
            depth = r"\.\./\.\./info" if "zszp" in url else r"\.\./info"
            items = []
            for m in re.finditer(
                rf'<a href="({depth}/\d+/\d+\.htm)"[^>]*>\s*<time><span>\d+</span>/\s*([\d-]+)</time>\s*<div class="txt">\s*<h3 class="eclip">([^<]+)</h3>',
                html,
            ):
                prefix = "https://www.rdfz.cn/" + ("../" * (2 if "zszp" in url else 1))
                link = "https://www.rdfz.cn/" + m.group(1).replace("../", "")
                items.append({
                    "title": m.group(3),
                    "link": link,
                    "date": m.group(2),
                    "tag": tag_of(m.group(3)),
                    "kp": key_point(m.group(3)),
                })
            out[sec] = items
        except Exception:
            out[sec] = []
    return out


def fetch_qhfz() -> list:
    """清华附中招生专栏。"""
    url = "https://www.qhfz.edu.cn/student_talent/"
    try:
        html = fetch(url).decode("utf-8", errors="ignore")
        items = []
        for m in re.finditer(r'<a href="(info/\d+/\d+\.htm)" title="([^"]{6,100})"', html):
            items.append({
                "title": m.group(2),
                "link": url + m.group(1),
                "tag": tag_of(m.group(2)),
                "kp": key_point(m.group(2)),
            })
        return items[:10]
    except Exception:
        return []


# ---------- diff（NEW 徽章） ----------

def load_prev_ids() -> set:
    p = DOCS / "data.json"
    if not p.exists():
        return set()
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
        ids = set()
        for d in prev.get("data", {}).get("区级", {}).values():
            for it in d.get("items", []):
                ids.add(it.get("id") or it.get("link"))
        for it in prev.get("data", {}).get("市教委", []) + prev.get("data", {}).get("教育部", []):
            ids.add(it.get("link"))
        for sec_items in prev.get("data", {}).get("校级", {}).values():
            for it in sec_items:
                ids.add(it.get("link"))
        return ids
    except Exception:
        return set()


# ---------- 页面生成 ----------

HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K12 官方信源看板</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background: #f5f6f7; color: #1c1e21; padding: 24px; max-width: 1200px; margin: 0 auto; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-size: 20px; }}
  .meta {{ font-size: 12px; color: #888; }}
  h2 {{ font-size: 15px; margin: 28px 0 12px; color: #444; display: flex; align-items: center; gap: 8px; }}
  h2 .badge {{ font-size: 11px; background: #fce8e6; color: #d93025; padding: 1px 8px; border-radius: 10px; }}
  .summary {{ font-size: 13px; color: #555; background: #eef3fb; border-radius: 8px; padding: 10px 14px; margin-bottom: 4px; line-height: 1.7; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.08); border-left: 3px solid #2f7d32; }}
  .card.err {{ border-left-color: #d93025; opacity: .7; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
  .card-head .name {{ font-weight: 600; font-size: 14px; }}
  .card-head .count {{ font-size: 11px; color: #2f7d32; background: #e8f5e9; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }}
  .card.err .count {{ color: #d93025; background: #fce8e6; }}
  .kp {{ font-size: 12px; color: #666; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px dashed #e0e0e0; }}
  .kp b {{ color: #1a5fb4; font-weight: 500; }}
  ul {{ list-style: none; }}
  li {{ font-size: 13px; line-height: 1.55; border-bottom: 1px solid #f0f0f0; padding: 5px 0; display: flex; gap: 6px; align-items: baseline; }}
  li:last-child {{ border-bottom: none; }}
  li a {{ color: #1a5fb4; text-decoration: none; flex: 1; }}
  li a:hover {{ text-decoration: underline; }}
  li .tag {{ font-size: 10px; padding: 1px 6px; border-radius: 8px; background: #f1f3f4; color: #5f6368; white-space: nowrap; }}
  li .tag.t入学政策 {{ background: #e8f0fe; color: #1a5fb4; }}
  li .tag.t招生简章 {{ background: #fef7e0; color: #b06000; }}
  li .tag.t审核细则 {{ background: #e6f4ea; color: #137333; }}
  li .tag.t入学问答 {{ background: #f3e8fd; color: #7627bb; }}
  li .new {{ font-size: 10px; background: #d93025; color: #fff; padding: 1px 6px; border-radius: 8px; }}
  li.empty {{ color: #999; }}
  details {{ margin-top: 4px; }}
  details summary {{ font-size: 12px; color: #888; cursor: pointer; }}
  footer {{ margin-top: 32px; font-size: 12px; color: #999; text-align: center; }}
</style>
</head>
<body>
<header>
  <h1>K12 官方信源看板</h1>
  <div class="meta">构建时间：{built_at} ｜ 每 6 小时自动更新</div>
</header>
<div class="summary">
  <b>本页要点</b>：市级政策 <b>{jw_new}</b> 条更新 · 区级 <b>{d_online}</b>/18 区在线（合计 {d_total} 条政策）· 校级 {s_total} 条 ·
  今日新增 <b class="new-count">{new_total}</b> 条{new_list}
</div>

<h2>市级 {jw_new_badge}</h2>
<div class="grid">
  <div class="card">
    <div class="card-head"><span class="name">北京市教委 · 通知公告</span><span class="count">{jw_n} 条</span></div>
    <div class="kp">{jw_kp}</div>
    <ul>{jw_lis}</ul>
  </div>
  <div class="card">
    <div class="card-head"><span class="name">教育部 · 公告公示</span><span class="count">{moe_n} 条</span></div>
    <div class="kp">{moe_kp}</div>
    <ul>{moe_lis}</ul>
  </div>
</div>

<h2>区级招生政策（yjrx） {d_new_badge}</h2>
<div class="grid">{district_html}
</div>

<h2>校级（可自动采集的学校）</h2>
<div class="grid">{school_html}
</div>

<footer>信源：yjrx.bjedu.cn ｜ jw.beijing.gov.cn ｜ moe.gov.cn ｜ rdfz.cn ｜ qhfz.edu.cn<br>
公众号与私域信源不在本看板覆盖范围（走 wewe-rss 与访谈通道）</footer>
</body>
</html>"""


def item_li(it: dict, prev_ids: set) -> str:
    new = '<span class="new">NEW</span>' if (it.get("id") or it.get("link")) not in prev_ids else ""
    tag = it.get("tag", "")
    return (
        f'<li>{new}<span class="tag t{tag}">{tag}</span>'
        f'<a href="{it["link"]}" target="_blank">{it["title"]}</a></li>'
    )


def card(name: str, items: list, ok: bool, prev_ids: set, max_show: int = 5) -> str:
    n = len(items)
    top = items[:max_show]
    rest = items[max_show:]
    new_in_card = sum(1 for it in items if (it.get("id") or it.get("link")) not in prev_ids)
    status = "ok" if ok else "err"
    kp = top[0]["kp"] if top else "暂无数据"
    lis = "".join(item_li(it, prev_ids) for it in top)
    more = ""
    if rest:
        rest_lis = "".join(item_li(it, prev_ids) for it in rest)
        more = f'<details><summary>展开其余 {len(rest)} 条</summary><ul>{rest_lis}</ul></details>'
    new_badge = f' <span class="count" style="background:#fce8e6;color:#d93025">+{new_in_card} 新</span>' if new_in_card else ""
    empty_li = '<li class="empty">暂无数据</li>'
    return (
        f'<div class="card {status}">'
        f'<div class="card-head"><span class="name">{name}</span><span>{new_badge}<span class="count">{n} 条</span></span></div>'
        f'<div class="kp">{kp}</div>'
        f'<ul>{lis or empty_li}</ul>{more}</div>'
    )


def build_html(data: dict, prev_ids: set, built_at: str, new_items: list) -> str:
    jw, moe = data["市教委"], data["教育部"]
    districts, schools = data["区级"], data["校级"]

    district_html = ""
    d_total, d_online, d_new = 0, 0, 0
    for name in DISTRICTS:
        d = districts[name]
        d_total += len(d["items"])
        d_online += 1 if d["ok"] else 0
        d_new += sum(1 for it in d["items"] if it.get("id") not in prev_ids)
        district_html += card(name, d["items"], d["ok"], prev_ids, max_show=4)

    school_html = ""
    s_total = 0
    rdfz = schools.get("人大附中", {})
    for sec, items in rdfz.items():
        s_total += len(items)
        school_html += card(f"人大附中 · {sec}", items, bool(items), prev_ids, max_show=4)
    qhfz_items = schools.get("清华附中", [])
    s_total += len(qhfz_items)
    school_html += card("清华附中 · 招生专栏", qhfz_items, bool(qhfz_items), prev_ids, max_show=4)

    new_total = len(new_items)
    if new_items and new_total <= 10:
        new_list = "：" + "、".join(f'{it["src"]}「{it["title"][:22]}」' for it in new_items[:6])
    else:
        new_list = ""

    jw_new = sum(1 for it in jw if it["link"] not in prev_ids)
    jw_new_badge = f'<span class="badge">+{jw_new + d_new} 新</span>' if (jw_new + d_new) else ""
    d_new_badge = f'<span class="badge">+{d_new} 新</span>' if d_new else ""
    jw_kp = jw[0]["kp"] if jw else "拉取失败"
    moe_kp = moe[0]["kp"] if moe else "拉取失败"

    return HTML_TMPL.format(
        built_at=built_at,
        jw_new=jw_new,
        d_online=d_online,
        d_total=d_total,
        s_total=s_total,
        new_total=new_total,
        new_list=new_list,
        jw_new_badge=jw_new_badge,
        d_new_badge=d_new_badge,
        jw_n=len(jw),
        jw_kp=jw_kp,
        jw_lis="".join(item_li(it, prev_ids) for it in jw[:10]),
        moe_n=len(moe),
        moe_kp=moe_kp,
        moe_lis="".join(item_li(it, prev_ids) for it in moe[:10]),
        district_html=district_html,
        school_html=school_html,
    )


def main():
    built_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    prev_ids = load_prev_ids()

    data = {
        "市教委": fetch_jw_notice(),
        "教育部": fetch_moe_notice(),
        "区级": fetch_yjrx(),
        "校级": {
            "人大附中": fetch_rdfz(),
            "清华附中": fetch_qhfz(),
        },
    }

    # 收集新增条目（摘要区用）
    new_items = []
    for it in data["市教委"]:
        if it["link"] not in prev_ids:
            new_items.append({"src": "市教委", "title": it["title"]})
    for name, d in data["区级"].items():
        for it in d["items"]:
            if it.get("id") not in prev_ids:
                new_items.append({"src": name, "title": it["title"]})

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(
        json.dumps({"built_at": built_at, "data": data}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOCS / "index.html").write_text(build_html(data, prev_ids, built_at, new_items), encoding="utf-8")

    ok = sum(1 for d in data["区级"].values() if d["ok"])
    print(
        f"built: {built_at} | 市教委 {len(data['市教委'])} | 教育部 {len(data['教育部'])} | "
        f"区级在线 {ok}/18 | 校级 {sum(len(v) for s in data['校级'].values() for v in (s.values() if isinstance(s, dict) else [s]))} | 新增 {len(new_items)}"
    )


if __name__ == "__main__":
    main()
