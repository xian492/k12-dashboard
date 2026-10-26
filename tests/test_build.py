import importlib.util
import asyncio
import json
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
    def test_collects_crawl4ai_updates_by_district_and_health(self):
        original_batch = getattr(build, "_crawl4ai_batch", None)

        async def fake_batch(specs):
            return [
                {
                    "school": "测试学校",
                    "district": "海淀区",
                    "status": "success",
                    "updates": [{"title": "校园新闻", "url": "https://school.example/news/1.html"}],
                    "candidate_sections": [{"title": "校园新闻", "url": "https://school.example/news/"}],
                    "items_found": 1,
                    "error": "",
                    "checked_at": "2026-10-22T00:00:00+00:00",
                }
            ]

        build._crawl4ai_batch = fake_batch
        try:
            updates, health = build.collect_crawl4ai_school_updates()
        finally:
            if original_batch is None:
                del build._crawl4ai_batch
            else:
                build._crawl4ai_batch = original_batch

        self.assertEqual(updates["海淀区"]["测试学校"][0]["title"], "校园新闻")
        self.assertEqual(health[0]["status"], "success")

    def test_merges_crawl4ai_updates_into_school_sections(self):
        schools = {
            "测试学校": {"学校信息": [{"title": "入口", "link": "https://school.example/"}]}
        }
        updates = {
            "测试学校": [
                {
                    "title": "校园新闻",
                    "url": "https://school.example/news/1.html",
                    "published_at": "2026-10-22",
                    "category": "校园新闻",
                }
            ]
        }

        build.merge_crawl4ai_school_updates(schools, updates)

        self.assertNotIn("学校信息", schools["测试学校"])
        self.assertEqual(schools["测试学校"]["校园新闻"][0]["link"], "https://school.example/news/1.html")

    def test_failed_crawl_does_not_create_school_placeholder(self):
        schools = {"失败学校": {}}

        build.merge_crawl4ai_school_updates(schools, {"失败学校": []})

        self.assertEqual(schools, {"失败学校": {}})

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
    def test_actions_installs_crawl4ai_and_runs_on_python_312(self):
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements-crawl4ai.txt").read_text(encoding="utf-8")

        self.assertIn("python-version: \"3.12\"", workflow)
        self.assertIn("crawl4ai-setup", workflow)
        self.assertIn("actions/cache@v4", workflow)
        self.assertIn("crawl4ai==0.9.5", requirements)
        self.assertIn("actions/upload-pages-artifact@v3", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)

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

    def test_sidebar_directory_links_to_city_and_every_district(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertIn('<nav class="page-directory" aria-label="页面目录">', html)
        self.assertIn('<a href="#city">市级</a>', html)
        self.assertIn('<h2 id="city">市级</h2>', html)
        for index, district in enumerate(build.DISTRICTS, start=1):
            anchor = f"district-{index:02d}"
            self.assertIn(f'<a href="#{anchor}">{district}</a>', html)
            self.assertIn(f'<details id="{anchor}" class="row"', html)

    def test_sidebar_directory_becomes_horizontal_navigation_on_mobile(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertIn(".page-directory { position: fixed;", html)
        self.assertIn(".page-directory { position: sticky;", html)
        self.assertIn("overflow-x: auto;", html)

    def test_sidebar_directory_is_centered_and_enlarges_the_active_link(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertIn("top: 50%;", html)
        self.assertIn("transform: translateY(-50%);", html)
        self.assertIn('.page-directory a[aria-current="location"] {', html)
        self.assertIn("font-size: 13px;", html)
        self.assertIn("transform: translateX(4px);", html)
        self.assertIn("transition: color .18s ease", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
        self.assertIn("transform: none;", html)

    def test_admission_season_timeline_is_not_rendered(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertNotIn('<div class="season">', html)
        self.assertNotIn("招生季空窗期", html)
        self.assertNotIn('<div class="today"', html)

    def test_dashboard_title_covers_all_k12_stages(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertIn("<title>K12 信源看板</title>", html)
        self.assertIn("<h1>K12 信源看板</h1>", html)
        self.assertNotIn("北京小升初 · 官方信源台账", html)


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
        # 官网已关停的学校降级为纯名称+公众号入口（2026-10-26 复核）。
        self.assertEqual(
            directory["东城区"]["北京市第二中学分校"]["homepage"],
            "",
        )
        self.assertEqual(
            directory["东城区"]["北京市第一七一中学"]["homepage"],
            "",
        )
        # 海淀死链学校迁入 bjhdedu.cn 统一建站平台。
        self.assertEqual(
            directory["海淀区"]["北京市育英学校"]["homepage"],
            "https://bjsyyxx.bjhdedu.cn/",
        )
        self.assertEqual(
            directory["海淀区"]["北京市中关村中学"]["homepage"],
            "https://zgczx.bjhdedu.cn/",
        )
        self.assertEqual(
            directory["丰台区"]["北京市第十中学"]["homepage"],
            "https://bj10z.ftedu.cn/",
        )
        # 交大附中原域名被接管，链接必须移除。
        self.assertEqual(directory["海淀区"]["交大附中"]["homepage"], "")
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
        configured = {
            **getattr(build, "SCHOOL_NAVIGATION_FALLBACKS", {}),
            **getattr(build, "SCHOOL_HOMEPAGES", {}),
        }
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

    def test_district_directory_is_not_presented_as_a_school_homepage(self):
        self.assertNotIn("北京市第二中学", build.SCHOOL_HOMEPAGES)
        self.assertEqual(
            build.SCHOOL_NAVIGATION_FALLBACKS["北京市第二中学"],
            build._DONGCHENG_SCHOOLS,
        )
        self.assertEqual(build.school_homepage_link("北京市第二中学"), "北京市第二中学")

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

    def test_replaced_school_domains_use_current_reachable_homepages(self):
        self.assertEqual(build.SCHOOL_HOMEPAGES["北京市通州区潞河中学"], "https://www.luhe.cn/")
        self.assertEqual(build.SCHOOL_HOMEPAGES["北京市顺义牛栏山第一中学"], "http://www.nlsyz.com.cn/")

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

    def test_multi_section_school_renders_entry_link_once(self):
        districts = {
            name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
            for name in build.DISTRICTS
        }
        # 人大附中两个栏目 + 亦庄实验中学跨两个区（大兴区目录与经开区属地）。
        districts["海淀区"]["学校"] = {
            "人大附中": {
                "通知公告": [{"title": "通知一", "link": "https://www.rdfz.cn/a", "tag": "通知公告", "date": "2026-10-22"}],
                "招生资讯": [{"title": "招生一", "link": "https://www.rdfz.cn/b", "tag": "招生资讯", "date": "2026-10-22"}],
            },
        }
        districts["大兴区"]["学校"] = {"北京亦庄实验中学": {"官方学校信息": [{"title": "大兴条目", "link": "https://dx.gov.cn/x", "tag": "信息", "date": "2026-10-22"}]}}
        districts["经济技术开发区"]["学校"] = {"北京亦庄实验中学": {"官方学校信息": [{"title": "经开区条目", "link": "https://kfq.gov.cn/y", "tag": "信息", "date": "2026-10-22"}]}}
        data = {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": districts,
        }

        html = build.build_page(data, set(), "2026-10-22 12:00")

        import re as _re

        rdfz_links = _re.findall(r'class="school-homepage"[^>]*>人大附中<', html)
        yizhuang_links = _re.findall(r'class="school-homepage"[^>]*>北京亦庄实验中学<', html)
        self.assertEqual(len(rdfz_links), 1)
        self.assertEqual(len(yizhuang_links), 1)
        # 校名块（含公众号）只出现一次；栏目以纯栏名子标题挂在校名块下。
        self.assertEqual(html.count(">人大附中<"), 1)
        self.assertEqual(html.count("rdfz1950"), 1)
        self.assertIn("招生资讯 · 1 条", html)
        self.assertIn("通知公告 · 1 条", html)
        # 两个区条目本身都还在。
        self.assertIn("经开区条目", html)

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

    def test_footer_distinguishes_school_crawling_from_wechat_navigation(self):
        data = {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": {
                name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
                for name in build.DISTRICTS
            },
        }
        html = build.build_page(data, set(), "2026-10-22 12:00")

        self.assertIn("仅已确认的学校官网提供点击与动态抓取", html)
        self.assertIn("微信公众号 ID 仅作人工检索入口", html)


class OfficialHomepageTests(unittest.TestCase):
    def make_data(self):
        return {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": {
                name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
                for name in build.DISTRICTS
            },
        }

    def test_city_and_every_district_have_official_homepages(self):
        self.assertEqual(
            set(build.CITY_HOMEPAGES),
            {"北京市教委 · 通知公告", "教育部 · 公告公示", "全市学校信息"},
        )
        self.assertEqual(set(build.DISTRICT_HOMEPAGES), set(build.DISTRICTS))
        self.assertTrue(
            all(url.startswith("https://") for url in build.CITY_HOMEPAGES.values())
        )
        # 朝阳/延庆门户 https 通道失效（握手失败/超时），http 可达（2026-10-26 复核）。
        http_only = {"朝阳区", "延庆区"}
        for district, url in build.DISTRICT_HOMEPAGES.items():
            if district in http_only:
                self.assertTrue(url.startswith("http://"))
            else:
                self.assertTrue(url.startswith("https://"))

    def test_city_labels_and_district_names_link_to_official_sites(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")

        self.assertIn(
            '<h3><a class="official-homepage" href="https://jw.beijing.gov.cn/" '
            'target="_blank" rel="noopener">北京市教委 · 通知公告</a></h3>',
            html,
        )
        self.assertIn(
            '<span class="d-name"><a class="official-homepage" '
            'href="https://www.bjhdedu.cn/" target="_blank" '
            'rel="noopener">海淀区</a></span>',
            html,
        )


class RssFeedTests(unittest.TestCase):
    def make_data(self):
        return {
            "市教委": [],
            "教育部": [],
            "市级学校信息": [],
            "区级": {
                name: {"政策": [], "动态": None, "通用信息": [], "学校": {}}
                for name in build.DISTRICTS
            },
        }

    def test_page_contains_official_and_community_view_switcher(self):
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "record_count": 1,
            "records": [{
                "title": "社区入学线索",
                "link": "https://community.example/post/1",
                "source": "示例社区",
                "published_at": "2026-10-22",
                "content_type": "政策与流程",
                "stage": ["小升初"],
                "event_type": ["报名"],
                "district_candidates": ["海淀区"],
                "school_candidates": [],
                "verification_status": "待官方核验",
                "community_notice": True,
            }],
        }
        html = build.build_page(
            self.make_data(), set(), "2026-10-22 12:00", community_data=community
        )
        self.assertIn("官方信源（北京）", html)
        self.assertIn("社区信源（多城市）", html)
        self.assertIn("社区内容仅用于发现线索", html)
        self.assertIn("社区入学线索", html)
        self.assertIn("community.example/post/1", html)

    def test_community_view_groups_by_stage_then_content_type(self):
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "records": [
                {
                    "title": "家长经验帖子",
                    "link": "https://community.example/experience",
                    "source": "社区甲",
                    "published_at": "2026-10-22",
                    "content_type": "家长经验",
                    "stage": ["小升初"],
                    "event_type": ["分班"],
                    "district_candidates": ["海淀区"],
                },
                {
                    "title": "报名政策帖子",
                    "link": "https://community.example/policy",
                    "source": "社区乙",
                    "published_at": "2026-10-21",
                    "content_type": "政策与流程",
                    "stage": ["幼升小"],
                    "event_type": ["报名", "入学"],
                    "district_candidates": ["朝阳区"],
                },
            ],
        }

        html = build.community_view(community)

        self.assertLess(html.index("幼升小"), html.index("小升初"))
        self.assertIn('class="community-stage"', html)
        self.assertIn('class="community-type"', html)
        self.assertIn('<span class="chip">分班</span>', html)
        self.assertIn('<span class="chip">报名</span><span class="chip">入学</span>', html)
        self.assertIn('<span class="community-geo">海淀区</span>', html)
        self.assertIn('<span class="community-geo">朝阳区</span>', html)
        self.assertIn("来源：社区甲", html)
        self.assertIn("来源：社区乙", html)
        self.assertIn('class="chip chip--verify">待官方核验', html)

    def test_community_view_groups_by_school_phase_with_stage_labels(self):
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "records": [
                {
                    "title": "小升初政策",
                    "link": "https://community.example/primary",
                    "source": "社区甲",
                    "content_type": "政策与流程",
                    "stage": ["小升初"],
                    "event_type": ["报名"],
                },
                {
                    "title": "中考经验",
                    "link": "https://community.example/middle",
                    "source": "社区乙",
                    "content_type": "家长经验",
                    "stage": ["中考"],
                    "event_type": ["考试"],
                },
                {
                    "title": "高考动态",
                    "link": "https://community.example/high",
                    "source": "社区丙",
                    "content_type": "学校动态",
                    "stage": ["高考"],
                    "event_type": ["招生"],
                },
            ],
        }

        html = build.community_view(community)

        # 过渡期各自成组：小升初、初升高（中考）、高考，按升学时间线排序。
        self.assertLess(html.index("小升初"), html.index("初升高"))
        self.assertLess(html.index("初升高"), html.index("高考"))
        self.assertIn("小升初 · 1 条", html)
        self.assertIn("初升高 · 1 条", html)
        self.assertIn("高考 · 1 条", html)
        self.assertIn('<span class="chip chip--stage">小升初</span>', html)
        self.assertIn('<span class="chip chip--stage">中考</span>', html)
        self.assertIn('<span class="chip chip--stage">高考</span>', html)

    def test_community_view_renders_multi_stage_record_once(self):
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "records": [
                {
                    "title": "海淀小升初跨区怎么选",
                    "link": "https://community.example/multi-stage",
                    "source": "社区甲",
                    "published_at": "2026-10-13",
                    "content_type": "政策与流程",
                    "stage": ["幼升小", "小升初", "中考"],
                    "event_type": ["报名"],
                    "district_candidates": ["海淀区"],
                },
            ],
        }

        html = build.community_view(community)

        self.assertEqual(html.count("community.example/multi-stage"), 1)
        self.assertIn("幼升小 · 1 条", html)
        self.assertIn(
            '<span class="chip chip--stage">幼升小</span>'
            '<span class="chip chip--stage">小升初</span>'
            '<span class="chip chip--stage">中考</span>',
            html,
        )
        self.assertNotIn("小学 · ", html)
        self.assertNotIn("中学 · ", html)

    def test_community_view_places_preschool_transition_in_own_phase(self):
        """幼升小单独成组；幼儿园档只收真正的幼儿园内容（入园/托班）。"""
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "records": [
                {
                    "title": "2026年芍药居幼儿园小班、托班几个班汇总",
                    "link": "https://community.example/kindergarten",
                    "source": "社区甲",
                    "content_type": "政策与流程",
                    "stage": ["幼儿园"],
                },
                {
                    "title": "2027北京小升初入学指南",
                    "link": "https://community.example/primary-entry",
                    "source": "社区甲",
                    "content_type": "政策与流程",
                    # 社区宽标签：小升初帖同时带出幼升小标签，首标签定档。
                    "stage": ["幼升小", "小升初", "中考"],
                },
            ],
        }

        html = build.community_view(community)

        self.assertIn("幼儿园 · 1 条", html)
        self.assertIn("幼升小 · 1 条", html)

    def test_community_view_maps_forum_board_tags_to_school_phases(self):
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "records": [
                {
                    "title": "2026年芍药居幼儿园小班、托班几个班汇总",
                    "link": "https://community.example/kindergarten",
                    "source": "社区甲",
                    "content_type": "政策与流程",
                    "stage": ["幼儿园"],
                },
                {
                    "title": "2026年，芍药居1年级新生，提前到校时间",
                    "link": "https://community.example/primary",
                    "source": "社区甲",
                    "content_type": "政策与流程",
                    "stage": ["小学"],
                },
                {
                    "title": "2025年人朝初中（初一新生）领取通知书时间地点",
                    "link": "https://community.example/middle",
                    "source": "社区甲",
                    "content_type": "家长经验",
                    "stage": ["初中"],
                },
                {
                    "title": "北大附中朝阳未来学校面向全市招收高一年级新生",
                    "link": "https://community.example/high",
                    "source": "社区甲",
                    "content_type": "学校动态",
                    "stage": ["高中"],
                },
            ],
        }

        html = build.community_view(community)

        self.assertIn("幼儿园 · 1 条", html)
        self.assertIn("小学 · 1 条", html)
        self.assertIn("中学 · 1 条", html)
        self.assertIn("高中 · 1 条", html)
        self.assertIn('<span class="chip chip--stage">幼儿园</span>', html)
        self.assertIn('<span class="chip chip--stage">初中</span>', html)

    def test_community_view_caps_long_tag_lists_with_overflow_hints(self):
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "records": [
                {
                    "title": "全区通用报名流程汇总",
                    "link": "https://community.example/capped",
                    "source": "社区甲",
                    "published_at": "2026-10-22",
                    "content_type": "政策与流程",
                    "stage": ["小升初"],
                    "event_type": ["报名", "入学", "派位", "摇号", "划片", "学区", "招生"],
                    "district_candidates": [
                        "海淀区", "西城区", "东城区", "朝阳区", "丰台区", "通州区",
                    ],
                },
            ],
        }

        html = build.community_view(community)

        self.assertIn('<span class="chip" title="报名、入学、派位、摇号、划片、学区、招生">等 7 项</span>', html)
        self.assertIn("等 6 区", html)
        # 超出截断的部分不整串渲染，完整清单保留在 title 提示里。
        self.assertNotIn("区县：海淀区、西城区、东城区、朝阳区、丰台区、通州区", html)
        self.assertIn('title="海淀区、西城区、东城区、朝阳区、丰台区、通州区"', html)
        self.assertIn("海淀区、西城区、东城区 等 6 区", html)

    def test_community_view_groups_records_by_city_then_phase(self):
        community = {
            "status": "success",
            "generated_at": "2026-10-22T12:00:00+08:00",
            "records": [
                {
                    "title": "上海中考经验",
                    "link": "https://community.example/shanghai",
                    "source": "篱笆网",
                    "region": "上海",
                    "content_type": "家长经验",
                    "stage": ["中考"],
                },
                {
                    "title": "北京小升初政策",
                    "link": "https://community.example/beijing-primary",
                    "source": "北京小升初网",
                    "region": "北京",
                    "content_type": "政策与流程",
                    "stage": ["小升初"],
                },
                {
                    "title": "北京高考动态",
                    "link": "https://community.example/beijing-high",
                    "source": "社区丙",
                    "region": "北京",
                    "content_type": "学校动态",
                    "stage": ["高考"],
                },
            ],
        }

        html = build.community_view(community)

        self.assertIn('<nav class="page-directory" aria-label="社区页面目录">', html)
        self.assertIn('<a href="#community-overview">概览</a>', html)
        self.assertIn('<h2 id="community-overview">社区信源</h2>', html)
        # 目录按城市导航，城市按条数降序（北京 2 条在上海 1 条之前）。
        self.assertLess(html.index('href="#community-city-beijing"'), html.index('href="#community-city-shanghai"'))
        self.assertIn('<a href="#community-city-beijing">北京</a>', html)
        self.assertIn('<a href="#community-city-shanghai">上海</a>', html)
        self.assertIn('<section id="community-city-beijing" class="community-city">', html)
        self.assertIn('<h3>北京 · 2 条</h3>', html)
        self.assertIn('<h3>上海 · 1 条</h3>', html)
        # 学段落在城市分区内，锚点带城市前缀避免重复 id。
        self.assertIn(
            '<section id="community-city-beijing-community-phase-primary-transition" class="community-stage">',
            html,
        )
        self.assertIn(
            '<section id="community-city-shanghai-community-phase-middle-transition" class="community-stage">',
            html,
        )
        self.assertIn("覆盖城市：北京、上海", html)

    def test_page_tolerates_missing_community_snapshot(self):
        html = build.build_page(self.make_data(), set(), "2026-10-22 12:00")
        self.assertIn("社区数据暂不可用", html)

    def test_render_only_rebuilds_page_and_feed_from_existing_snapshot(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            snapshot = {"built_at": "2026-10-22 12:00", "data": self.make_data()}
            (docs / "data.json").write_text(
                json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
            )
            with mock.patch.object(build, "DOCS", docs):
                build.render_only()

            html = (docs / "index.html").read_text(encoding="utf-8")
            self.assertIn("<h1>K12 信源看板</h1>", html)
            rss = ET.fromstring((docs / "feed.xml").read_text(encoding="utf-8"))
            self.assertEqual(rss.find("channel/title").text, "K12 信源看板 · 区教委与学校动态")

    def test_render_only_fails_loudly_without_a_snapshot(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(build, "DOCS", Path(tmp)):
                with self.assertRaises(SystemExit):
                    build.render_only()

    def test_official_feed_never_contains_community_records(self):
        data = self.make_data()
        data["community"] = {
            "records": [{"title": "不应进入 RSS", "link": "https://community.example/post"}]
        }
        feed = build.build_feed(data, "2026-10-22 12:00")
        self.assertNotIn("不应进入 RSS", feed)
        self.assertNotIn("community.example", feed)

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
