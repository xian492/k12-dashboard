#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K12 官方信源看板构建脚本。

拉取三路官方信源，生成静态看板 docs/index.html + 数据快照 docs/data.json：
1. yjrx 18 区招生政策 JSON 接口（每区一个 fid）
2. 北京市教委通知公告 RSS（本地 RSSHub 转发，构建时直拉原始页面不行，改拉 RSSHub 公网可达性问题，
   实际方案：教委通知走 yjrx 同款 JSON 思路不存在，故用 RSSHub 部署在 Actions 里的方式成本过高，
   简化：市级和部级公告直接解析其官网列表页）
3. 教育部公告公示（官网列表页）

用法：python3 build.py（无第三方依赖，纯标准库，方便 GitHub Actions 直接跑）
"""
import json
import re
import ssl
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# yjrx 18 区 fid（与本地 RSSHub 路由一致，实测于 2026-10-21）
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


def fetch_yjrx() -> dict:
    """拉 18 区招生政策 JSON。"""
    result = {}
    for name, fid in DISTRICTS.items():
        try:
            data = json.loads(fetch(YJRX_JSON.format(fid)).decode("utf-8"))
            result[name] = {
                "items": [
                    {"title": it["name"], "link": YJRX_ITEM_URL.format(it["accessPath"]), "id": it["id"]}
                    for it in data
                ],
                "ok": True,
            }
        except Exception as e:
            result[name] = {"items": [], "ok": False, "error": str(e)[:100]}
    return result


def fetch_jw_notice() -> list:
    """北京市教委通知公告：解析官网列表页。"""
    url = "https://jw.beijing.gov.cn/tzgg/"
    try:
        html = fetch(url).decode("utf-8", errors="ignore")
        items = []
        for m in re.finditer(r'<a href="(\./\d{6}/t\d{8}_\d+\.html)">([^<]{6,100})</a>', html):
            link, title = m.group(1), m.group(2).strip()
            link = "https://jw.beijing.gov.cn/tzgg/" + link[2:]
            items.append({"title": title, "link": link})
        return items[:20]
    except Exception:
        return []


def fetch_moe_notice() -> list:
    """教育部公告公示：解析官网列表页。"""
    url = "http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/A01/"
    try:
        html = fetch(url).decode("utf-8", errors="ignore")
        items = []
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*title="([^"]{6,80})"', html):
            items.append({"title": m.group(2), "link": m.group(1)})
        return items[:20]
    except Exception:
        return []


def build_html(data: dict, built_at: str) -> str:
    jw = data["市教委"]
    moe = data["教育部"]
    districts = data["区级"]

    def row(item):
        return f'<li><a href="{item["link"]}" target="_blank">{item["title"]}</a></li>'

    district_html = ""
    total_district_items = 0
    for name in DISTRICTS:
        d = districts[name]
        status = "ok" if d["ok"] else "err"
        n = len(d["items"])
        total_district_items += n
        lis = "".join(row(it) for it in d["items"])
        district_html += f"""
        <div class="card {status}">
          <div class="card-head"><span class="name">{name}</span><span class="count">{n} 条政策</span></div>
          <ul>{lis or '<li class="empty">暂无数据</li>'}</ul>
        </div>"""

    jw_lis = "".join(row(it) for it in jw) or '<li class="empty">拉取失败</li>'
    moe_lis = "".join(row(it) for it in moe) or '<li class="empty">拉取失败</li>'

    ok_count = sum(1 for d in districts.values() if d["ok"])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K12 官方信源看板</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background: #f5f6f7; color: #1c1e21; padding: 24px; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-size: 20px; }}
  .meta {{ font-size: 12px; color: #888; }}
  h2 {{ font-size: 15px; margin: 24px 0 12px; color: #444; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.08); border-left: 3px solid #2f7d32; }}
  .card.err {{ border-left-color: #d93025; opacity: .7; }}
  .card-head {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
  .card-head .name {{ font-weight: 600; font-size: 14px; }}
  .card-head .count {{ font-size: 12px; color: #2f7d32; background: #e8f5e9; padding: 2px 8px; border-radius: 10px; }}
  .card.err .count {{ color: #d93025; background: #fce8e6; }}
  ul {{ list-style: none; }}
  li {{ font-size: 13px; line-height: 1.6; border-bottom: 1px solid #f0f0f0; padding: 4px 0; }}
  li:last-child {{ border-bottom: none; }}
  li a {{ color: #1a5fb4; text-decoration: none; }}
  li a:hover {{ text-decoration: underline; }}
  li.empty {{ color: #999; }}
  .summary {{ font-size: 13px; color: #555; background: #eef3fb; border-radius: 8px; padding: 10px 14px; margin-bottom: 4px; }}
</style>
</head>
<body>
<header>
  <h1>K12 官方信源看板</h1>
  <div class="meta">构建时间：{built_at} ｜ GitHub Actions 每 6 小时自动更新</div>
</header>
<div class="summary">市级 2 路 ｜ 区级 18 路（在线 {ok_count}/18）｜ 区级政策合计 {total_district_items} 条</div>

<h2>市级</h2>
<div class="grid">
  <div class="card">
    <div class="card-head"><span class="name">北京市教委 · 通知公告</span><span class="count">{len(jw)} 条</span></div>
    <ul>{jw_lis}</ul>
  </div>
  <div class="card">
    <div class="card-head"><span class="name">教育部 · 公告公示</span><span class="count">{len(moe)} 条</span></div>
    <ul>{moe_lis}</ul>
  </div>
</div>

<h2>区级招生政策（yjrx）</h2>
<div class="grid">{district_html}
</div>
</body>
</html>"""


def main():
    built_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    data = {
        "市教委": fetch_jw_notice(),
        "教育部": fetch_moe_notice(),
        "区级": fetch_yjrx(),
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(
        json.dumps({"built_at": built_at, "data": {k: (v if k != "区级" else v) for k, v in data.items()}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOCS / "index.html").write_text(build_html(data, built_at), encoding="utf-8")
    ok = sum(1 for d in data["区级"].values() if d["ok"])
    print(f"built: {built_at} | 市教委 {len(data['市教委'])} 条 | 教育部 {len(data['教育部'])} 条 | 区级在线 {ok}/18")


if __name__ == "__main__":
    main()
