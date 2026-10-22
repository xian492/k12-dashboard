#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K12 官方信源看板构建脚本 v3。

v3 布局：按区分组。市级置顶；区级政策与该区学校合并为同一个「区卡片」；学校按校名合并。
信源：yjrx 18 区 + 市教委 + 教育部 + 4 所可解析学校官网。

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

# 区名 -> (yjrx fid, [(学校名, 栏目配置...)])
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

# 学校配置：区 -> [学校列表]，每个学校 = (校名, [(栏目名, 栏目URL, 解析器)])
# 解析器类型：rdfz(人大附中模板)、qhfz(title属性)、sdfz(北师大附中模板)、cnuhs(首师大附中)
SCHOOLS = {
    "海淀区": [
        ("人大附中", [
            ("通知公告", "https://www.rdfz.cn/xwzx/tzgg.htm", "rdfz"),
            ("招生资讯", "https://www.rdfz.cn/zszp/zszx1/zsdt.htm", "rdfz"),
        ]),
        ("清华附中", [
            ("招生专栏", "https://www.qhfz.edu.cn/student_talent/", "qhfz"),
        ]),
        ("首师大附中", [
            ("校园快讯", "https://www.cnuhs.cn/CampusNews/50.html", "cnuhs"),
        ]),
    ],
    "西城区": [
        ("北师大附中", [
            ("招生专栏", "https://www.bjsdfz.com/list-219-1.html", "sdfz"),
        ]),
    ],
}

YJRX_JSON = "https://yjrx.bjedu.cn/uploads/json/{}.json"
YJRX_ITEM_URL = "https://yjrx.bjedu.cn{}"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CTX = ssl.create_default_context()


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


# ---------- 标签 ----------

TAG_RULES = [
    ("入学政策", [r"入学工作", r"入学.{0,4}意见", r"实施细则", r"入学方案", r"招生办法"]),
    ("招生简章", [r"招生简章", r"特长生", r"报名通知", r"信息采集", r"采集通知", r"测试公告"]),
    ("审核细则", [r"审核细则", r"审核办法", r"材料审核"]),
    ("入学问答", [r"问答", r"答疑"]),
]


def tag_of(title: str) -> str:
    for tag, patterns in TAG_RULES:
        if any(re.search(p, title) for p in patterns):
            return tag
    return "通知公告"


def key_point(title: str) -> str:
    parts = []
    m = re.search(r"(20\d{2})", title)
    if m:
        parts.append(m.group(1) + "年")
    for tag, patterns in TAG_RULES:
        if any(re.search(p, title) for p in patterns):
            parts.append(tag)
            break
    return " · ".join(parts) if parts else "常规通知"


# ---------- 拉取 ----------

def fetch_yjrx(fid: str) -> list:
    data = json.loads(fetch(YJRX_JSON.format(fid)).decode("utf-8"))
    return [
        {"title": it["name"], "link": YJRX_ITEM_URL.format(it["accessPath"]), "id": it["id"],
         "tag": tag_of(it["name"]), "kp": key_point(it["name"]), "src": "区政策"}
        for it in data
    ]


def parse_rdfz(url: str) -> list:
    html = fetch(url).decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(
        r'<a href="((?:\.\./)+info/\d+/\d+\.htm)"[^>]*>\s*<time><span>\d+</span>/\s*([\d-]+)</time>\s*<div class="txt">\s*<h3 class="eclip">([^<]+)</h3>',
        html,
    ):
        link = "https://www.rdfz.cn/" + m.group(1).replace("../", "")
        items.append({"title": m.group(3), "link": link, "date": m.group(2),
                      "tag": tag_of(m.group(3)), "kp": key_point(m.group(3)), "src": "学校"})
    return items


def parse_qhfz(url: str) -> list:
    html = fetch(url).decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a href="(info/\d+/\d+\.htm)" title="([^"]{6,100})"', html):
        items.append({"title": m.group(2), "link": url + m.group(1),
                      "tag": tag_of(m.group(2)), "kp": key_point(m.group(2)), "src": "学校"})
    return items


def parse_sdfz(url: str) -> list:
    html = fetch(url).decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a href="(/show-219-\d+-1\.html)"[^>]*>.*?<em class="em3">\s*(.*?)\s*</em>', html, re.S):
        link = "https://www.bjsdfz.com" + m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        items.append({"title": title, "link": link,
                      "tag": tag_of(title), "kp": key_point(title), "src": "学校"})
    return items


def parse_cnuhs(url: str) -> list:
    html = fetch(url).decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a target="_blank" href="(/CampusNews/\d+/\d+\.html)"[^>]*>([^<]{6,})</a>', html):
        items.append({"title": m.group(2), "link": "https://www.cnuhs.cn" + m.group(1),
                      "tag": tag_of(m.group(2)), "kp": key_point(m.group(2)), "src": "学校"})
    return items


PARSERS = {"rdfz": parse_rdfz, "qhfz": parse_qhfz, "sdfz": parse_sdfz, "cnuhs": parse_cnuhs}


def fetch_jw_notice() -> list:
    html = fetch("https://jw.beijing.gov.cn/tzgg/").decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a href="(\./\d{6}/t\d{8}_\d+\.html)">([^<]{6,100})</a>', html):
        items.append({"title": m.group(2).strip(),
                      "link": "https://jw.beijing.gov.cn/tzgg/" + m.group(1)[2:],
                      "tag": tag_of(m.group(2)), "kp": key_point(m.group(2)), "src": "市教委"})
    return items[:12]


def fetch_moe_notice() -> list:
    html = fetch("http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/A01/").decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*title="([^"]{6,80})"', html):
        items.append({"title": m.group(2), "link": m.group(1),
                      "tag": tag_of(m.group(2)), "kp": key_point(m.group(2)), "src": "教育部"})
    return items[:12]


# ---------- diff ----------

def load_prev_keys() -> set:
    p = DOCS / "data.json"
    if not p.exists():
        return set()
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
        keys = set()
        for d in prev.get("data", {}).get("区级", {}).values():
            for sec in d.values():
                for it in sec.get("items", []) if isinstance(sec, dict) else sec:
                    if isinstance(it, dict):
                        keys.add(it.get("id") or it.get("link"))
        for it in prev.get("data", {}).get("市教委", []):
            keys.add(it.get("link"))
        for it in prev.get("data", {}).get("教育部", []):
            keys.add(it.get("link"))
        return keys
    except Exception:
        return set()


# ---------- 页面 ----------

HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K12 官方信源看板</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background: #f5f6f7; color: #1c1e21; padding: 24px; max-width: 1280px; margin: 0 auto; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-size: 20px; }}
  .meta {{ font-size: 12px; color: #888; }}
  h2 {{ font-size: 15px; margin: 28px 0 12px; color: #444; }}
  h2 .n {{ font-size: 12px; font-weight: normal; color: #888; }}
  .summary {{ font-size: 13px; color: #555; background: #eef3fb; border-radius: 8px; padding: 10px 14px; margin-bottom: 4px; line-height: 1.8; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 14px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .card-head {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; border-bottom: 2px solid #2f7d32; padding-bottom: 8px; }}
  .card-head .name {{ font-weight: 700; font-size: 16px; color: #2f7d32; }}
  .card-head .sub {{ font-size: 11px; color: #999; }}
  .count {{ font-size: 11px; color: #2f7d32; background: #e8f5e9; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }}
  .sec {{ margin-bottom: 10px; }}
  .sec-t {{ font-size: 12px; color: #666; font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }}
  .sec-t .n-new {{ font-size: 10px; background: #d93025; color: #fff; padding: 0 6px; border-radius: 8px; }}
  ul {{ list-style: none; }}
  li {{ font-size: 13px; line-height: 1.55; border-bottom: 1px solid #f0f0f0; padding: 5px 0; display: flex; gap: 6px; align-items: baseline; }}
  li:last-child {{ border-bottom: none; }}
  li a {{ color: #1a5fb4; text-decoration: none; flex: 1; }}
  li a:hover {{ text-decoration: underline; }}
  .tag {{ font-size: 10px; padding: 1px 6px; border-radius: 8px; background: #f1f3f4; color: #5f6368; white-space: nowrap; }}
  .tag.t入学政策 {{ background: #e8f0fe; color: #1a5fb4; }}
  .tag.t招生简章 {{ background: #fef7e0; color: #b06000; }}
  .tag.t审核细则 {{ background: #e6f4ea; color: #137333; }}
  .tag.t入学问答 {{ background: #f3e8fd; color: #7627bb; }}
  .new {{ font-size: 10px; background: #d93025; color: #fff; padding: 1px 6px; border-radius: 8px; }}
  li.empty {{ color: #999; }}
  details {{ margin-top: 2px; }}
  details summary {{ font-size: 12px; color: #888; cursor: pointer; padding: 4px 0; }}
  .citycard {{ border-left: 3px solid #1a5fb4; }}
  footer {{ margin-top: 32px; font-size: 12px; color: #999; text-align: center; line-height: 1.8; }}
</style>
</head>
<body>
<header>
  <h1>K12 官方信源看板</h1>
  <div class="meta">构建时间：{built_at} ｜ 每 6 小时自动更新</div>
</header>
<div class="summary">{summary}</div>
"""


def item_li(it: dict, prev_keys: set) -> str:
    is_new = (it.get("id") or it.get("link")) not in prev_keys
    new = '<span class="new">NEW</span>' if is_new else ""
    tag = it.get("tag", "")
    return (
        f'<li>{new}<span class="tag t{tag}">{tag}</span>'
        f'<a href="{it["link"]}" target="_blank">{it["title"]}</a></li>'
    )


def section(title: str, items: list, prev_keys: set, max_show: int = 4) -> str:
    """一个小节：标题 + 最多 max_show 条 + 折叠剩余。"""
    if not items:
        return f'<div class="sec"><div class="sec-t">{title}</div><ul><li class="empty">暂无数据</li></ul></div>'
    n_new = sum(1 for it in items if (it.get("id") or it.get("link")) not in prev_keys)
    new_badge = f'<span class="n-new">{n_new} 新</span>' if n_new else ""
    top_lis = "".join(item_li(it, prev_keys) for it in items[:max_show])
    more = ""
    if len(items) > max_show:
        rest_lis = "".join(item_li(it, prev_keys) for it in items[max_show:])
        more = f'<details><summary>展开其余 {len(items) - max_show} 条</summary><ul>{rest_lis}</ul></details>'
    return (
        f'<div class="sec"><div class="sec-t">{title} · {len(items)} 条 {new_badge}</div>'
        f'<ul>{top_lis}</ul>{more}</div>'
    )


def build_page(data: dict, prev_keys: set, built_at: str) -> str:
    parts = [HTML_HEAD.format(built_at=built_at, summary="")]

    # 摘要
    jw, moe = data["市教委"], data["教育部"]
    d_online = sum(1 for d in data["区级"].values() if d["政策"])
    n_new = sum(
        1
        for d in data["区级"].values()
        for sec_list in ([d["政策"]] + [s for sch in d["学校"].values() for s in sch.values()])
        for it in sec_list
        if (it.get("id") or it.get("link")) not in prev_keys
    )
    summary = (
        f"<b>总览</b>：市级 2 路 · 区级 {d_online}/18 在线 · 学校 {sum(len(d['学校']) for d in data['区级'].values())} 所 ·"
        f" 本次新增 <b>{n_new}</b> 条。市级最新：<b>{jw[0]['title'][:30]}</b>"
        if jw else "市级拉取失败"
    )
    parts[0] = HTML_HEAD.format(built_at=built_at, summary=summary)

    # 市级
    parts.append('<h2>市级 <span class="n">市教委 · 教育部</span></h2><div class="grid">')
    parts.append(
        f'<div class="card citycard"><div class="card-head"><span class="name">北京市教委</span><span class="count">{len(jw)} 条</span></div>'
        + section("通知公告", jw, prev_keys, max_show=6) + "</div>"
    )
    parts.append(
        f'<div class="card citycard"><div class="card-head"><span class="name">教育部</span><span class="count">{len(moe)} 条</span></div>'
        + section("公告公示", moe, prev_keys, max_show=6) + "</div>"
    )
    parts.append("</div>")

    # 区级（每区一卡，政策+学校合并）
    parts.append('<h2>分区 <span class="n">区招生政策 + 该区学校</span></h2><div class="grid">')
    for 区名, fid in DISTRICTS.items():
        d = data["区级"][区名]
        card = f'<div class="card"><div class="card-head"><span class="name">{区名}</span><span class="sub">{len(d["政策"])} 政策 · {len(d["学校"])} 校</span></div>'
        card += section("区招生政策", d["政策"], prev_keys, max_show=3)
        for 校名, 栏目 in d["学校"].items():
            for 栏名, items in 栏目.items():
                card += section(f"{校名} · {栏名}", items, prev_keys, max_show=3)
        card += "</div>"
        parts.append(card)
    parts.append("</div>")

    parts.append(
        '<footer>信源：yjrx.bjedu.cn（18区政策）｜ jw.beijing.gov.cn ｜ moe.gov.cn ｜ '
        "rdfz.cn ｜ qhfz.edu.cn ｜ bjsdfz.com ｜ cnuhs.cn<br>"
        "学校官网能自动化采集的有限（多数学校无独立官网或动态渲染），公众号渠道走 wewe-rss 另行接入</footer>"
    )
    return "".join(parts) + "</body></html>"


def main():
    built_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    prev_keys = load_prev_keys()

    区级 = {}
    for 区名, fid in DISTRICTS.items():
        try:
            政策 = fetch_yjrx(fid)
        except Exception:
            政策 = []
        学校 = {}
        for 校名, 栏目 in SCHOOLS.get(区名, []):
            学校[校名] = {}
            for 栏名, url, parser in 栏目:
                try:
                    学校[校名][栏名] = PARSERS[parser](url)
                except Exception:
                    学校[校名][栏名] = []
        区级[区名] = {"政策": 政策, "学校": 学校}

    data = {
        "市教委": fetch_jw_notice(),
        "教育部": fetch_moe_notice(),
        "区级": 区级,
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(
        json.dumps({"built_at": built_at, "data": data}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOCS / "index.html").write_text(build_page(data, prev_keys, built_at), encoding="utf-8")

    d_online = sum(1 for d in 区级.values() if d["政策"])
    print(
        f"built: {built_at} | 市教委 {len(data['市教委'])} | 教育部 {len(data['教育部'])} | "
        f"区在线 {d_online}/18 | 学校 {sum(len(d['学校']) for d in 区级.values())} 所"
    )


if __name__ == "__main__":
    main()
