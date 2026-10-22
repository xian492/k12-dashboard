import importlib.util
import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "school_crawler", ROOT / "tools" / "school_crawler.py"
)
school_crawler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(school_crawler)
CLI_SPEC = importlib.util.spec_from_file_location(
    "probe_school_websites", ROOT / "tools" / "probe_school_websites.py"
)
probe_cli = importlib.util.module_from_spec(CLI_SPEC)
CLI_SPEC.loader.exec_module(probe_cli)


class SchoolCrawlerPureFunctionTests(unittest.TestCase):
    def test_normalize_url_resolves_relative_path(self):
        result = school_crawler.normalize_url("../news/1.html", "https://school.example.edu.cn/list/")

        self.assertEqual(result, "https://school.example.edu.cn/news/1.html")

    def test_extract_internal_links_filters_external_and_navigation_links(self):
        links = [
            {"text": "校园新闻", "href": "/news/"},
            {"text": "招生通知", "href": "https://school.example.edu.cn/admission/"},
            {"text": "联系我们", "href": "/contact/"},
            {"text": "网站备案", "href": "/beian/"},
            {"text": "外部链接", "href": "https://other.example.com/news/"},
            {"text": "校园新闻", "href": "/news/"},
        ]

        result = school_crawler.extract_internal_links(
            links,
            "https://school.example.edu.cn/",
            {"school.example.edu.cn"},
        )

        self.assertEqual(
            [(item["title"], item["url"]) for item in result],
            [
                ("校园新闻", "https://school.example.edu.cn/news/"),
                ("招生通知", "https://school.example.edu.cn/admission/"),
            ],
        )

    def test_rank_section_candidates_prioritizes_school_content_sections(self):
        links = [
            {"title": "联系我们", "url": "https://school.example.edu.cn/contact/"},
            {"title": "校园新闻", "url": "https://school.example.edu.cn/news/"},
            {"title": "招生通知", "url": "https://school.example.edu.cn/admission/"},
            {
                "title": "2026年招生通知详细内容",
                "url": "https://school.example.edu.cn/news/202610/t20261022_1.shtml",
            },
            {
                "title": "招生简章详细内容",
                "url": "https://school.example.edu.cn/AdmissionsInformation/88/16404.html",
            },
            {"title": "学校简介", "url": "https://school.example.edu.cn/about/"},
        ]

        result = school_crawler.rank_section_candidates(links)

        self.assertEqual(
            [item["title"] for item in result],
            ["校园新闻", "招生通知"],
        )


class _FakeResult:
    def __init__(self, *, success=True, url="https://school.example.edu.cn/", links=None, error=""):
        self.success = success
        self.url = url
        self.links = links or {"internal": []}
        self.error_message = error


class _FakeCrawler:
    def __init__(self, results):
        self.results = iter(results)
        self.urls = []

    async def arun(self, *, url, config):
        self.urls.append(url)
        return next(self.results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class SchoolCrawlerAsyncTests(unittest.TestCase):
    def test_probe_school_returns_normalized_success_report(self):
        crawler = _FakeCrawler(
            [
                _FakeResult(
                    url="https://new.school.example.edu.cn/",
                    links={
                        "internal": [
                            {"text": "校园新闻", "href": "/news/"},
                            {"text": "联系我们", "href": "/contact/"},
                        ]
                    },
                )
            ]
        )

        result = asyncio.run(
            school_crawler.probe_school(
                crawler,
                {
                    "school": "测试学校",
                    "district": "海淀区",
                    "homepage": "https://school.example.edu.cn/",
                    "allowed_hosts": {"school.example.edu.cn", "new.school.example.edu.cn"},
                },
            )
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_url"], "https://new.school.example.edu.cn/")
        self.assertEqual(result["candidate_sections"][0]["title"], "校园新闻")
        self.assertEqual(result["items_found"], 1)

    def test_probe_school_returns_failure_report_without_raising(self):
        result = asyncio.run(
            school_crawler.probe_school(
                _FakeCrawler([_FakeResult(success=False, error="timeout")]),
                {
                    "school": "失败学校",
                    "district": "海淀区",
                    "homepage": "https://school.example.edu.cn/",
                    "allowed_hosts": {"school.example.edu.cn"},
                },
            )
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "timeout")

    def test_probe_schools_isolates_one_failed_school(self):
        original_factory = school_crawler._make_crawler
        school_crawler._make_crawler = lambda: _FakeCrawler(
            [
                _FakeResult(
                    links={"internal": [{"text": "学校新闻", "href": "/news/"}]}
                ),
                _FakeResult(success=False, error="blocked"),
            ]
        )
        try:
            results = asyncio.run(
                school_crawler.probe_schools(
                    [
                        {
                            "school": "成功学校",
                            "district": "海淀区",
                            "homepage": "https://school.example.edu.cn/",
                            "allowed_hosts": {"school.example.edu.cn"},
                        },
                        {
                            "school": "失败学校",
                            "district": "海淀区",
                            "homepage": "https://school.example.edu.cn/",
                            "allowed_hosts": {"school.example.edu.cn"},
                        },
                    ]
                )
            )
        finally:
            school_crawler._make_crawler = original_factory

        self.assertEqual([result["status"] for result in results], ["success", "failed"])


class SchoolCrawlerReportTests(unittest.TestCase):
    def test_write_probe_report_preserves_success_failure_and_timestamp(self):
        report = [
            {"school": "成功学校", "status": "success", "checked_at": "2026-10-22T00:00:00+00:00"},
            {"school": "失败学校", "status": "failed", "error": "timeout", "checked_at": "2026-10-22T00:00:01+00:00"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "report.json"
            probe_cli.write_probe_report(report, output)
            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(saved, report)

    def test_cli_requires_output_argument(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "probe_school_websites.py")],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("--output", completed.stderr)


if __name__ == "__main__":
    unittest.main()
