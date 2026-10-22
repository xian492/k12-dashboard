import importlib.util
import unittest
from pathlib import Path


COMMUNITY_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "community_content_cleaner", COMMUNITY_ROOT / "tools" / "community_content_cleaner.py"
)
cleaner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleaner)


class CommunityContentCleanerTests(unittest.TestCase):
    def test_marks_policy_page_as_valid_and_classifies_it(self):
        result = cleaner.clean_record(
            {
                "title": "2027北京小升初报名和划片政策",
                "link": "https://example.com/post/1",
                "source_id": "xschu",
                "source": "北京小升初网",
                "region": "北京",
                "tags": ["小升初", "报名"],
                "published_at_hint": "2026-10-22",
                "crawl_status": "success",
                "content_text": "北京小升初报名时间、划片范围和入学材料说明。" * 20,
            }
        )

        self.assertTrue(result["valid_result"])
        self.assertEqual(result["content_type"], "政策与流程")
        self.assertIn("报名", result["event_type"])
        self.assertEqual(result["region_confidence"], "high")
        self.assertEqual(result["needs_official_verification"], True)

    def test_rejects_resource_and_login_pages(self):
        resource = cleaner.clean_record(
            {
                "title": "小学试卷答案资料下载",
                "link": "https://example.com/download",
                "source_id": "xschu",
                "source": "北京小升初网",
                "region": "北京",
                "crawl_status": "success",
                "content_text": "小学试卷答案资料下载" * 20,
            }
        )
        login = cleaner.clean_record(
            {
                "title": "登录",
                "link": "https://example.com/login",
                "source_id": "xschu",
                "source": "北京小升初网",
                "region": "北京",
                "crawl_status": "login_required",
                "content_text": "",
            }
        )

        self.assertFalse(resource["valid_result"])
        self.assertEqual(resource["content_type"], "资源与培训")
        self.assertFalse(login["valid_result"])
        self.assertEqual(login["content_type"], "账号与导航")

    def test_rejects_section_page_even_when_it_contains_long_navigation_text(self):
        result = cleaner.clean_record(
            {
                "title": "海淀区小升初",
                "link": "https://www.xscxx.com/xiaoshengchu/hdqxsc/",
                "source_id": "xscxx",
                "source": "北京小升初信息网",
                "region": "北京",
                "crawl_status": "success",
                "content_text": "家长 学校 小升初 导航内容" * 100,
            }
        )

        self.assertFalse(result["valid_result"])
        self.assertEqual(result["content_type"], "账号与导航")

    def test_marks_parent_experience_without_official_claim_as_uncertain(self):
        result = cleaner.clean_record(
            {
                "title": "家长分享孩子在海淀某校的分班经历",
                "link": "https://www.shaoyaojuwang.com/thread-123-1-1.html",
                "source_id": "shaoyaojuwang",
                "source": "芍药居社区网",
                "region": "北京",
                "crawl_status": "success",
                "content_text": "家长反馈、个人经历和分班感受。" * 20,
            }
        )

        self.assertTrue(result["valid_result"])
        self.assertEqual(result["content_type"], "家长经验")
        self.assertEqual(result["needs_official_verification"], True)

    def test_rejects_shaoyaojuwang_portal_and_forum_pages(self):
        result = cleaner.clean_record(
            {
                "title": "论坛BBS",
                "link": "https://www.shaoyaojuwang.com/forum.php",
                "source_id": "shaoyaojuwang",
                "source": "芍药居社区网",
                "region": "北京",
                "crawl_status": "success",
                "content_text": "入学政策 小升初 报名" * 100,
            }
        )
        self.assertFalse(result["valid_result"])
