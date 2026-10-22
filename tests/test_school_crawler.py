import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "school_crawler", ROOT / "tools" / "school_crawler.py"
)
school_crawler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(school_crawler)


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
            {"title": "学校简介", "url": "https://school.example.edu.cn/about/"},
        ]

        result = school_crawler.rank_section_candidates(links)

        self.assertEqual(
            [item["title"] for item in result],
            ["校园新闻", "招生通知"],
        )


if __name__ == "__main__":
    unittest.main()
