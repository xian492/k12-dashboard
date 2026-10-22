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
BUILD_SPEC = importlib.util.spec_from_file_location("dashboard_build", ROOT / "tools" / "build.py")
dashboard_build = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(dashboard_build)
CLI_SPEC = importlib.util.spec_from_file_location(
    "probe_school_websites", ROOT / "tools" / "probe_school_websites.py"
)
probe_cli = importlib.util.module_from_spec(CLI_SPEC)
CLI_SPEC.loader.exec_module(probe_cli)


class SchoolCrawlerPureFunctionTests(unittest.TestCase):
    def test_make_crawler_does_not_depend_on_a_file_logger(self):
        crawler = school_crawler._make_crawler()

        self.assertIsNone(crawler.logger.log_file)

    def test_build_school_probe_specs_covers_catalog_homepages(self):
        specs = school_crawler.build_school_probe_specs(
            dashboard_build.SCHOOL_CATALOG,
            dashboard_build.SCHOOL_HOMEPAGES,
        )

        self.assertGreaterEqual(len(specs), 100)
        self.assertTrue(all(spec["school"] and spec["district"] for spec in specs))
        self.assertTrue(all("allowed_hosts" in spec and "enabled" in spec for spec in specs))
        self.assertEqual(
            len({(spec["district"], spec["school"]) for spec in specs}),
            len(specs),
        )

    def test_district_directory_fallbacks_are_not_school_crawl_targets(self):
        specs = school_crawler.build_school_probe_specs(
            dashboard_build.SCHOOL_CATALOG,
            dashboard_build.SCHOOL_HOMEPAGES,
        )
        by_school = {
            (spec["district"], spec["school"]): spec
            for spec in specs
        }

        self.assertFalse(by_school[("东城区", "北京市第二中学")]["enabled"])
        self.assertEqual(by_school[("东城区", "北京市第二中学")]["homepage"], "")
        self.assertTrue(by_school[("海淀区", "人大附中")]["enabled"])

    def test_build_school_probe_specs_ignores_empty_and_javascript_homepages(self):
        specs = school_crawler.build_school_probe_specs(
            {"测试区": ["有效学校", "空链接学校", "脚本学校"]},
            {
                "有效学校": "https://school.example.edu.cn/",
                "空链接学校": "",
                "脚本学校": "javascript:void(0)",
            },
        )

        self.assertEqual([spec["school"] for spec in specs], ["有效学校", "空链接学校", "脚本学校"])
        self.assertTrue(specs[0]["enabled"])
        self.assertFalse(specs[1]["enabled"])
        self.assertFalse(specs[2]["enabled"])

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

    def test_extract_article_links_limits_detail_pages_and_filters_navigation(self):
        links = [
            {"text": "2026年校园新闻", "href": "/news/202610/t20261022_1.shtml"},
            {"text": "2026年第二条新闻", "href": "/news/202610/t20261021_2.shtml"},
            {"text": "下一页", "href": "/news/page/2/"},
            {"text": "外部文章", "href": "https://other.example.com/a"},
        ]

        result = school_crawler.extract_article_links(
            links,
            "https://school.example.edu.cn/news/",
            limit=1,
        )

        self.assertEqual(result, [{
            "title": "2026年校园新闻",
            "url": "https://school.example.edu.cn/news/202610/t20261022_1.shtml",
        }])

    def test_normalize_school_item_extracts_date_and_marks_date_source(self):
        spec = {"school": "测试学校", "district": "海淀区", "homepage": "https://school.example.edu.cn/"}

        dated = school_crawler.normalize_school_item(
            {"title": "校园新闻", "url": "https://school.example.edu.cn/news/1.html", "date": "2026-10-22"},
            spec,
            "https://school.example.edu.cn/news/",
        )
        undated = school_crawler.normalize_school_item(
            {"title": "没有日期的新闻", "url": "https://school.example.edu.cn/news/2.html"},
            spec,
            "https://school.example.edu.cn/news/",
        )

        self.assertEqual(dated["published_at"], "2026-10-22")
        self.assertEqual(dated["date_source"], "page")
        self.assertEqual(undated["date_source"], "crawl")
        self.assertEqual(undated["school"], "测试学校")


class _FakeResult:
    def __init__(self, *, success=True, url="https://school.example.edu.cn/", links=None, error="", title="", date="", markdown=""):
        self.success = success
        self.url = url
        self.links = links or {"internal": []}
        self.error_message = error
        self.title = title
        self.date = date
        self.markdown = markdown


class _FakeCrawler:
    def __init__(self, results):
        self.results = iter(results)
        self.urls = []
        self.configs = []

    async def arun(self, *, url, config):
        self.urls.append(url)
        self.configs.append(config)
        return next(self.results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class SchoolCrawlerAsyncTests(unittest.TestCase):
    def test_probe_school_retries_transient_timeout_and_then_succeeds(self):
        crawler = _FakeCrawler(
            [
                _FakeResult(success=False, error="Page.goto: Timeout 30000ms exceeded."),
                _FakeResult(links={"internal": [{"text": "招生", "href": "/admissions/"}]}),
            ]
        )
        had_delay = hasattr(school_crawler, "PROBE_RETRY_DELAY_SECONDS")
        original_delay = getattr(school_crawler, "PROBE_RETRY_DELAY_SECONDS", None)
        school_crawler.PROBE_RETRY_DELAY_SECONDS = 0
        try:
            result = asyncio.run(
                school_crawler.probe_school(
                    crawler,
                    {
                        "school": "测试学校",
                        "district": "通州区",
                        "homepage": "https://school.example.edu.cn/",
                        "allowed_hosts": {"school.example.edu.cn"},
                    },
                )
            )
        finally:
            if had_delay:
                school_crawler.PROBE_RETRY_DELAY_SECONDS = original_delay
            else:
                del school_crawler.PROBE_RETRY_DELAY_SECONDS

        self.assertEqual(result["status"], "success")
        self.assertEqual(crawler.urls, ["https://school.example.edu.cn/"] * 2)
        self.assertEqual(
            [config.page_timeout for config in crawler.configs],
            [30000, 45000],
        )

    def test_probe_school_does_not_retry_permanent_failure(self):
        crawler = _FakeCrawler([_FakeResult(success=False, error="HTTP 403 blocked")])

        result = asyncio.run(
            school_crawler.probe_school(
                crawler,
                {
                    "school": "测试学校",
                    "district": "通州区",
                    "homepage": "https://school.example.edu.cn/",
                    "allowed_hosts": {"school.example.edu.cn"},
                },
            )
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(crawler.urls, ["https://school.example.edu.cn/"])

    def test_crawl_school_updates_crawls_sections_and_details(self):
        crawler = _FakeCrawler(
            [
                _FakeResult(
                    links={"internal": [{"text": "校园新闻", "href": "/news/"}]}
                ),
                _FakeResult(
                    links={"internal": [{"text": "2026年校园新闻", "href": "/news/202610/t20261022_1.shtml"}]}
                ),
                _FakeResult(
                    url="https://school.example.edu.cn/news/202610/t20261022_1.shtml",
                    title="2026年校园新闻",
                    date="2026-10-22",
                    markdown="# 2026年校园新闻\n学校活动内容",
                ),
            ]
        )

        result = asyncio.run(
            school_crawler.crawl_school_updates(
                crawler,
                {
                    "school": "测试学校",
                    "district": "海淀区",
                    "homepage": "https://school.example.edu.cn/",
                    "allowed_hosts": {"school.example.edu.cn"},
                    "enabled": True,
                },
            )
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["updates"]), 1)
        self.assertEqual(result["updates"][0]["title"], "2026年校园新闻")
        self.assertEqual(result["updates"][0]["published_at"], "2026-10-22")

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
                    "allowed_hosts": {"school.example.edu.cn"},
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
                _FakeCrawler([_FakeResult(success=False, error="blocked")]),
                {
                    "school": "失败学校",
                    "district": "海淀区",
                    "homepage": "https://school.example.edu.cn/",
                    "allowed_hosts": {"school.example.edu.cn"},
                },
            )
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "blocked")

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

    def test_crawl_schools_updates_returns_disabled_report_without_crawling(self):
        original_factory = school_crawler._make_crawler
        school_crawler._make_crawler = lambda: _FakeCrawler([])
        try:
            results = asyncio.run(
                school_crawler.crawl_schools_updates(
                    [
                        {
                            "school": "不可用学校",
                            "district": "海淀区",
                            "homepage": "",
                            "allowed_hosts": set(),
                            "enabled": False,
                        }
                    ]
                )
            )
        finally:
            school_crawler._make_crawler = original_factory

        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[0]["error"], "disabled")


class SchoolCrawlerReportTests(unittest.TestCase):
    def test_probe_cli_uses_full_school_catalog(self):
        self.assertGreaterEqual(len(probe_cli.SCHOOL_PROBE_SPECS), 100)

    def test_probe_cli_runs_full_update_crawl(self):
        original_crawler = probe_cli.crawl_schools_updates

        async def fake_crawler(specs):
            return [{"school": "测试学校", "status": "success", "updates": [{"title": "校园新闻"}]}]

        probe_cli.crawl_schools_updates = fake_crawler
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "report.json"
                asyncio.run(probe_cli.run(output))
                saved = json.loads(output.read_text(encoding="utf-8"))
        finally:
            probe_cli.crawl_schools_updates = original_crawler

        self.assertEqual(saved[0]["updates"][0]["title"], "校园新闻")

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
