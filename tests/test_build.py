import importlib.util
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
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

    def test_catalog_keeps_at_least_three_schools_per_district(self):
        for district in build.DISTRICTS:
            self.assertGreaterEqual(len(build.SCHOOL_CATALOG[district]), 3, district)

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

    def test_parser_discards_non_education_administrative_links(self):
        markup = """
        <a href="news.html">学校举办科技节活动</a>
        <a href="javascript:;">版权所有 北京市示例中学</a>
        <a href="https://beian.miit.gov.cn/">京ICP备12345678号</a>
        <a href="admission.html">义务教育入学</a>
        <a href="budget.html">北京市示例中学2025年度部门决算</a>
        <a href="purchase.html">学校大宗食材采购项目招标公告</a>
        <a href="bid.html">学校空调采购项目比选公告</a>
        """
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "index.html"
            page.write_text(markup, encoding="utf-8")
            items = build.parse_spec({
                "url": page.as_uri(),
                "pattern": r'<a href="(?P<link>[^"]+)">(?P<title>[^<]+)</a>',
                "base": "https://school.example/",
            })

        self.assertEqual([item["title"] for item in items], ["学校举办科技节活动"])

    def test_seed_items_fill_empty_school_without_overwriting_live_items(self):
        live = {"title": "实时动态", "link": "https://example/live"}
        seed = {"title": "学校甲举办科技节活动", "link": "https://example/seed"}
        schools = {
            "学校甲": {"学校信息": [{"title": "待接入", "link": "https://example"}]},
            "学校乙": {"校园动态": [live]},
        }

        build.merge_school_seed_items(schools, {"学校甲": [seed], "学校乙": [seed]})

        self.assertEqual(schools["学校甲"]["官方学校信息"], [seed])
        self.assertNotIn("学校信息", schools["学校甲"])
        self.assertEqual(schools["学校乙"], {"校园动态": [live]})

    def test_generic_official_seed_does_not_create_a_school_update(self):
        schools = {"学校甲": {}, "学校乙": {}}
        generic = {
            "学校甲": [build._official_seed(
                "北京市2026年具有招生资格的学校名单",
                "https://www.beijing.gov.cn/school-list.html",
            )],
            "学校乙": [build._official_seed(
                "官方学校信息",
                "https://example.gov.cn/general-school-info.html",
            )],
        }

        build.merge_school_seed_items(schools, generic)

        self.assertEqual(schools["学校甲"], {})
        self.assertEqual(schools["学校乙"], {})


class DashboardLayoutTests(unittest.TestCase):
    def make_data(self):
        districts = {
            name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
            for name in build.DISTRICTS
        }
        first_district = next(iter(build.DISTRICTS))
        districts[first_district] = {
            "政策": [{"title": "区级政策示例", "link": "https://example/policy"}],
            "动态": (
                "区教委",
                [{"title": "区级动态示例", "link": "https://example/district"}],
            ),
            "通用信息": [
                {"title": "本区学校名录", "link": "https://example/district-schools"}
            ],
            "学校": {
                "示例中学": {
                    "校园动态": [
                        {"title": "学校动态示例", "link": "https://example/school"}
                    ]
                },
                "待更新中学": {},
            },
        }
        return {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [
                {"title": "北京市具有招生资格的学校名单", "link": "https://example/city-schools"}
            ],
            "区级": districts,
        }

    def test_district_and_school_information_are_rendered_in_separate_columns(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        official_start = html.index('<section class="district-column district-column--official">')
        school_start = html.index('<section class="district-column district-column--schools">')
        official_column = html[official_start:school_start]
        school_column = html[school_start:html.index("</details>", school_start)]

        self.assertIn('<h3 class="column-title">区级信息</h3>', official_column)
        self.assertIn("区级政策示例", official_column)
        self.assertIn("区级动态示例", official_column)
        self.assertIn("本区学校名录", official_column)
        self.assertNotIn("学校动态示例", official_column)
        self.assertIn('<h3 class="column-title">学校入口与动态</h3>', school_column)
        self.assertIn("学校动态示例", school_column)
        self.assertIn("待更新中学", school_column)
        self.assertNotIn("待更新中学 · 暂无有效动态", school_column)

    def test_citywide_school_information_is_rendered_at_city_level(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        city_section = html[:html.index("<h2>分区台账</h2>")]
        district_section = html[html.index("<h2>分区台账</h2>"):]

        self.assertIn("全市学校信息", city_section)
        self.assertIn("北京市具有招生资格的学校名单", city_section)
        self.assertNotIn("北京市具有招生资格的学校名单", district_section)

    def test_district_columns_stack_at_the_mobile_breakpoint(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertIn(".district-columns { display: grid;", html)
        self.assertIn("grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);", html)
        self.assertIn("@media (max-width: 760px)", html)
        self.assertIn(".district-columns { grid-template-columns: 1fr;", html)


class SchoolHomepageTests(unittest.TestCase):
    def test_taixing_directory_contains_every_school_website(self):
        directory = getattr(build, "TAIXING_SCHOOL_DIRECTORY", {})

        self.assertEqual(
            {district: len(schools) for district, schools in directory.items()},
            {
                "海淀区": 39,
                "朝阳区": 17,
                "西城区": 19,
                "东城区": 16,
                "丰台区": 7,
                "昌平区": 4,
                "大兴区": 3,
                "顺义区": 1,
                "通州区": 4,
                "石景山区": 4,
            },
        )
        self.assertEqual(
            sum(len(schools) for schools in directory.values()),
            114,
        )
        self.assertEqual(
            directory["东城区"]["北京市第二中学分校"]["homepage"],
            "http://www.2zfx.com/",
        )
        self.assertEqual(
            directory["东城区"]["北京市第一七一中学"]["homepage"],
            "http://www.171sch.com/",
        )
        self.assertNotIn(
            "xschu.com/qhy/wordBox/",
            " ".join(
                school["homepage"]
                for schools in directory.values()
                for school in schools.values()
            ),
        )

    def test_taixing_schools_are_added_to_the_dashboard_catalog(self):
        directory = getattr(build, "TAIXING_SCHOOL_DIRECTORY", {})

        missing = [
            f"{district} / {school}"
            for district, schools in directory.items()
            for school in schools
            if school not in build.SCHOOL_CATALOG.get(district, [])
        ]

        self.assertEqual(missing, [])

    def test_every_catalog_school_has_an_official_entry(self):
        configured = getattr(build, "SCHOOL_HOMEPAGES", {})
        expected = {
            district: set(schools)
            for district, schools in build.SCHOOL_CATALOG.items()
        }
        for district, school_specs in build.SCHOOL_SPECS.items():
            expected.setdefault(district, set()).update(
                school for school, _ in school_specs
            )
        missing = [
            f"{district} / {school}"
            for district, schools in expected.items()
            for school in schools
            if school not in configured
        ]

        self.assertEqual(missing, [])

    def test_school_name_links_to_its_official_homepage(self):
        districts = {
            name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
            for name in build.DISTRICTS
        }
        districts["海淀区"]["学校"] = {"人大附中": {}}
        data = {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": districts,
        }

        html = build.build_page(data, set(), "2026-10-22 12:00")

        self.assertIn(
            '<a class="school-homepage" href="http://www.rdfz.cn/" '
            'target="_blank" rel="noopener" title="打开学校官方入口">人大附中</a>',
            html,
        )

    def test_school_wechat_ids_render_below_the_school_name(self):
        districts = {
            name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
            for name in build.DISTRICTS
        }
        districts["海淀区"]["学校"] = {"人大附中": {}}
        data = {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": districts,
        }

        html = build.build_page(data, set(), "2026-10-22 12:00")

        self.assertIn("微信公众号", html)
        self.assertIn("rdfz1950", html)
        self.assertNotIn("人大附中 · 暂无有效动态", html)

    def test_district_wechat_ids_render_in_the_official_column(self):
        districts = {
            name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
            for name in build.DISTRICTS
        }
        data = {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": districts,
        }

        html = build.build_page(data, set(), "2026-10-22 12:00")

        self.assertIn("海淀教育", html)
        self.assertIn("jybxwb", html)
        self.assertIn("北京朝阳教育", html)
        self.assertIn("educhaoyang", html)

    def test_navigation_metadata_does_not_enter_the_rss(self):
        data = {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": {
                "海淀区": {
                    "政策": [],
                    "动态": None,
                    "通用信息": [],
                    "学校": {"人大附中": {}},
                }
            },
        }

        feed = build.build_feed(data, "2026-10-22 12:00")

        self.assertNotIn("rdfz.cn", feed)
        self.assertNotIn("rdfz1950", feed)


class RssFeedTests(unittest.TestCase):
    def test_feed_contains_new_dashboard_sources_without_existing_policy_feeds(self):
        shared = {"title": "区校联合活动", "link": "https://example/shared"}
        data = {
            "市教委": [{"title": "已有市教委订阅", "link": "https://example/jw"}],
            "教育部": [{"title": "已有教育部订阅", "link": "https://example/moe"}],
            "市级学校信息": [
                {"title": "全市招生资格名单", "link": "https://example/city-schools"}
            ],
            "区级": {
                "示例区": {
                    "政策": [{"title": "已有区级政策订阅", "link": "https://example/policy"}],
                    "动态": ("示例区教委", [shared]),
                    "通用信息": [
                        {"title": "示例区学校名录", "link": "https://example/district-schools"}
                    ],
                    "学校": {
                        "示例中学": {
                            "校园动态": [
                                shared,
                                {"title": "示例中学校园开放日", "link": "https://example/school"},
                            ]
                        }
                    },
                }
            },
        }

        self.assertTrue(hasattr(build, "build_feed"), "build_feed must generate the dashboard RSS")
        root = ET.fromstring(build.build_feed(data, "2026-10-22 14:00"))
        titles = [item.findtext("title") for item in root.findall("./channel/item")]

        self.assertEqual(
            titles,
            ["全市招生资格名单", "区校联合活动", "示例区学校名录", "示例中学校园开放日"],
        )
        self.assertEqual(titles.count("区校联合活动"), 1)
        self.assertNotIn("已有市教委订阅", titles)
        self.assertNotIn("已有教育部订阅", titles)
        self.assertNotIn("已有区级政策订阅", titles)
        self.assertEqual(
            root.findtext("./channel/link"),
            "https://xian492.github.io/k12-dashboard/",
        )


if __name__ == "__main__":
    unittest.main()
