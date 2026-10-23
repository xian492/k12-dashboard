import importlib.util
import unittest
from pathlib import Path


COMMUNITY_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "community_crawler", COMMUNITY_ROOT / "tools" / "community_crawler.py"
)
community = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(community)


class BeijingCommunityCrawlerTests(unittest.TestCase):
    def test_defines_public_beijing_sources(self):
        ids = {source["id"] for source in community.BEIJING_SOURCES}

        self.assertEqual(
            ids,
            {
                "xschu",
                "newsmth-child-education",
                "xscxx",
                "hlgnet",
                "shaoyaojuwang",
                "xiaoshengchu-index",
            },
        )
        self.assertTrue(all(source["url"].startswith("https://") for source in community.BEIJING_SOURCES))

    def test_keeps_local_education_link_and_normalizes_fields(self):
        item = community.normalize_link(
            {
                "text": "海淀区小升初报名政策和入学材料说明",
                "href": "https://example.com/article-1",
            },
            community.BEIJING_SOURCES[0],
        )

        self.assertEqual(item["title"], "海淀区小升初报名政策和入学材料说明")
        self.assertEqual(item["link"], "https://example.com/article-1")
        self.assertEqual(item["region"], "北京")
        self.assertEqual(item["source"], "北京小升初网")
        self.assertIn("小升初", item["tags"])

    def test_discards_ads_and_unrelated_links(self):
        links = [
            {"text": "海淀区小升初报名政策", "href": "https://www.xschu.com/policy"},
            {"text": "家长分享孩子今年的学习体验", "href": "https://www.xschu.com/experience"},
            {"text": "小升初免费资料领取加微信", "href": "https://www.xschu.com/ad"},
            {"text": "北京小升初家长交流群", "href": "https://www.xschu.com/group"},
            {"text": "北京二手房学区房出售", "href": "https://www.xschu.com/house"},
            {"text": "学校简介", "href": "https://www.xschu.com/about"},
            {"text": "联系我们", "href": "https://www.xschu.com/contact"},
        ]

        result = community.extract_candidate_links(links, community.BEIJING_SOURCES[0])

        self.assertEqual(
            [item["link"] for item in result],
            ["https://www.xschu.com/policy", "https://www.xschu.com/experience"],
        )

    def test_keeps_most_descriptive_anchor_for_duplicate_thread_link(self):
        shaoyaoju = next(source for source in community.BEIJING_SOURCES if source["id"] == "shaoyaojuwang")
        links = [
            {"text": "有新回复 - 新窗口打开", "href": "https://www.shaoyaojuwang.com/thread-493-1-1.html"},
            {"text": "2026年，芍药居1年级新生，提前到校时间", "href": "https://www.shaoyaojuwang.com/thread-493-1-1.html"},
        ]

        result = community.extract_candidate_links(links, shaoyaoju)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "2026年，芍药居1年级新生，提前到校时间")

