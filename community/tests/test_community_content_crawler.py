import importlib.util
import unittest
from pathlib import Path


COMMUNITY_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "community_content_crawler", COMMUNITY_ROOT / "tools" / "community_content_crawler.py"
)
content_crawler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(content_crawler)


class CommunityContentCrawlerTests(unittest.TestCase):
    def test_classifies_content_page(self):
        self.assertEqual(
            content_crawler.classify_content(
                success=True,
                markdown="标题\n\n这是正文内容。" * 20,
                error="",
            ),
            "success",
        )

    def test_rejects_login_and_not_found_pages(self):
        self.assertEqual(
            content_crawler.classify_content(
                success=True,
                markdown="请登录后查看全部内容",
                error="",
            ),
            "login_required",
        )
        self.assertEqual(
            content_crawler.classify_content(
                success=True,
                markdown="# 404 Not Found",
                error="",
            ),
            "not_found",
        )
        self.assertEqual(
            content_crawler.classify_content(
                success=True,
                markdown="登录页正文看起来很长" * 20,
                error="",
                candidate_title="登录",
            ),
            "login_required",
        )

    def test_normalizes_result_with_content_and_metadata(self):
        result = content_crawler.normalize_content_result(
            {
                "title": "北京小升初报名政策",
                "link": "https://example.com/post/1",
                "source": "示例社区",
                "region": "北京",
                "tags": ["小升初"],
            },
            status="success",
            markdown="标题\n\n正文内容",
            error="",
            crawled_at="2026-10-22T10:00:00+00:00",
        )

        self.assertEqual(result["title"], "北京小升初报名政策")
        self.assertEqual(result["source"], "示例社区")
        self.assertEqual(result["content_text"], "标题\n\n正文内容")
        self.assertEqual(result["crawl_status"], "success")
        self.assertEqual(result["crawled_at"], "2026-10-22T10:00:00+00:00")
