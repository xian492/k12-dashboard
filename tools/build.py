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
  html {{ font-variant-numeric: tabular-nums; }}
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #FBFAF7; color: #212427;
    padding: 28px 20px 40px; line-height: 1.6;
  }}
  .page {{ max-width: 920px; margin: 0 auto; }}

  /* ── 头部 ───────────────────── */
  header {{ display: flex; justify-content: space-between; align-items: flex-end;
    padding-bottom: 14px; border-bottom: 2px solid #212427; flex-wrap: wrap; gap: 6px; }}
  h1 {{ font-family: "Songti SC", "Noto Serif SC", "SimSun", serif;
    font-size: 22px; font-weight: 700; letter-spacing: .02em; }}
  .meta {{ font-size: 12px; color: #8a877e; }}

  /* ── 招生季时间轴 ─────────────── */
  .season {{ margin: 26px 0 6px; }}
  .track {{
    position: relative; height: 34px; margin: 10px 2px 0;
    border-bottom: 1px solid #E3E1D8;
  }}
  .hot {{
    position: absolute; top: 0; bottom: -1px;
    background: #F0E4DE; opacity: .6;
  }}
  .stop {{
    position: absolute; top: 0; width: 34%; max-width: 120px;
    transform: translateX(-4px); padding-top: 10px;
  }}
  .stop i {{ position: absolute; top: 20px; left: 4px; width: 7px; height: 7px;
    border-radius: 50%; background: #B23B32; display: block; }}
  .stop b {{ font-size: 12px; font-weight: 600; color: #212427; display: block; line-height: 1.3; }}
  .stop em {{ font-style: normal; font-size: 11px; color: #8a877e; }}
  .today {{
    position: absolute; top: 6px; text-align: center;
    animation: mark .5s ease-out .25s backwards;
  }}
  .today b {{
    font-size: 11px; color: #B23B32; font-weight: 600; display: block;
  }}
  .today i {{
    position: absolute; left: -2px; top: 17px; width: 5px; height: 5px;
    border: 1.5px solid #B23B32; border-radius: 50%; background: #FBFAF7;
    display: block;
  }}
  @keyframes mark {{ from {{ opacity: 0; transform: translateY(4px); }} }}
  .season-note {{ font-size: 12px; color: #8a877e; margin-top: 8px; }}

  /* ── 区块标题 ────────────────── */
  h2 {{
    font-family: "Songti SC", "Noto Serif SC", serif;
    font-size: 17px; margin: 34px 0 4px; padding-bottom: 4px;
    border-bottom: 1px solid #B23B32; width: fit-content;
  }}
  h2::after {{ content: ""; }}

  /* ── 市级头条 ────────────────── */
  .city {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 36px; margin-top: 14px; }}
  @media (max-width: 680px) {{ .city {{ grid-template-columns: 1fr; }} }}
  .city h3 {{ font-size: 12px; font-weight: 600; color: #31586E; margin-bottom: 2px; }}
  .headline {{ font-family: "Songti SC", "Noto Serif SC", serif;
    font-size: 15.5px; line-height: 1.5; margin: 4px 0 10px; }}
  .headline a {{ color: #212427; text-decoration: none; }}
  .headline a:hover {{ color: #B23B32; }}
  .headline .n-new {{ margin-right: 6px; }}

  /* ── 条目 ─────────────────── */
  ul {{ list-style: none; }}
  li {{ font-size: 13px; padding: 6px 0; border-bottom: 1px solid #EDEBE3;
    display: flex; gap: 8px; align-items: baseline; }}
  li:last-child {{ border-bottom: none; }}
  li a {{ color: #212427; text-decoration: none; flex: 1; }}
  li a:hover {{ color: #31586E; text-decoration: underline; text-underline-offset: 3px; }}
  .kind {{ font-size: 11px; color: #31586E; white-space: nowrap; }}
  .date {{ font-size: 11px; color: #a5a29a; white-space: nowrap; }}
  .n-new {{
    font-size: 10px; font-weight: 600; background: #B23B32; color: #FBFAF7;
    padding: 0 5px; border-radius: 2px; white-space: nowrap; flex: none;
  }}
  li.empty {{ color: #a5a29a; border: none; }}

  /* ── 区台账 ─────────────────── */
  .ledger {{ margin-top: 14px; border-top: 1px solid #212427; }}
  details.row {{ border-bottom: 1px solid #E3E1D8; }}
  details.row summary {{
    list-style: none; cursor: pointer; padding: 11px 2px;
    display: grid; grid-template-columns: 84px 44px 1fr auto;
    gap: 12px; align-items: baseline;
  }}
  details.row summary::-webkit-details-marker {{ display: none; }}
  details.row summary:hover {{ background: #F3F1EC; }}
  .d-name {{ font-family: "Songti SC", "Noto Serif SC", serif;
    font-weight: 700; font-size: 15px; }}
  .d-count {{ font-size: 12px; color: #8a877e; text-align: right; }}
  .d-latest {{ font-size: 12.5px; color: #6b6862;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .d-side {{ font-size: 11px; color: #31586E; white-space: nowrap; display: flex; gap: 6px; align-items: baseline; }}
  .row-body {{ padding: 2px 2px 14px 96px; }}
  @media (max-width: 680px) {{
    details.row summary {{ grid-template-columns: 72px 1fr auto; }}
    .d-count {{ display: none; }}
    .d-latest {{ grid-column: 1 / -1; white-space: normal; }}
    .row-body {{ padding-left: 2px; }}
  }}
  .school-sec {{ margin-top: 12px; }}
  .school-sec h4 {{ font-size: 12px; font-weight: 600; color: #31586E; margin-bottom: 2px; }}
  .open-hint {{ font-size: 11px; color: #a5a29a; padding: 2px 2px 0; }}

  footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #E3E1D8;
    font-size: 12px; color: #a5a29a; line-height: 1.9; }}
  @media (prefers-reduced-motion: reduce) {{ .today {{ animation: none; }} }}
</style>
</head>
<body>
<div class="page">
<header>
  <h1>北京小升初 · 官方信源台账</h1>
  <div class="meta">构建于 {built_at}，每 6 小时自动更新</div>
</header>

<div class="season">
  <div class="track">
    <div class="hot" style="left:31%;width:28%"></div>
    <div class="stop" style="left:31%"><i></i><b>市政策</b><em>4 月中</em></div>
    <div class="stop" style="left:36%"><i></i><b>区细则</b><em>4 月底</em></div>
    <div class="stop" style="left:42%"><i></i><b>信息采集</b><em>5 月</em></div>
    <div class="stop" style="left:47%"><i></i><b>派位</b><em>6 月</em></div>
    <div class="stop" style="left:55%"><i></i><b>录取</b><em>7 月</em></div>
    <div class="today" style="left:{today_pct:.0f}%"><b>今天</b><i></i></div>
  </div>
  <div class="season-note">{season_note}</div>
</div>
"""


def item_li(it: dict, prev_keys: set) -> str:
    is_new = (it.get("id") or it.get("link")) not in prev_keys
    new = '<span class="n-new">NEW</span>' if is_new else ""
    kind = it.get("tag", "")
    date = f'<span class="date">{it["date"]}</span>' if it.get("date") else ""
    return (
        f'<li>{new}<span class="kind">{kind}</span>'
        f'<a href="{it["link"]}" target="_blank">{it["title"]}</a>{date}</li>'
    )


def section(title: str, items: list, prev_keys: set, max_show: int = 5) -> str:
    if not items:
        return f'<div class="school-sec"><h4>{title}</h4><ul><li class="empty">暂无数据</li></ul></div>'
    top_lis = "".join(item_li(it, prev_keys) for it in items[:max_show])
    more = ""
    if len(items) > max_show:
        rest_lis = "".join(item_li(it, prev_keys) for it in items[max_show:])
        more = f'<li style="display:block"><details><summary class="open-hint" style="cursor:pointer">其余 {len(items) - max_show} 条</summary><ul style="margin-top:4px">{rest_lis}</ul></details></li>'
    return f'<div class="school-sec"><h4>{title} · {len(items)} 条</h4><ul>{top_lis}{more}</ul></div>'


def build_page(data: dict, prev_keys: set, built_at: str) -> str:
    jw, moe = data["市教委"], data["教育部"]

    # 时间轴：今天在学年周期里的位置（1月=0%，12月≈92%）
    now = datetime.now(timezone(timedelta(hours=8)))
    today_pct = (now.month + now.day / 31) / 12 * 100
    if 8 <= now.month <= 12 or now.month <= 3:
        season_note = "当前处于招生季空窗期。政策集中发布于每年 4 至 7 月，届时本页各区行的更新徽章即为信号。"
    else:
        season_note = "招生季进行中，政策更新频繁，注意各区 NEW 标记。"

    parts = [HTML_HEAD.format(built_at=built_at, today_pct=today_pct, season_note=season_note)]

    # 市级头条
    parts.append('<h2>市级</h2><div class="city">')
    for name, items in (("北京市教委 · 通知公告", jw), ("教育部 · 公告公示", moe)):
        if items:
            top = items[0]
            top_new = '<span class="n-new">NEW</span>' if top["link"] not in prev_keys else ""
            parts.append(
                f'<div><h3>{name} · {len(items)} 条</h3>'
                f'<div class="headline">{top_new}<a href="{top["link"]}" target="_blank">{top["title"]}</a></div>'
                f'<ul>{"".join(item_li(it, prev_keys) for it in items[1:6])}</ul></div>'
            )
        else:
            parts.append(f'<div><h3>{name}</h3><ul><li class="empty">拉取失败</li></ul></div>')
    parts.append("</div>")

    # 区台账
    parts.append('<h2>分区台账</h2><div class="ledger">')
    for 区名, fid in DISTRICTS.items():
        d = data["区级"][区名]
        policies = d["政策"]
        schools = d["学校"]
        n_new = sum(1 for it in policies if (it.get("id") or it.get("link")) not in prev_keys)
        latest = policies[0]["title"] if policies else "（无数据）"
        school_label = f"{len(schools)} 校" if schools else ""
        new_badge = f'<span class="n-new">{n_new} 新</span>' if n_new else ""
        parts.append(
            f'<details class="row"{" open" if (schools or n_new) else ""}><summary>'
            f'<span class="d-name">{区名}</span>'
            f'<span class="d-count">{len(policies)} 条</span>'
            f'<span class="d-latest">{latest}</span>'
            f'<span class="d-side">{new_badge}{school_label}</span>'
            f"</summary>"
            f'<div class="row-body">'
            + section("区招生政策", policies, prev_keys, max_show=4)
        )
        for 校名, 栏目 in schools.items():
            for 栏名, items in 栏目.items():
                parts.append(section(f"{校名} · {栏名}", items, prev_keys, max_show=4))
        parts.append("</div></details>")
    parts.append("</div>")

    parts.append(
        "<footer>信源：yjrx.bjedu.cn（18 区招生政策）｜ jw.beijing.gov.cn ｜ moe.gov.cn ｜ "
        "rdfz.cn ｜ qhfz.edu.cn ｜ bjsdfz.com ｜ cnuhs.cn<br>"
        "多数学校无独立官网或页面动态渲染，公众号渠道经 wewe-rss 另行接入，不在本台账。</footer>"
    )
    return "".join(parts) + "</div></body></html>"


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
