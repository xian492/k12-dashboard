import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("community_stage", ROOT / "tools" / "community_stage.py")
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


class StageClassificationTests(unittest.TestCase):
    """学段按“内容里的孩子在哪个学段”判定；标题信号优先于正文。"""

    def test_grade_anchor_beats_transition_word(self):
        # 新初一分班/月考：孩子已在初中，压过标题或正文里的小升初。
        for title in (
            "2026年朝阳陈分新初一月考成绩、分班情况一览",
            "八十中和北京中学新初一分班曝光，实验班比例有多高？",
            "海淀初一国庆作业参考！9大学科作业一览",
        ):
            self.assertEqual(stage.classify_stage(title), ["中学"], title)

    def test_school_type_anchor_when_no_grade_word(self):
        # 无年级词时，校名后缀定位学段。
        self.assertEqual(
            stage.classify_stage("清华附中志新校情介绍：师资、SY班、作业考试、校园生活一览"),
            ["中学"],
        )
        self.assertEqual(stage.classify_stage("2026西城区各中学班级数量汇总"), ["中学"])

    def test_transition_words_map_to_own_phases(self):
        self.assertEqual(stage.classify_stage("2027小升初全年时间线、本月大事件→"), ["小升初"])
        self.assertEqual(stage.classify_stage("生源到达峰值！丰台区2027中考人数、竞争趋势完整解读"), ["初升高"])
        self.assertEqual(stage.classify_stage("2025年8月信息：人大附中凤凰城高中新高一10个班")[0], "高中")

    def test_kindergarten_and_xsc(self):
        self.assertEqual(stage.classify_stage("幼儿园入学登记信息汇总"), ["幼儿园"])
        self.assertEqual(stage.classify_stage("2026年北京XSC动态，持续更新中ing..."), ["小升初"])

    def test_board_tag_fallback(self):
        # 内容型版块映射；身份型版块（家有X学生）不映射，育儿帖归综合。
        self.assertEqual(stage.classify_stage("孩子还小，求经验", board="早教幼教"), ["幼儿园"])
        self.assertEqual(stage.classify_stage("中考前怎么安排", board="中高考"), ["初升高"])
        self.assertEqual(stage.classify_stage("孩子作业写不完怎么办", board="社区论坛"), [])
        self.assertEqual(stage.classify_stage("真正的亲子阅读心得", board="家有小学生"), [])

    def test_no_signal_returns_empty_for_general(self):
        # 无学段锚点的育儿内容归“综合”（渲染层的空 stage 哨兵）。
        self.assertEqual(stage.classify_stage("真正的亲子阅读，不应该是一条直线"), [])

    def test_body_fallback_after_title_miss(self):
        self.assertEqual(stage.classify_stage("转学通知", "朝阳区初一转学安排"), ["中学"])


class RelevanceGateTests(unittest.TestCase):
    """相关性只信标题与核心正文：侧栏噪声和生活杂帖出局。"""

    def test_festival_greetings_are_rejected(self):
        title = "2026年中秋节祝福语合集（100条分4大类：领导客户/恋人/朋友圈/通用短句）"
        self.assertFalse(stage.relevant_article(title, "正文提及小升初和中考的侧栏链接"))
        self.assertFalse(stage.relevant_forum(title))

    def test_forum_off_topic_posts_are_rejected(self):
        for title in (
            "医生不可能只通过电话和微信就能指导病人完成阑尾手术，律师其实也一样",
            "律师本身就是高收入，虽然现在没有以前高了",
            "ai暂时还开不了庭。",
            "[666][666][666]",
            "",
        ):
            self.assertFalse(stage.relevant_forum(title), title)

    def test_parenting_posts_pass_via_title(self):
        self.assertTrue(stage.relevant_forum("开家长会很累"))
        self.assertTrue(stage.relevant_forum("真正的亲子阅读，不应该是一条直线"))

    def test_education_titles_pass(self):
        for title in (
            "丰台新增 2880 个学位三校 9 月启用",
            "2027北京小升初入学指南",
            "北京供暖新消息",
        ):
            if title == "北京供暖新消息":
                self.assertFalse(stage.relevant_article(title, ""), title)
            else:
                self.assertTrue(stage.relevant_forum(title), title)

    def test_article_body_needs_two_distinct_terms(self):
        # 标题无教育词时，正文需 ≥2 个不同教育词才算相关。
        self.assertTrue(stage.relevant_article("一张图看懂", "招生对象为小学六年级学生"))
        self.assertFalse(stage.relevant_article("一张图看懂", "提到一次招生"))


if __name__ == "__main__":
    unittest.main()
