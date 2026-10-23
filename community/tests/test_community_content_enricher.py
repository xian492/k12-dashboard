import importlib.util
import unittest
from pathlib import Path


COMMUNITY_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "community_content_enricher", COMMUNITY_ROOT / "tools" / "community_content_enricher.py"
)
enricher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(enricher)


class CommunityContentEnricherTests(unittest.TestCase):
    def test_extracts_article_body_after_site_navigation(self):
        record = {
            "source_id": "xscxx",
            "title": "2027小升初报名政策",
            "link": "https://www.xschu.com/zhengcezixun/88303.html",
            "content_text_clean": (
                "首页 政策资讯 登录\n"
                "2027小升初报名政策\n"
                "2026-10-22 09:33|编辑: 赵老师\n"
                "摘要\n"
                "报名时间、划片和入学材料说明。\n"
                "正文第一段，介绍报名和入学安排。\n" * 5
            ),
        }
        result = enricher.enrich_record(record)
        self.assertIn("正文第一段", result["body_text"])
        self.assertNotIn("首页 政策资讯 登录", result["body_text"])
        self.assertEqual(result["body_extraction_method"], "title_anchor")

    def test_uses_xschu_summary_as_article_body_anchor(self):
        result = enricher.enrich_record(
            {
                "source_id": "xschu",
                "title": "2027小升初全年时间线",
                "link": "https://www.xschu.com/zhengcezixun/88303.html",
                "content_text_clean": (
                    "首页 政策资讯 登录\n热搜\n2027年北京小升初全年时间线\n"
                    "2026-10-22 09:33|编辑: 赵老师\n摘要\n"
                    "这是摘要内容。\n这是正文内容，包含报名、入学和划片安排。" * 6
                ),
            }
        )
        self.assertEqual(result["body_extraction_method"], "summary_anchor")
        self.assertNotIn("首页 政策资讯 登录", result["body_text"])

    def test_normalizes_date_from_xscxx_url(self):
        result = enricher.enrich_record(
            {
                "source_id": "xscxx",
                "title": "北京学校招生通知",
                "link": "https://www.xscxx.com/xiaoshengchu/hdqxsc/2026102114262.html",
                "content_text_clean": "北京学校招生通知" * 40,
            }
        )
        self.assertEqual(result["published_at_normalized"], "2026-10-21")
        self.assertEqual(result["date_confidence"], "high")

    def test_extracts_shaoyaojuwang_forum_post_after_post_metadata(self):
        result = enricher.enrich_record(
            {
                "source_id": "shaoyaojuwang",
                "title": "本版置顶主题 - 新窗口打开",
                "link": "https://www.shaoyaojuwang.com/thread-444-1-1.html",
                "content_text_clean": (
                    "论坛导航 登录\n发表于 2026-05-21 18:55:18 | 只看该作者 | "
                    "（630政策汇总）2022-2026年，每年芍药居小学，初中，都是执行630政策。\n"
                    "返回列表"
                ),
            }
        )
        self.assertEqual(result["body_extraction_method"], "forum_post_anchor")
        self.assertIn("630政策", result["body_text"])

    def test_recovers_forum_subject_and_board_tag_from_detail_page(self):
        result = enricher.enrich_record(
            {
                "source_id": "shaoyaojuwang",
                "title": "有新回复 - 新窗口打开",
                "link": "https://www.shaoyaojuwang.com/thread-493-1-1.html",
                "content_text_clean": (
                    "## [![芍药居社区网](https://www.shaoyaojuwang.com/logo.png)](https://www.shaoyaojuwang.com/)\n"
                    "#  [[小学]](https://www.shaoyaojuwang.com/forum.php?mod=forumdisplay&fid=6) "
                    "2026年，芍药居1年级新生，提前到校时间：8月29日、8月30日\n"
                    "### 浏览过的版块\n"
                ),
            }
        )

        self.assertEqual(result["title"], "2026年，芍药居1年级新生，提前到校时间：8月29日、8月30日")
        self.assertTrue(result["title_recovered"])
        self.assertEqual(result["stage"], ["小学"])

    def test_board_tag_policy_does_not_claim_a_school_stage(self):
        result = enricher.enrich_record(
            {
                "source_id": "shaoyaojuwang",
                "title": "有新回复 - 新窗口打开",
                "link": "https://www.shaoyaojuwang.com/thread-444-1-1.html",
                "content_text_clean": (
                    "#  [[政策]](https://www.shaoyaojuwang.com/forum.php?mod=forumdisplay&fid=6) "
                    "（630政策汇总）2022-2026年，每年芍药居小学，初中，都是执行630政策。\n"
                ),
            }
        )

        self.assertEqual(result["title"], "（630政策汇总）2022-2026年，每年芍药居小学，初中，都是执行630政策。")
        self.assertEqual(result.get("stage", []), [])

    def test_board_tag_does_not_overwrite_existing_stage(self):
        result = enricher.enrich_record(
            {
                "source_id": "shaoyaojuwang",
                "title": "有新回复 - 新窗口打开",
                "link": "https://www.shaoyaojuwang.com/thread-457-1-1.html",
                "stage": ["小升初"],
                "content_text_clean": (
                    "#  [[初中]](https://www.shaoyaojuwang.com/forum.php?mod=forumdisplay&fid=6) "
                    "2025年人朝初中（初一新生）领取通知书时间地点（7月5日上午）。\n"
                ),
            }
        )

        self.assertEqual(result["stage"], ["小升初"])

    def test_keeps_original_title_when_anchor_text_is_not_boilerplate(self):
        result = enricher.enrich_record(
            {
                "source_id": "shaoyaojuwang",
                "title": "（630政策汇总）2022-2026年芍药居入学政策",
                "link": "https://www.shaoyaojuwang.com/thread-444-1-1.html",
                "content_text_clean": "# [[政策]](https://example.com) 无关标题",
            }
        )

        self.assertEqual(result["title"], "（630政策汇总）2022-2026年芍药居入学政策")
        self.assertNotIn("title_recovered", result)

    def test_extracts_school_and_district_candidates_and_fingerprint(self):
        result = enricher.enrich_record(
            {
                "source_id": "xschu",
                "title": "海淀区人大附中小升初报名",
                "link": "https://example.com/1",
                "content_text_clean": "海淀区人大附中和清华附中报名材料及时间安排。" * 20,
            }
        )
        self.assertIn("人大附中", result["school_candidates"])
        self.assertIn("海淀区", result["district_candidates"])
        self.assertEqual(len(result["content_fingerprint"]), 64)


if __name__ == "__main__":
    unittest.main()
