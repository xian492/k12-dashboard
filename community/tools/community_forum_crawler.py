"""Collect forum threads, posts, and replies from public K12 community sources.

Adapters cover the page shapes verified on 2026-10-23:

- ``discuz``  芍药居社区网 / 广州妈妈网：列表 forum-FID-PAGE.html，帖子
  thread-TID-PAGE-1.html，楼层 post_PID / postmessage_PID。
- ``hlgnet``  回龙观社区网：列表 frame.php，帖子 showid.php?theid=ID，回复在
  「相关文章」列表中以 info/u1_REPLYID/ 链接出现，需逐条跟进。
- ``newsmth`` 水木社区：版面列表 board/BOARD?p=N（GBK 编码）。文章页对游客
  有验证码，只采集列表元数据（标题/作者/日期/回复数），不抓正文。
- ``liba``    篱笆网：版面 f_FID.htm 列表公开，帖子详情强制跳登录，只采集
  列表元数据。

千帆（数据库错误）、家长帮（DNS 失效）、家在深圳（域名停放）当日不可用，
不列入。水木、篱笆的登录/验证码墙不做绕过。

Usage:
    python community_forum_crawler.py [--max-pages N] [--max-threads N]
        [--delay 1.5] [--output community/data/community_forum_posts.jsonl]
        [--sources a,b] [--no-replies]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

SOURCES = [
    {
        "id": "shaoyaoju",
        "name": "芍药居社区网",
        "adapter": "discuz",
        "region": "北京",
        "base": "https://www.shaoyaojuwang.com/",
        "encoding": "utf-8",
        "boards": [{"fid": 6, "name": "入学政策"}],
    },
    {
        "id": "gzmama",
        "name": "广州妈妈网",
        "adapter": "discuz",
        "region": "广州",
        "base": "http://www.gzmama.com/",
        "encoding": "utf-8",
        "boards": [
            {"fid": 42, "name": "家有小学生"},
            {"fid": 76, "name": "家有中学生"},
            {"fid": 13, "name": "早教幼教"},
        ],
    },
    {
        "id": "hlgnet",
        "name": "回龙观社区网",
        "adapter": "hlgnet",
        "region": "北京",
        "base": "https://bbs.hlgnet.com/",
        "encoding": "utf-8",
        "boards": [{"bbscate": 0, "boardid": 1, "name": "社区论坛"}],
    },
    {
        "id": "newsmth",
        "name": "水木社区·儿童教育",
        "adapter": "newsmth",
        "region": "北京",
        "base": "https://www.newsmth.net/",
        "encoding": "gbk",
        "boards": [{"board": "ChildEducation", "name": "儿童教育"}],
    },
    {
        "id": "liba",
        "name": "篱笆网",
        "adapter": "liba",
        "region": "上海",
        "base": "https://www.libaclub.com/",
        "encoding": "utf-8",
        "boards": [
            {"fid": 7352, "name": "中高考"},
            {"fid": 1127, "name": "儿童6-11"},
            {"fid": 1126, "name": "家长里短"},
        ],
    },
]

_SPACE_RE = re.compile(r"\s+")


def _text(node) -> str:
    if node is None:
        return ""
    return _SPACE_RE.sub(" ", node.get_text(" ", strip=True)).strip()


class Fetcher:
    def __init__(self, delay: float, timeout: float = 20.0) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0

    def get(self, url: str, encoding: str = "utf-8") -> str | None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            self._last = time.monotonic()
            if resp.status_code != 200:
                return None
            if encoding:
                resp.encoding = encoding
            return resp.text
        except requests.RequestException as exc:
            print(f"  fetch failed: {url}: {exc}", file=sys.stderr)
            self._last = time.monotonic()
            return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_record(source: dict, board_name: str, *, title: str, url: str, thread_id: str) -> dict:
    return {
        "source_id": source["id"],
        "source": source["name"],
        "region": source["region"],
        "board": board_name,
        "thread_id": str(thread_id),
        "title": title,
        "url": url,
        "author": "",
        "published_at": "",
        "reply_count": 0,
        "content_chars": 0,
        "content_text": "",
        "replies": [],
        "crawl_status": "success",
        "crawled_at": _now(),
    }


# ---------------------------------------------------------------------------
# Discuz adapter（芍药居 / 广州妈妈网）
# ---------------------------------------------------------------------------

_THREAD_RE = re.compile(r"thread-(\d+)-1-1\.html")


def discuz_list_threads(fetcher: Fetcher, source: dict, board: dict, max_pages: int) -> list[dict]:
    """Yield {'tid','title','url'} from forum-FID-PAGE.html list pages."""
    threads: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        url = f"{source['base']}forum-{board['fid']}-{page}.html"
        html = fetcher.get(url, source["encoding"])
        if not html:
            break
        found = 0
        for a in BeautifulSoup(html, "html.parser").find_all("a", href=_THREAD_RE):
            tid = _THREAD_RE.search(a["href"]).group(1)
            title = _text(a)
            if not title or tid in threads:
                continue
            threads[tid] = {
                "tid": tid,
                "title": title,
                "url": urljoin(source["base"], a["href"]),
            }
            found += 1
        print(f"  list page {page}: +{found} threads")
        if found == 0:
            break
    return list(threads.values())


_DATE_RE = re.compile(r"发表于\s*(\d{4}-\d{1,2}-\d{1,2}[^<]*)")


def discuz_fetch_thread(fetcher: Fetcher, source: dict, board: dict, thread: dict, fetch_replies: bool) -> dict:
    """Collect all posts of one Discuz thread across its pagination."""
    record = _base_record(
        source,
        board["name"],
        title=thread["title"],
        url=thread["url"],
        thread_id=thread["tid"],
    )
    posts: list[dict] = []
    page = 1
    seen_pids: set[str] = set()
    while True:
        url = f"{source['base']}thread-{thread['tid']}-{page}-1.html"
        html = fetcher.get(url, source["encoding"])
        if not html:
            if page == 1:
                record["crawl_status"] = "fetch_failed"
            break
        soup = BeautifulSoup(html, "html.parser")
        page_new = 0
        for post in soup.find_all(id=re.compile(r"^post_\d+$")):
            pid = post.get("id")[5:]
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            author_node = post.find(class_="authi")
            author = _text(author_node.find("a")) if author_node else ""
            date = ""
            em = post.find(id=re.compile(r"^authorposton\d+$"))
            if em:
                m = _DATE_RE.search(em.get_text(" ", strip=True))
                date = m.group(1).strip() if m else _text(em)
            content_node = post.find(id=f"postmessage_{pid}")
            content = _text(content_node)
            posts.append(
                {"post_id": pid, "author": author, "published_at": date, "content_text": content}
            )
            page_new += 1
        if page_new == 0:
            break
        page += 1
    if posts:
        record["author"] = posts[0]["author"]
        record["published_at"] = posts[0]["published_at"]
        record["content_text"] = posts[0]["content_text"]
        record["reply_count"] = max(0, len(posts) - 1)
        if fetch_replies:
            record["replies"] = posts[1:]
    record["content_chars"] = len(record["content_text"])
    return record


# ---------------------------------------------------------------------------
# 回龙观社区网 adapter
# ---------------------------------------------------------------------------

_HLG_THREAD_RE = re.compile(r"showid\.php\?page=1&boardid=(\d+)&theid=(\d+)&bbscate=(\d+)")


def hlgnet_list_threads(fetcher: Fetcher, source: dict, board: dict, max_pages: int) -> list[dict]:
    threads: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        url = (
            f"{source['base']}frame.php?bbscate={board['bbscate']}"
            f"&boardid={board['boardid']}&page={page}"
        )
        html = fetcher.get(url, source["encoding"])
        if not html:
            break
        found = 0
        for m in _HLG_THREAD_RE.finditer(html):
            theid = m.group(2)
            if theid in threads:
                continue
            seg = html[m.end():m.end() + 400]
            title_m = re.search(r"target=\"down\">(.*?)</a>", seg, re.S)
            title = _SPACE_RE.sub(" ", re.sub(r"<[^>]+>", "", title_m.group(1))).strip() if title_m else ""
            threads[theid] = {
                "tid": theid,
                "title": title.removesuffix("(空)"),
                "url": f"{source['base']}showid.php?page=1&boardid={board['boardid']}&theid={theid}&bbscate={board['bbscate']}",
            }
            found += 1
        print(f"  list page {page}: +{found} threads")
        if found == 0:
            break
    return list(threads.values())


_HLG_REPLY_RE = re.compile(r"info/u1_(\d+)/")


_HLG_AUTHOR_RE = re.compile(r'alt="查看(.+?)个人资料"')
_HLG_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_HLG_REG_RE = re.compile(r"注册日期：\d{4}-\d{2}-\d{2}")


def _hlgnet_extract(html: str) -> tuple[str, str, str]:
    """Split one hlgnet post page into (author, date, content).

    Page text layout: header / author stats ending at ``注册日期：date`` /
    content / ``--`` signature divider / display name / post date /
    ``此文章已经被查看``.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]

    author_m = _HLG_AUTHOR_RE.search(html)
    author = author_m.group(1) if author_m else ""

    reg_idx = next((i for i, line in enumerate(lines) if _HLG_REG_RE.search(line)), None)
    end_idx = next(
        (i for i, line in enumerate(lines) if "此文章已经被查看" in line), None
    )
    if reg_idx is None or end_idx is None:
        return author, "", ""

    body = lines[reg_idx + 1 : end_idx]
    # 尾部签名：``--`` 之后是显示名 + 发帖时间
    date = ""
    if "--" in body:
        tail = body[body.index("--") + 1 :]
        date_m = _HLG_DATE_RE.search(" ".join(tail))
        if date_m:
            date = date_m.group(1)
        body = body[: body.index("--")]
    if not date:
        date_m = _HLG_DATE_RE.search(" ".join(body))
        date = date_m.group(1) if date_m else ""
    content = "\n".join(part for part in (line for line in body if line) if part)
    content = _SPACE_RE.sub(" ", content).strip()
    # 短帖无 ``--`` 签名线时，末尾的发帖时间留在正文里，去掉
    trailing = _HLG_DATE_RE.search(content[-25:])
    if trailing:
        content = content[: len(content) - 25 + trailing.start()].rstrip(" -")
    return author, date, content


def hlgnet_fetch_thread(fetcher: Fetcher, source: dict, board: dict, thread: dict, fetch_replies: bool) -> dict:
    """Collect the main post; replies follow their info/u1_ID/ links."""
    record = _base_record(
        source,
        board["name"],
        title=thread["title"],
        url=thread["url"],
        thread_id=thread["tid"],
    )
    html = fetcher.get(thread["url"], source["encoding"])
    if not html:
        record["crawl_status"] = "fetch_failed"
        return record
    record["author"], record["published_at"], record["content_text"] = _hlgnet_extract(html)
    record["content_chars"] = len(record["content_text"])

    reply_ids = []
    for m in _HLG_REPLY_RE.finditer(html):
        rid = m.group(1)
        if rid != thread["tid"] and rid not in reply_ids:
            reply_ids.append(rid)
    record["reply_count"] = len(reply_ids)
    if not fetch_replies or not reply_ids:
        return record

    # 「相关文章」列表里每条回复的标题/作者/日期
    reply_meta = re.findall(
        r"info/u1_(\d+)/\"[^>]*>(.*?)</a>.*?seename=([^\"']+)'[^>]*>(.*?)</a>&nbsp;</b><small>\(([^)]*)\)",
        html,
        re.S,
    )
    meta_by_id = {}
    for rid, rtitle, _, rauthor, rmeta in reply_meta:
        meta_by_id[rid] = (rtitle, rauthor, rmeta)

    for rid in reply_ids:
        url = f"{source['base']}info/u1_{rid}/"
        rhtml = fetcher.get(url, source["encoding"])
        if not rhtml:
            continue
        rauthor, rdate, rtext = _hlgnet_extract(rhtml)
        rtitle = _SPACE_RE.sub(" ", re.sub(r"<[^>]+>", "", meta_by_id.get(rid, ("",))[0])).strip()
        record["replies"].append(
            {
                "post_id": rid,
                "author": rauthor,
                "published_at": rdate,
                "content_text": rtext,
                "title_hint": rtitle,
            }
        )
    return record


# ---------------------------------------------------------------------------
# 水木社区 adapter（列表元数据；文章页游客验证码，不抓正文）
# ---------------------------------------------------------------------------

_SMTH_ROW_RE = re.compile(
    r'href="/nForum/article/(?P<board>[^/]+)/(?P<tid>\d+)"\s*title="在新窗口打开此主题".*?'
    r'class="title_9"><a href="/nForum/article/\1/\2">(?P<title>.*?)</a>.*?'
    r'class="title_10">(?P<date>[\d-]+)</td><td class="title_12">\|&ensp;'
    r'<a href="/nForum/user/query/(?P<author>[^"]+)"',
    re.S,
)


def newsmth_list_threads(fetcher: Fetcher, source: dict, board: dict, max_pages: int) -> list[dict]:
    raw: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        url = f"{source['base']}nForum/board/{board['board']}?p={page}"
        html = fetcher.get(url, source["encoding"])
        if not html:
            break
        found = 0
        for m in _SMTH_ROW_RE.finditer(html):
            tid = m.group("tid")
            if tid in raw:
                continue
            title = _SPACE_RE.sub(" ", re.sub(r"<[^>]+>", "", m.group("title"))).strip()
            raw[tid] = {
                "tid": tid,
                "title": title,
                "url": f"{source['base']}nForum/article/{board['board']}/{tid}",
                "author": m.group("author"),
                "date": m.group("date"),
            }
            found += 1
        print(f"  list page {page}: +{found} threads")
        if found == 0:
            break
    return list(raw.values())


def newsmth_make_record(source: dict, board: dict, thread: dict) -> dict:
    record = _base_record(
        source,
        board["name"],
        title=thread["title"],
        url=thread["url"],
        thread_id=thread["tid"],
    )
    record["author"] = thread.get("author", "")
    record["published_at"] = thread.get("date", "")
    record["crawl_status"] = "list_only_guest_captcha"
    return record


# ---------------------------------------------------------------------------
# 篱笆网 adapter（列表元数据；详情强制登录）
# ---------------------------------------------------------------------------

_LIBA_THREAD_RE = re.compile(r"t_(\d+)_(\d+)_1\.htm")


def liba_list_threads(fetcher: Fetcher, source: dict, board: dict, max_pages: int) -> list[dict]:
    threads: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        url = f"{source['base']}f_{board['fid']}_{page}.htm" if page > 1 else f"{source['base']}f_{board['fid']}.htm"
        html = fetcher.get(url, source["encoding"])
        if not html:
            break
        found = 0
        for a in BeautifulSoup(html, "html.parser").find_all("a", href=_LIBA_THREAD_RE):
            m = _LIBA_THREAD_RE.search(a["href"])
            tid = m.group(2)
            title = _text(a)
            if not title or tid in threads:
                continue
            threads[tid] = {
                "tid": tid,
                "title": title,
                "url": f"{source['base']}t_{m.group(1)}_{tid}_1.htm",
            }
            found += 1
        print(f"  list page {page}: +{found} threads")
        if found == 0:
            break
    return list(threads.values())


def liba_make_record(source: dict, board: dict, thread: dict) -> dict:
    record = _base_record(
        source,
        board["name"],
        title=thread["title"],
        url=thread["url"],
        thread_id=thread["tid"],
    )
    record["crawl_status"] = "list_only_login_required"
    return record


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def crawl_source(
    fetcher: Fetcher,
    source: dict,
    *,
    max_pages: int,
    max_threads: int,
    fetch_replies: bool,
    seen_urls: set[str],
    output: Path,
) -> int:
    print(f"[{source['id']}] {source['name']} ({source['region']})")
    written = 0
    for board in source["boards"]:
        print(f" board: {board['name']}")
        adapter = source["adapter"]
        if adapter == "discuz":
            threads = discuz_list_threads(fetcher, source, board, max_pages)
            make = lambda t: discuz_fetch_thread(fetcher, source, board, t, fetch_replies)
        elif adapter == "hlgnet":
            threads = hlgnet_list_threads(fetcher, source, board, max_pages)
            make = lambda t: hlgnet_fetch_thread(fetcher, source, board, t, fetch_replies)
        elif adapter == "newsmth":
            threads = newsmth_list_threads(fetcher, source, board, max_pages)
            make = lambda t: newsmth_make_record(source, board, t)
        elif adapter == "liba":
            threads = liba_list_threads(fetcher, source, board, max_pages)
            make = lambda t: liba_make_record(source, board, t)
        else:
            continue
        print(f"  threads discovered: {len(threads)}")
        for thread in threads[:max_threads]:
            if thread["url"] in seen_urls:
                continue
            record = make(thread)
            with output.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            seen_urls.add(thread["url"])
            written += 1
            flag = "" if record["crawl_status"] == "success" else f" [{record['crawl_status']}]"
            print(
                f"  + {record['title'][:40]} posts={record['reply_count'] + (1 if record['content_text'] else 0)}{flag}"
            )
    return written


def load_seen(output: Path, retry_failed: bool = False) -> set[str]:
    """Load previously collected thread URLs; optionally re-fetch failures.

    With ``retry_failed`` the failed records are dropped from the output file
    so those threads are collected again on this run (site rate limits are
    usually transient).
    """
    seen: set[str] = set()
    if not output.exists():
        return seen
    lines = output.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if retry_failed and record.get("crawl_status") == "fetch_failed":
            continue
        kept.append(line)
        seen.add(record.get("url", ""))
    if retry_failed and len(kept) != len(lines):
        output.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect K12 community forum threads and replies")
    parser.add_argument("--output", type=Path, default=Path("community/data/community_forum_posts.jsonl"))
    parser.add_argument("--max-pages", type=int, default=3, help="list pages per board")
    parser.add_argument("--max-threads", type=int, default=50, help="threads per board (0 = all)")
    parser.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    parser.add_argument("--no-replies", action="store_true", help="skip reply pages (hlgnet/discuz floors)")
    parser.add_argument("--retry-failed", action="store_true", help="drop fetch_failed records and recollect them")
    parser.add_argument("--sources", default="", help="comma-separated source ids; default all")
    args = parser.parse_args()

    wanted = {s.strip() for s in args.sources.split(",") if s.strip()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    seen = load_seen(args.output, retry_failed=args.retry_failed)
    print(f"resume: {len(seen)} threads already collected in {args.output}")

    fetcher = Fetcher(delay=args.delay)
    total = 0
    for source in SOURCES:
        if wanted and source["id"] not in wanted:
            continue
        total += crawl_source(
            fetcher,
            source,
            max_pages=args.max_pages,
            max_threads=args.max_threads or 10**9,
            fetch_replies=not args.no_replies,
            seen_urls=seen,
            output=args.output,
        )
    print(f"done: +{total} threads -> {args.output}")


if __name__ == "__main__":
    main()
