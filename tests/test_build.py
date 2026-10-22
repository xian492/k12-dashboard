import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dashboard_build", ROOT / "tools" / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class SchoolFeedTests(unittest.TestCase):
    def test_assigns_list_item_to_school_by_title_alias(self):
        items = [{"title": "怀柔五中入选人工智能标杆学校", "link": "https://example/a"}]
        aliases = {"北京市怀柔区第五中学": ["怀柔五中"]}

        result = build.assign_school_feed_items(items, aliases, detail_loader=lambda _: "")

        self.assertEqual(result["北京市怀柔区第五中学"], items)

    def test_assigns_item_when_school_only_appears_in_detail(self):
        items = [{"title": "全区高中新生军训圆满完成", "link": "https://example/b"}]
        aliases = {
            "北京市怀柔区第一中学": ["怀柔一中"],
            "北京市怀柔区第二中学": ["怀柔二中"],
        }

        result = build.assign_school_feed_items(
            items,
            aliases,
            detail_loader=lambda _: "怀柔一中、怀柔二中等学校参加本次活动。",
        )

        self.assertEqual(result["北京市怀柔区第一中学"], items)
        self.assertEqual(result["北京市怀柔区第二中学"], items)

    def test_does_not_add_unmatched_items(self):
        items = [{"title": "教师资格认定公告", "link": "https://example/c"}]
        aliases = {"北京市第九中学": ["北京九中", "九中教育集团"]}

        result = build.assign_school_feed_items(items, aliases, detail_loader=lambda _: "无学校信息")

        self.assertEqual(result["北京市第九中学"], [])

    def test_official_fallback_sources_cover_missing_and_unreliable_districts(self):
        expected = {
            "东城区", "西城区", "石景山区", "门头沟区", "房山区", "通州区",
            "大兴区", "平谷区", "怀柔区", "密云区", "延庆区", "燕山地区",
            "经济技术开发区",
        }

        covered = set(build.SCHOOL_GOV_FEEDS) | set(build.SCHOOL_OFFICIAL_SEEDS)
        self.assertTrue(expected.issubset(covered))

    def test_merges_official_items_and_removes_pending_placeholder(self):
        schools = {
            "北京市怀柔区第五中学": {
                "学校信息": [{"title": "学校信息入口（动态栏目待接入）", "link": "https://example"}]
            }
        }
        item = {"title": "怀柔五中入选标杆学校", "link": "https://example/news"}

        build.merge_school_feed_items(schools, {"北京市怀柔区第五中学": [item]})

        self.assertNotIn("学校信息", schools["北京市怀柔区第五中学"])
        self.assertEqual(schools["北京市怀柔区第五中学"]["区级官方动态"], [item])

    def test_unreachable_school_pages_are_not_polled_directly(self):
        bad_hosts = {"bj15.cn", "bndssjs.cn", "bjs.net.cn", "rdfztzxq.cn", "bjeaedu.com", "pgzx.net"}
        configured_urls = {
            cfg["url"]
            for entries in build.SCHOOL_SPECS.values()
            for _, sections in entries
            for _, cfg in sections
        }

        self.assertFalse(any(any(host in url for host in bad_hosts) for url in configured_urls))

    def test_official_feed_pattern_accepts_nested_title_markup(self):
        markup = '<a href="./news.html"><span>房山中学开展校园活动</span></a>'

        match = re.search(build._PLAIN_LINK, markup)

        self.assertIsNotNone(match)
        self.assertIn("房山中学", match.group("title"))

    def test_seed_items_fill_empty_school_without_overwriting_live_items(self):
        live = {"title": "实时动态", "link": "https://example/live"}
        seed = {"title": "官方学校信息", "link": "https://example/seed"}
        schools = {
            "学校甲": {"学校信息": [{"title": "待接入", "link": "https://example"}]},
            "学校乙": {"校园动态": [live]},
        }

        build.merge_school_seed_items(schools, {"学校甲": [seed], "学校乙": [seed]})

        self.assertEqual(schools["学校甲"]["官方学校信息"], [seed])
        self.assertNotIn("学校信息", schools["学校甲"])
        self.assertEqual(schools["学校乙"], {"校园动态": [live]})

    def test_official_seeds_cover_districts_without_reliable_live_results(self):
        expected = {
            "东城区", "西城区", "石景山区", "门头沟区", "房山区", "通州区",
            "大兴区", "平谷区", "怀柔区", "密云区", "延庆区", "经济技术开发区",
        }

        self.assertTrue(expected.issubset(build.SCHOOL_OFFICIAL_SEEDS))

    def test_every_catalog_school_has_a_real_source_path(self):
        for district, catalog in build.SCHOOL_CATALOG.items():
            direct = {school for school, _ in build.SCHOOL_SPECS.get(district, [])}
            aggregate = set(build.SCHOOL_GOV_FEEDS.get(district, {}).get("aliases", {}))
            seeds = set(build.SCHOOL_OFFICIAL_SEEDS.get(district, {}))

            self.assertTrue(set(catalog).issubset(direct | aggregate | seeds), district)


class DashboardLayoutTests(unittest.TestCase):
    def make_data(self):
        districts = {
            name: {"政策": [], "动态": None, "学校": {}}
            for name in build.DISTRICTS
        }
        first_district = next(iter(build.DISTRICTS))
        districts[first_district] = {
            "政策": [{"title": "区级政策示例", "link": "https://example/policy"}],
            "动态": (
                "区教委",
                [{"title": "区级动态示例", "link": "https://example/district"}],
            ),
            "学校": {
                "示例中学": {
                    "校园动态": [
                        {"title": "学校动态示例", "link": "https://example/school"}
                    ]
                }
            },
        }
        return {"市教委": [], "教育部": [], "区级": districts}

    def test_district_and_school_information_are_rendered_in_separate_columns(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        official_start = html.index('<section class="district-column district-column--official">')
        school_start = html.index('<section class="district-column district-column--schools">')
        official_column = html[official_start:school_start]
        school_column = html[school_start:html.index("</details>", school_start)]

        self.assertIn('<h3 class="column-title">区级信息</h3>', official_column)
        self.assertIn("区级政策示例", official_column)
        self.assertIn("区级动态示例", official_column)
        self.assertNotIn("学校动态示例", official_column)
        self.assertIn('<h3 class="column-title">学校动态</h3>', school_column)
        self.assertIn("学校动态示例", school_column)

    def test_district_columns_stack_at_the_mobile_breakpoint(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertIn(".district-columns { display: grid;", html)
        self.assertIn("grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);", html)
        self.assertIn("@media (max-width: 760px)", html)
        self.assertIn(".district-columns { grid-template-columns: 1fr;", html)


if __name__ == "__main__":
    unittest.main()
