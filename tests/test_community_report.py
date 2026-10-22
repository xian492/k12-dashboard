import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "community_report", ROOT / "tools" / "community_report.py"
)
community_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(community_report)


class CommunityReportTests(unittest.TestCase):
    def test_extracts_unique_markdown_sources_with_labels(self):
        markdown = """
        [家长帮](https://example.com/) · [重复](https://example.com/)
        [论坛](https://forum.example.com/)
        """

        result = community_report.extract_sources(markdown)

        self.assertEqual(
            result,
            [
                {"label": "家长帮", "url": "https://example.com/"},
                {"label": "论坛", "url": "https://forum.example.com/"},
            ],
        )

    def test_extracts_source_category_from_headings(self):
        markdown = """
        ## 全国性入口
        [家长帮](https://example.com/parents)
        ### 北京
        [地方论坛](https://example.com/local)
        """

        result = community_report.extract_sources(markdown)

        self.assertEqual(result[0]["category"], "全国性入口")
        self.assertEqual(result[1]["category"], "全国性入口 / 北京")

    def test_classifies_blocked_result_from_error_text(self):
        self.assertEqual(
            community_report.classify_result(
                success=False,
                markdown="",
                links=0,
                error="Blocked by anti-bot protection",
            ),
            "blocked",
        )

    def test_classifies_successful_page_with_content(self):
        self.assertEqual(
            community_report.classify_result(
                success=True,
                markdown="页面正文",
                links=12,
                error="",
            ),
            "success",
        )

    def test_classifies_not_found_page_as_failed(self):
        self.assertEqual(
            community_report.classify_result(
                success=True,
                markdown="# 404 Not Found",
                links=0,
                error="",
            ),
            "failed",
        )

    def test_render_report_leads_with_findings_and_groups_details(self):
        report = community_report.render_report(
            [
                {
                    "label": "公开论坛",
                    "url": "https://example.com/forum",
                    "status": "success",
                    "http_status": 200,
                    "markdown_chars": 1200,
                    "internal_links": 24,
                    "preview": "论坛正文预览",
                    "error": "",
                    "seconds": 1.2,
                },
                {
                    "label": "受限来源",
                    "url": "https://example.com/blocked",
                    "status": "blocked",
                    "http_status": 403,
                    "markdown_chars": 0,
                    "internal_links": 0,
                    "preview": "",
                    "error": "Blocked by anti-bot protection",
                    "seconds": 2.3,
                },
            ],
            "docs/sources.md",
            "2026-10-22 12:00:00 +0800",
        )

        self.assertIn("## 一、结论摘要", report)
        self.assertIn("## 二、结果分组", report)
        self.assertIn("## 三、来源明细", report)
        self.assertIn("公开论坛", report)
        self.assertIn("受限来源", report)
        self.assertIn("入口巡检成功不等于内容质量已验证", report)
        self.assertIn("原始链接", report)
        self.assertIn("| 公开论坛 | [https://example.com/forum](https://example.com/forum) |", report)
        self.assertIn("| 社区/名称 | 原始链接 |", report)
