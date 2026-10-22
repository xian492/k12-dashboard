#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K12 官方信源看板构建脚本 v5。

v5 布局：按区分组。市级置顶；区卡片 = 区招生政策(yjrx) + 区教委动态 + 该区学校官网（按校名合并）。
信源：yjrx 18 区 + 市教委 + 教育部 + 学校官网/区教委官网（配置驱动，见 SCHOOL_SPECS / DISTRICT_GOV_SPECS）。

用法：python3 build.py（无第三方依赖）
"""
import json
import re
import ssl
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# 区名 -> (yjrx fid, [(学校名, 栏目配置...)])
DISTRICTS = {
    "东城区": "e84eb33d8d5062933ab3bf3e7a37acb5",
    "西城区": "de2599415bc9f2a48110859f4e973e96",
    "朝阳区": "e8cc3c21eb88fbde7781fb5f21e436e4",
    "海淀区": "74e3d283b5f295df7647561e2df7b583",
    "丰台区": "e7db49a3850de47674a9bf7f71c8c69d",
    "石景山区": "85d3d957639fe5e4a6facb8dad0d3430",
    "门头沟区": "190ce81f6e5d6ebeb7b0b39181c22f49",
    "房山区": "84b1313554b883c852e6486b5cde3ed8",
    "通州区": "14b10256a87dc2435b7941aa5bc26f60",
    "顺义区": "52a020fcec213bb8cfc12de6c599b126",
    "昌平区": "fe1ada1cac784a209e8718f521c97afb",
    "大兴区": "bdf89e0651429eda155421d6ce98f5d2",
    "平谷区": "f54e9a0d0b90724a1ec7b47b0ea8fe28",
    "怀柔区": "befcfdf69d43807b4919a79c25d11a52",
    "密云区": "2422496aa8597ab6585f95b01d529602",
    "延庆区": "68583790ba5e15b072902e3e57297242",
    "燕山地区": "e835141af2396c12c563620073f4c25b",
    "经济技术开发区": "779cf55da96380347589642668fc439a",
}

# 学校配置：区 -> [学校列表]，每个学校 = (校名, [源配置...])
# 源配置 = (栏名, spec)，spec 字典：
#   url      列表页地址
#   pattern  正则（re.S 可选），命名组：link / title / date（date 可选）
#   base     相对 href 的绝对前缀；None 表示 href 已是绝对地址
#   enc      页面编码（utf-8 / gbk ...），默认 utf-8
#   strip    从 href 中剔除的子串（如 "../"），可选
SCHOOL_SPECS = {
    "海淀区": [
        ("人大附中", [
            ("通知公告", dict(
                url="https://www.rdfz.cn/xwzx/tzgg.htm",
                pattern=r'<a href="(?P<link>(?:\.\./)+info/\d+/\d+\.htm)"[^>]*>\s*<time><span>\d+</span>/\s*(?P<date>[\d-]+)</time>\s*<div class="txt">\s*<h3 class="eclip">(?P<title>[^<]+)</h3>',
                base="https://www.rdfz.cn/", strip="../")),
            ("招生资讯", dict(
                url="https://www.rdfz.cn/zszp/zszx1/zsdt.htm",
                pattern=r'<a href="(?P<link>(?:\.\./)+info/\d+/\d+\.htm)"[^>]*>\s*<time><span>\d+</span>/\s*(?P<date>[\d-]+)</time>\s*<div class="txt">\s*<h3 class="eclip">(?P<title>[^<]+)</h3>',
                base="https://www.rdfz.cn/", strip="../")),
        ]),
        ("清华附中", [
            ("招生专栏", dict(
                url="https://www.qhfz.edu.cn/student_talent/",
                pattern=r'<a href="(?P<link>info/\d+/\d+\.htm)" title="(?P<title>[^"]{6,100})"',
                base="https://www.qhfz.edu.cn/student_talent/")),
        ]),
        ("首师大附中", [
            ("校园快讯", dict(
                url="https://www.cnuhs.cn/CampusNews/50.html",
                pattern=r'<a target="_blank" href="(?P<link>/CampusNews/\d+/\d+\.html)"[^>]*>(?P<title>[^<]{6,})</a>',
                base="https://www.cnuhs.cn")),
        ]),
        ("一零一中学", [
            ("通知公告", dict(
                url="https://www.beijing101.com/school/listArticle.do?schoolId=587bb213-aab9-415d-b129-b629de3718e8&navigationId=a2b7ac77-2b54-4e64-9d0c-fe50d248e48e",
                pattern=r'<a href="(?P<link>/school/getNavigationArticle\.do\?[^"]+)"[^>]*>(?P<title>[^<]{6,})</a><span>(?P<date>[\d-]+)',
                base="https://www.beijing101.com",
                exclude=r"食堂一周食谱")),
        ]),
        ("八一学校", [
            ("校园动态", dict(
                url="https://byxx.bjhdedu.cn/xyfc/xndt/",
                pattern=r'<span class="date">\[(?P<date>[\d-]+)\]</span>\s*<a href="(?P<link>\./\d{6}/t\d+_\d+\.shtml)"[^>]*>(?P<title>[^<]{6,})</a>',
                base="https://byxx.bjhdedu.cn/xyfc/xndt/")),
        ]),
        ("交大附中", [
            ("校园动态", dict(
                url="https://jdfz.bjhdedu.cn/xyfc/xndt/",
                pattern=r'<span class="date">\[(?P<date>[\d-]+)\]</span>\s*<a href="(?P<link>\./\d{6}/t\d+_\d+\.shtml)"[^>]*>(?P<title>[^<]{6,})</a>',
                base="https://jdfz.bjhdedu.cn/xyfc/xndt/")),
        ]),
        ("北京大学附属中学", [
            ("校内新闻", dict(
                url="https://www.pkuschool.edu.cn/news/news.html",
                pattern=r'<div class="li">.*?<div class="t">(?P<title>[^<]{6,})</div>.*?<div class="y">(?P<date>[\d-]+)</div>.*?<a href="(?P<link>[^"]+)"',
                base="https://www.pkuschool.edu.cn", re_s=True)),
        ]),
    ],
    "西城区": [
        ("北师大附中", [
            ("招生专栏", dict(
                url="https://www.bjsdfz.com/list-219-1.html",
                pattern=r'<a href="(?P<link>/show-219-\d+-1\.html)"[^>]*>.*?<em class="em3">\s*(?P<title>.*?)\s*</em>',
                base="https://www.bjsdfz.com", re_s=True)),
        ]),
    ],
}

SCHOOL_SPECS["朝阳区"] = [
    ("北京市第八十中学", [
        ("最新动态", dict(
            url="http://www.bj80.com/zxdt/",
            pattern=r'<a href="(?P<link>\./\d{6}/t\d+_\d+\.html)">\s*(?P<title>[^<]{6,})</a>\s*<p>(?P<date>[\d-]+)</p>',
            base="http://www.bj80.com/zxdt/", re_s=True)),
    ]),
    ("陈经纶中学", [
        ("校园新闻", dict(
            url="http://bjcjl.bjchyedu.cn/xyxw/",
            pattern=r'<a target="_blank" href="(?P<link>\./\d{6}/t\d+(?:_\d+)?\.html)">\s*<span class="detail_txt">(?P<title>[^<]{6,})</span>\s*<span class="detail_date">(?P<date>[\d-]+)</span>',
            base="http://bjcjl.bjchyedu.cn/xyxw/", re_s=True)),
    ]),
    ("朝阳外国语学校", [
        ("通知公告", dict(
            url="http://cyfls.bjchyedu.cn/tzgg/",
            pattern=r'<a href="(?P<link>\./\d{6}/t\d+(?:_\d+)?\.html)">(?P<title>[^<]{6,})</a>\s*<span>(?P<date>[\d-]+)</span>',
            base="http://cyfls.bjchyedu.cn/tzgg/", re_s=True)),
    ]),
    ("日坛中学", [
        ("校园新闻", dict(
            url="http://rtzx.bjchyedu.cn/xyxw/",
            pattern=r'<span class="con"><a href="(?P<link>\./\d{6}/t\d+(?:_\d+)?\.html)">(?P<title>[^<]{6,})</a></span>\s*<span class="date">(?P<date>[\d-]+)</span>',
            base="http://rtzx.bjchyedu.cn/xyxw/", re_s=True)),
    ]),
    ("工大附中", [
        ("招生招聘", dict(
            url="http://www.bjgdfz.com/?a=web.articles&uid=9182&id=7984",
            pattern=r'<span class="add">(?P<date>[\d-]+)</span><a title="[^"]*" href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]{6,})</a>',
            base="http://www.bjgdfz.com")),
    ]),
    ("北京中学", [
        ("校园动态", dict(
            url="https://www.beijingacademy.com.cn/",
            pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>\s*(?P<title>[^<]{8,})\s*</a>',
            base="https://www.beijingacademy.com.cn/",
            exclude=r"首页|学校简介|联系我们|友情链接")),
    ]),
]

# 已核验的公开学校官网（页面结构独立配置，解析失败时仍安全降级为空列表）。
SCHOOL_SPECS["丰台区"] = [
    ("北京市第十二中学", [("校园动态", dict(
        url="https://www2.bj12hs.com.cn/",
        pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]{6,})</a>',
        base="https://www2.bj12hs.com.cn/",
        exclude=r"数字校园|创新人才学院|备案|登录"))]),
    ("北京市丰台第二中学", [("校园动态", dict(
        url="https://bjf2.ftedu.cn/ftez/708970/index.html",
        pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]{6,})</a>',
        base="https://bjf2.ftedu.cn"))]),
]
SCHOOL_SPECS["顺义区"] = [
    ("北京市顺义区第一中学", [("校园动态", dict(
        url="https://bjsyyz.cn/",
        pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]{8,})</a>',
        base="https://bjsyyz.cn/",
        exclude=r"首页|学校简介|联系我们|友情链接"))]),
]
SCHOOL_SPECS["昌平区"] = [
    ("北京市昌平区第一中学", [("校园动态", dict(
        url="http://www.cpyz.org.cn/",
        pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]{8,})</a>',
        base="http://www.cpyz.org.cn/",
        exclude=r"首页|学校简介|联系我们|友情链接"))]),
    ("北京市昌平区第二中学", [("校园动态", dict(
        url="https://bjcpez.com.cn/AdmissionInformation",
        pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]{8,})</a>',
        base="https://bjcpez.com.cn/",
        exclude=r"首页|学校简介|联系我们|友情链接"))]),
]

# 学校目录：先保证每个区有代表性学校入口；有稳定官网解析规则的学校
# 继续使用 SCHOOL_SPECS，只有目录入口的学校会显示“动态待接入”。
SCHOOL_CATALOG = {
    "东城区": ["北京市第二中学", "北京汇文中学", "北京市第五中学"],
    "西城区": ["北京市第四中学", "北京市第八中学", "北京市第十五中学"],
    "朝阳区": ["北京市第八十中学", "陈经纶中学", "北京中学"],
    "海淀区": ["人大附中", "清华附中", "北京大学附属中学"],
    "丰台区": ["北京市第十二中学", "北京市第十八中学", "北京市丰台第二中学"],
    "石景山区": ["北京市第九中学", "北京市京源学校", "北京市十一学校石景山实验中学"],
    "门头沟区": ["北京市大峪中学", "北京市门头沟区实验中学", "首都师范大学附属中学永定分校"],
    "房山区": ["北京市房山中学", "北京市房山区良乡中学", "首都师范大学附属中学房山学校"],
    "通州区": ["北京市通州区潞河中学", "北京学校", "人大附中通州校区"],
    "顺义区": ["北京市顺义牛栏山第一中学", "北京市顺义区第一中学", "北京市顺义区杨镇第一中学"],
    "昌平区": ["北京市昌平区第一中学", "北京市昌平区第二中学", "北京市昌平区实验学校"],
    "大兴区": ["北京市大兴区第一中学", "北京市大兴区兴华中学", "北京亦庄实验中学"],
    "平谷区": ["北京市平谷中学", "北京市平谷区第五中学", "北京市平谷区马坊实验中学"],
    "怀柔区": ["北京市怀柔区第一中学", "北京市怀柔区第二中学", "北京市怀柔区第五中学"],
    "密云区": ["北京市密云区第二中学", "首都师范大学附属密云中学", "北京师范大学密云实验中学"],
    "延庆区": ["北京市延庆区第一中学", "北京市延庆区第二中学", "北京市延庆区第五中学"],
    "燕山地区": ["北京市房山区燕山前进中学", "北京市房山区燕山向阳中学", "北京师范大学燕化附属中学"],
    "经济技术开发区": ["北京亦庄实验中学", "北京市第二中学经开区学校", "人大附中北京经济技术开发区学校"],
}

# 学校官网不可达或动态渲染时，使用区政府/教委公开教育动态作为官方替代源。
# 列表页只抓有限条目；学校名未出现在标题时，再检查详情正文。
_PLAIN_LINK = r'<a[^>]+href=["\'](?P<link>[^"\']+)["\'][^>]*>\s*(?P<title>[\s\S]{8,500}?)\s*</a>'
SCHOOL_GOV_FEEDS = {
    "东城区": dict(
        spec=dict(url="https://www.bjdch.gov.cn/zwgk/jgdh/qzfzcbmdh/qjw/bmgzqjw/",
                  pattern=_PLAIN_LINK, base="https://www.bjdch.gov.cn/zwgk/jgdh/qzfzcbmdh/qjw/bmgzqjw/"),
        aliases={"北京市第二中学": ["北京市第二中学", "北京二中"],
                 "北京汇文中学": ["北京汇文中学"],
                 "北京市第五中学": ["北京市第五中学", "北京五中"]}),
    "西城区": dict(
        spec=dict(url="https://www.bjxch.gov.cn/xxgk/zdly/jyylyjhsy/ywjy/ywjyjhfz.html",
                  pattern=_PLAIN_LINK, base="https://www.bjxch.gov.cn"),
        aliases={"北京市第四中学": ["北京市第四中学", "北京四中"],
                 "北京市第八中学": ["北京市第八中学", "北京八中"],
                 "北京市第十五中学": ["北京市第十五中学", "北京十五中"]}),
    "石景山区": dict(
        spec=dict(url="https://www.bjsjs.gov.cn/gongkai/zwgkpd/zdly_1960/jy_1975/index.shtml",
                  pattern=_PLAIN_LINK, base="https://www.bjsjs.gov.cn/gongkai/zwgkpd/zdly_1960/jy_1975/"),
        aliases={"北京市第九中学": ["北京市第九中学", "九中教育集团"],
                 "北京市京源学校": ["北京市京源学校", "京源学校"],
                 "北京市十一学校石景山实验中学": ["十一学校石景山实验中学"]}),
    "门头沟区": dict(
        spec=dict(url="https://www.bjmtg.gov.cn/bjmtg/zwxx/zwgg/index.shtml",
                  pattern=_PLAIN_LINK, base="https://www.bjmtg.gov.cn"),
        aliases={"北京市大峪中学": ["北京市大峪中学", "大峪中学"],
                 "北京市门头沟区实验中学": ["门头沟区实验中学", "京师实验中学"],
                 "首都师范大学附属中学永定分校": ["首都师范大学附属中学永定分校", "首师大附中永定分校"]}),
    "房山区": dict(
        spec=dict(url="https://www.bjfsh.gov.cn/zhxw/bmdt/index.shtml",
                  pattern=_PLAIN_LINK, base="https://www.bjfsh.gov.cn/zhxw/bmdt/"),
        aliases={"北京市房山中学": ["北京市房山中学", "房山中学"],
                 "北京市房山区良乡中学": ["房山区良乡中学", "良乡中学"],
                 "首都师范大学附属中学房山学校": ["首都师范大学附属中学房山学校", "首师大附中房山"]}),
    "大兴区": dict(
        spec=dict(url="https://www.bjdx.gov.cn/bjsdxqrmzf/zhyw/bmdt66/index.html",
                  pattern=_PLAIN_LINK, base="https://www.bjdx.gov.cn"),
        aliases={"北京市大兴区第一中学": ["大兴区第一中学", "大兴一中"],
                 "北京市大兴区兴华中学": ["大兴区兴华中学", "兴华中学"],
                 "北京亦庄实验中学": ["北京亦庄实验中学", "亦庄实验中学"]}),
    "怀柔区": dict(
        spec=dict(url="https://www.bjhr.gov.cn/zjhr/bxsh/jyzx/index.html",
                  pattern=_PLAIN_LINK, base="https://www.bjhr.gov.cn/zjhr/bxsh/jyzx/"),
        aliases={"北京市怀柔区第一中学": ["怀柔区第一中学", "怀柔一中"],
                 "北京市怀柔区第二中学": ["怀柔区第二中学", "怀柔二中"],
                 "北京市怀柔区第五中学": ["怀柔区第五中学", "怀柔五中"]}),
    "密云区": dict(
        spec=dict(url="https://www.bjmy.gov.cn/ywdt/gzdt/",
                  pattern=_PLAIN_LINK, base="https://www.bjmy.gov.cn/ywdt/gzdt/"),
        aliases={"北京市密云区第二中学": ["密云区第二中学", "密云二中"],
                 "首都师范大学附属密云中学": ["首都师范大学附属密云中学", "首师大附中密云中学"],
                 "北京师范大学密云实验中学": ["北京师范大学密云实验中学", "北师大密云实验中学"]}),
    "延庆区": dict(
        spec=dict(url="https://bj.wenming.cn/yq/tpxw/",
                  pattern=_PLAIN_LINK, base="https://bj.wenming.cn", enc="auto"),
        aliases={"北京市延庆区第一中学": ["延庆区第一中学", "延庆一中"],
                 "北京市延庆区第二中学": ["延庆区第二中学", "延庆二中"],
                 "北京市延庆区第五中学": ["延庆区第五中学", "延庆五中"]}),
    "燕山地区": dict(
        spec=dict(url="https://www.bjfsh.gov.cn/zwgk/qmzqb/ghjh_2674/index_bm.shtml",
                  pattern=_PLAIN_LINK, base="https://www.bjfsh.gov.cn/zwgk/qmzqb/ghjh_2674/"),
        aliases={"北京市房山区燕山前进中学": ["燕山前进中学", "前进中学"],
                 "北京市房山区燕山向阳中学": ["燕山向阳中学", "向阳中学"],
                 "北京师范大学燕化附属中学": ["北京师范大学燕化附属中学", "燕化附属中学", "北师大燕化附中"]}),
    "经济技术开发区": dict(
        spec=dict(url="https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/",
                  pattern=_PLAIN_LINK, base="https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/"),
        aliases={"北京亦庄实验中学": ["北京亦庄实验中学", "亦庄实验中学"],
                 "北京市第二中学经开区学校": ["北京市第二中学经开区学校", "二中经开区学校"],
                 "人大附中北京经济技术开发区学校": ["人大附中北京经济技术开发区学校"]}),
}


def _official_seed(title: str, link: str) -> dict:
    return {"title": title, "link": link, "tag": "官方信息", "kp": "官方信源", "src": "区级官方"}


# 实时列表暂无匹配时的官方兜底条目；仅用于避免学校栏目长期为空。
SCHOOL_OFFICIAL_SEEDS = {
    "东城区": {
        school: [_official_seed("东城区2026年学校官方信息", "https://www.bjdch.gov.cn/ztzl/bmyjsgkzl/bmysgkzl/2026nys/qzf2026ys/202602/t20260212_4511006.html")]
        for school in SCHOOL_CATALOG["东城区"]
    },
    "丰台区": {
        "北京市第十八中学": [_official_seed("北京市2026年具有招生资格的学校名单", "https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260519_4656965.html")],
    },
    "顺义区": {
        "北京市顺义牛栏山第一中学": [_official_seed("北京市2026年具有招生资格的学校名单", "https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260519_4656965.html")],
        "北京市顺义区杨镇第一中学": [_official_seed("北京市2026年具有招生资格的学校名单", "https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260519_4656965.html")],
    },
    "昌平区": {
        "北京市昌平区实验学校": [_official_seed("北京市2026年具有招生资格的学校名单", "https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260519_4656965.html")],
    },
    "石景山区": {
        school: [_official_seed("石景山区2026年初中入学学校名单", "https://www.bjsjs.gov.cn/gongkai/zwgkpd/ztzl/2026/sjsywjyzl/xgfw/202605/t20260507_761565.shtml")]
        for school in SCHOOL_CATALOG["石景山区"]
    },
    "西城区": {
        school: [_official_seed("西城区学校地址及办学信息", "https://www.bjxch.gov.cn/xxgk/xxxq/pnidpv909665.html")]
        for school in SCHOOL_CATALOG["西城区"]
    },
    "门头沟区": {
        school: [_official_seed("门头沟区初中学校官方名录", "https://www.bjmtg.gov.cn/bjmtg/c103090/202212/30bd097c14d04e30ad619a9eb9062521.shtml")]
        for school in SCHOOL_CATALOG["门头沟区"]
    },
    "房山区": {
        "北京市房山中学": [_official_seed("2026年房山区高考考点及学校信息", "https://www.bjfsh.gov.cn/zhxw/fsdt/202606/t20260605_40114417_fs.shtml")],
        "北京市房山区良乡中学": [_official_seed("2026年房山区高考考点及学校信息", "https://www.bjfsh.gov.cn/zhxw/fsdt/202606/t20260605_40114417_fs.shtml")],
        "首都师范大学附属中学房山学校": [_official_seed("房山区基础教育创新发展动态", "https://www.bjfsh.gov.cn/zhxw/fsb/202604/P020260430584823239425.pdf")],
    },
    "通州区": {
        school: [_official_seed("通州区中小学官方信息及联系电话", "https://www.bjtzh.gov.cn/bjtz/zwgk/tjsj/sjkf/2026052215435127308/index.shtml")]
        for school in SCHOOL_CATALOG["通州区"]
    },
    "大兴区": {
        "北京市大兴区第一中学": [_official_seed("大兴区优质教育集团建设动态", "https://www.bjdx.gov.cn/bjsdxqrmzf/zhyw/bmdt66/2139180/index.html")],
        "北京市大兴区兴华中学": [_official_seed("大兴区优质教育集团建设动态", "https://www.bjdx.gov.cn/bjsdxqrmzf/zhyw/bmdt66/2139180/index.html")],
        "北京亦庄实验中学": [_official_seed("北京亦庄实验中学2026年教育动态", "https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/202610/t20261009_4894513.html")],
    },
    "平谷区": {
        school: [_official_seed("北京市2026年具有招生资格的学校名单", "https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260519_4656965.html")]
        for school in SCHOOL_CATALOG["平谷区"]
    },
    "怀柔区": {
        "北京市怀柔区第一中学": [_official_seed("北京十一学校怀柔实验学校（怀柔一中）官方信息", "https://www.bjhr.gov.cn/zjhr/bxsh/jykj/jyzx/201911/t20191121_517308.html")],
        "北京市怀柔区第二中学": [_official_seed("怀柔区2026年高中学校教育动态", "https://www.bjhr.gov.cn/zjhr/bxsh/jyzx/202609/t20260904_4850782.html")],
        "北京市怀柔区第五中学": [_official_seed("怀柔五中入选人工智能应用场景标杆学校", "https://www.bjhr.gov.cn/zjhr/bxsh/jyzx/202602/t20260225_4539588.html")],
    },
    "密云区": {
        "北京市密云区第二中学": [_official_seed("密云二中2026年学校动态", "https://www.bjmy.gov.cn/zwgk/ztbd/xymy/xyxx/202609/t20260921_553091.html")],
        "首都师范大学附属密云中学": [_official_seed("密云区优质学校教育动态", "https://www.bjmy.gov.cn/ywdt/gzdt/202509/t20250911_511910.html")],
        "北京师范大学密云实验中学": [_official_seed("密云区2026年高考考点学校信息", "https://www.bjmy.gov.cn/zwgk/hygq/202606/t20260603_543905.html")],
    },
    "延庆区": {
        school: [_official_seed("北京市2026年具有招生资格的学校名单", "https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260519_4656965.html")]
        for school in SCHOOL_CATALOG["延庆区"]
    },
    "经济技术开发区": {
        "北京亦庄实验中学": [_official_seed("北京亦庄实验中学2026年教育动态", "https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/202610/t20261009_4894513.html")],
        "北京市第二中学经开区学校": [_official_seed("经开区2026年学校培养实验动态", "https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/202607/t20260722_4777982.html")],
        "人大附中北京经济技术开发区学校": [_official_seed("经开区2026年教育领域学校信息", "https://kfqgw.beijing.gov.cn/zwgkkfq/tzgg/202608/t20260825_4836554.html")],
    },
}

# 区级教育动态信源：区 -> (机构名, [源配置 spec])；spec 结构同上
DISTRICT_GOV_SPECS = {
    "海淀区": ("海淀教育网", [
        dict(url="https://www.bjhdedu.cn/gongkai/tzgg/",
             pattern=r'<a href="(?P<link>\./\d{6}/t\d{8}_\d+\.html)"[^>]*>(?P<title>[^<]{6,})</a>\s*<span>(?P<date>[\d-]+)</span>',
             base="https://www.bjhdedu.cn/gongkai/tzgg/", re_s=True),
    ]),
    "东城区": ("东城区教委 · 通知公告", [
        dict(url="https://www.bjdch.gov.cn/zwgk/jgdh/qzfzcbmdh/qjw/tzggqjw/",
             pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>\s*(?P<title>[^<]{6,})\s*</a>\s*(?:<[^>]+>\s*)?(?P<date>20\d{2}-\d{2}-\d{2})',
             base="https://www.bjdch.gov.cn", re_s=True, enc="auto"),
    ]),
    "丰台区": ("丰台区教委 · 教育公开", [
        dict(url="https://www.bjft.gov.cn/xxfb/zdlygs/c100013/list_ftb_1.shtml",
             pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>\s*(?P<title>[^<]{6,})\s*</a>\s*(?:<[^>]+>\s*)?(?P<date>20\d{2}-\d{2}-\d{2})',
             base="https://www.bjft.gov.cn", re_s=True, enc="auto"),
    ]),
    "石景山区": ("石景山区教委 · 政策公开", [
        dict(url="https://www.bjsjs.gov.cn/gongkai/",
             pattern=r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>\s*(?P<title>[^<]{6,})\s*</a>\s*(?:<[^>]+>\s*)?(?P<date>20\d{2}-\d{2}-\d{2})',
             base="https://www.bjsjs.gov.cn", re_s=True, enc="auto"),
    ]),
}

YJRX_JSON = "https://yjrx.bjedu.cn/uploads/json/{}.json"
YJRX_ITEM_URL = "https://yjrx.bjedu.cn{}"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CTX = ssl.create_default_context()


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def fetch_text(spec: dict) -> str:
    raw = fetch(spec["url"])
    enc = spec.get("enc", "utf-8")
    if enc == "auto":
        head = raw[:2048]
        m = re.search(rb'charset=["\']?([\w-]+)', head, re.I)
        enc = m.group(1).decode("ascii", "ignore").lower() if m else "utf-8"
    if enc in ("gb2312", "gbk"):
        enc = "gb18030"
    return raw.decode(enc, errors="ignore")


def parse_spec(spec: dict) -> list:
    """通用列表页解析：按 spec 的正则提取 link/title/date，拼绝对地址。"""
    html = fetch_text(spec)
    flags = re.S if spec.get("re_s") else 0
    items, seen = [], set()
    for m in re.finditer(spec["pattern"], html, flags):
        link = m.group("link").strip()
        title = re.sub(r"<[^>]+>", "", m.group("title")).strip()
        if len(title) < 6 or link in seen:
            continue
        if spec.get("exclude") and re.search(spec["exclude"], title):
            continue
        seen.add(link)
        if link.startswith("./"):
            link = link[2:]
        if spec.get("strip"):
            link = link.replace(spec["strip"], "")
        if spec.get("base") and not link.startswith(("http://", "https://")):
            if link.startswith("/"):
                origin = "/".join(spec["base"].split("/")[:3])
                link = origin + link
            else:
                link = spec["base"] + link
        it = {"title": title, "link": link,
              "tag": tag_of(title), "kp": key_point(title), "src": "学校"}
        if m.groupdict().get("date"):
            it["date"] = m.group("date").strip("[] ")
        items.append(it)
    return items


def assign_school_feed_items(items: list, aliases: dict, detail_loader, detail_limit=None) -> dict:
    """把区政府教育动态按学校别名分配给对应学校。"""
    assigned = {school: [] for school in aliases}
    detail_reads = 0
    for item in items:
        text = item.get("title", "")
        if (not any(alias in text for names in aliases.values() for alias in names)
                and (detail_limit is None or detail_reads < detail_limit)):
            try:
                text += " " + detail_loader(item["link"])
                detail_reads += 1
            except Exception:
                pass
        for school, names in aliases.items():
            if any(alias in text for alias in names):
                assigned[school].append(item)
    return assigned


def merge_school_feed_items(schools: dict, assigned: dict) -> None:
    """合并区级官方动态；有真实条目时移除“待接入”占位。"""
    for school, items in assigned.items():
        if not items:
            continue
        schools.setdefault(school, {})
        schools[school].pop("学校信息", None)
        seen = set()
        unique = []
        for item in items:
            key = item.get("link") or item.get("title")
            if key not in seen:
                seen.add(key)
                unique.append(item)
        schools[school]["区级官方动态"] = unique


def merge_school_seed_items(schools: dict, seeds: dict) -> None:
    """仅当学校没有真实动态时，补入已核验的官方信息条目。"""
    for school, items in seeds.items():
        sections = schools.setdefault(school, {})
        has_live = any(values for name, values in sections.items() if name != "学校信息")
        if has_live:
            continue
        sections.pop("学校信息", None)
        sections["官方学校信息"] = items


def fetch_article_text(url: str) -> str:
    page = fetch_text({"url": url, "enc": "auto"})
    page = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.I | re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


# ---------- 标签 ----------

TAG_RULES = [
    ("入学政策", [r"入学工作", r"入学.{0,4}意见", r"实施细则", r"入学方案", r"招生办法"]),
    ("招生简章", [r"招生简章", r"特长生", r"报名通知", r"信息采集", r"采集通知", r"测试公告"]),
    ("审核细则", [r"审核细则", r"审核办法", r"材料审核"]),
    ("入学问答", [r"问答", r"答疑"]),
]


def tag_of(title: str) -> str:
    for tag, patterns in TAG_RULES:
        if any(re.search(p, title) for p in patterns):
            return tag
    return "通知公告"


def key_point(title: str) -> str:
    parts = []
    m = re.search(r"(20\d{2})", title)
    if m:
        parts.append(m.group(1) + "年")
    for tag, patterns in TAG_RULES:
        if any(re.search(p, title) for p in patterns):
            parts.append(tag)
            break
    return " · ".join(parts) if parts else "常规通知"


# ---------- 拉取 ----------

def fetch_yjrx(fid: str) -> list:
    data = json.loads(fetch(YJRX_JSON.format(fid)).decode("utf-8"))
    return [
        {"title": it["name"], "link": YJRX_ITEM_URL.format(it["accessPath"]), "id": it["id"],
         "tag": tag_of(it["name"]), "kp": key_point(it["name"]), "src": "区政策"}
        for it in data
    ]



def fetch_jw_notice() -> list:
    html = fetch("https://jw.beijing.gov.cn/tzgg/").decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a href="(\./\d{6}/t\d{8}_\d+\.html)">([^<]{6,100})</a>', html):
        items.append({"title": m.group(2).strip(),
                      "link": "https://jw.beijing.gov.cn/tzgg/" + m.group(1)[2:],
                      "tag": tag_of(m.group(2)), "kp": key_point(m.group(2)), "src": "市教委"})
    return items[:12]


def fetch_moe_notice() -> list:
    html = fetch("http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/A01/").decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*title="([^"]{6,80})"', html):
        items.append({"title": m.group(2), "link": m.group(1),
                      "tag": tag_of(m.group(2)), "kp": key_point(m.group(2)), "src": "教育部"})
    return items[:12]


# ---------- diff ----------

def load_prev_keys() -> set:
    p = DOCS / "data.json"
    if not p.exists():
        return set()
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
        keys = set()

        def walk(node):
            if isinstance(node, dict):
                if "link" in node:
                    keys.add(node.get("id") or node.get("link"))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for it in node:
                    walk(it)

        walk(prev.get("data", {}))
        return keys
    except Exception:
        return set()


# ---------- 页面 ----------

HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K12 官方信源看板</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ font-variant-numeric: tabular-nums; }}
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #FBFAF7; color: #212427;
    padding: 28px 20px 40px; line-height: 1.6;
  }}
  .page {{ max-width: 1180px; margin: 0 auto; }}

  /* ── 头部 ───────────────────── */
  header {{ display: flex; justify-content: space-between; align-items: flex-end;
    padding-bottom: 14px; border-bottom: 2px solid #212427; flex-wrap: wrap; gap: 6px; }}
  h1 {{ font-family: "Songti SC", "Noto Serif SC", "SimSun", serif;
    font-size: 22px; font-weight: 700; letter-spacing: .02em; }}
  .meta {{ font-size: 12px; color: #8a877e; }}

  /* ── 招生季时间轴 ─────────────── */
  .season {{ margin: 26px 0 6px; }}
  .track {{
    position: relative; height: 34px; margin: 10px 2px 0;
    border-bottom: 1px solid #E3E1D8;
  }}
  .hot {{
    position: absolute; top: 0; bottom: -1px;
    background: #F0E4DE; opacity: .6;
  }}
  .stop {{
    position: absolute; top: 0; width: 34%; max-width: 120px;
    transform: translateX(-4px); padding-top: 10px;
  }}
  .stop i {{ position: absolute; top: 20px; left: 4px; width: 7px; height: 7px;
    border-radius: 50%; background: #B23B32; display: block; }}
  .stop b {{ font-size: 12px; font-weight: 600; color: #212427; display: block; line-height: 1.3; }}
  .stop em {{ font-style: normal; font-size: 11px; color: #8a877e; }}
  .today {{
    position: absolute; top: 6px; text-align: center;
    animation: mark .5s ease-out .25s backwards;
  }}
  .today b {{
    font-size: 11px; color: #B23B32; font-weight: 600; display: block;
  }}
  .today i {{
    position: absolute; left: -2px; top: 17px; width: 5px; height: 5px;
    border: 1.5px solid #B23B32; border-radius: 50%; background: #FBFAF7;
    display: block;
  }}
  @keyframes mark {{ from {{ opacity: 0; transform: translateY(4px); }} }}
  .season-note {{ font-size: 12px; color: #8a877e; margin-top: 8px; }}

  /* ── 区块标题 ────────────────── */
  h2 {{
    font-family: "Songti SC", "Noto Serif SC", serif;
    font-size: 17px; margin: 34px 0 4px; padding-bottom: 4px;
    border-bottom: 1px solid #B23B32; width: fit-content;
  }}
  h2::after {{ content: ""; }}

  /* ── 市级头条 ────────────────── */
  .city {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 36px; margin-top: 14px; }}
  @media (max-width: 680px) {{ .city {{ grid-template-columns: 1fr; }} }}
  .city h3 {{ font-size: 12px; font-weight: 600; color: #31586E; margin-bottom: 2px; }}
  .headline {{ font-family: "Songti SC", "Noto Serif SC", serif;
    font-size: 15.5px; line-height: 1.5; margin: 4px 0 10px; }}
  .headline a {{ color: #212427; text-decoration: none; }}
  .headline a:hover {{ color: #B23B32; }}
  .headline .n-new {{ margin-right: 6px; }}

  /* ── 条目 ─────────────────── */
  ul {{ list-style: none; }}
  li {{ font-size: 13px; padding: 6px 0; border-bottom: 1px solid #EDEBE3;
    display: flex; gap: 8px; align-items: baseline; }}
  li:last-child {{ border-bottom: none; }}
  li a {{ color: #212427; text-decoration: none; flex: 1; }}
  li a:hover {{ color: #31586E; text-decoration: underline; text-underline-offset: 3px; }}
  .kind {{ font-size: 11px; color: #31586E; white-space: nowrap; }}
  .date {{ font-size: 11px; color: #a5a29a; white-space: nowrap; }}
  .n-new {{
    font-size: 10px; font-weight: 600; background: #B23B32; color: #FBFAF7;
    padding: 0 5px; border-radius: 2px; white-space: nowrap; flex: none;
  }}
  li.empty {{ color: #a5a29a; border: none; }}

  /* ── 区台账 ─────────────────── */
  .ledger {{ margin-top: 14px; border-top: 1px solid #212427; }}
  details.row {{ border-bottom: 1px solid #E3E1D8; }}
  details.row summary {{
    list-style: none; cursor: pointer; padding: 11px 2px;
    display: grid; grid-template-columns: 84px 44px 1fr auto;
    gap: 12px; align-items: baseline;
  }}
  details.row summary::-webkit-details-marker {{ display: none; }}
  details.row summary:hover {{ background: #F3F1EC; }}
  .d-name {{ font-family: "Songti SC", "Noto Serif SC", serif;
    font-weight: 700; font-size: 15px; }}
  .d-count {{ font-size: 12px; color: #8a877e; text-align: right; }}
  .d-latest {{ font-size: 12.5px; color: #6b6862;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .d-side {{ font-size: 11px; color: #31586E; white-space: nowrap; display: flex; gap: 6px; align-items: baseline; }}
  .row-body {{ padding: 2px 2px 18px 96px; }}
  .district-columns {{ display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: 0 34px; }}
  .district-column {{ min-width: 0; }}
  .district-column--schools {{ border-left: 1px solid #E3E1D8; padding-left: 34px; }}
  .column-title {{ font-family: "Songti SC", "Noto Serif SC", serif;
    font-size: 14px; color: #212427; margin: 12px 0 3px; }}
  .column-empty {{ font-size: 12px; color: #a5a29a; padding: 10px 0; }}
  @media (max-width: 760px) {{
    details.row summary {{ grid-template-columns: 72px 1fr auto; }}
    .d-count {{ display: none; }}
    .d-latest {{ grid-column: 1 / -1; white-space: normal; }}
    .row-body {{ padding-left: 2px; }}
    .district-columns {{ grid-template-columns: 1fr; gap: 2px; }}
    .district-column--schools {{ border-left: 0; border-top: 1px solid #E3E1D8;
      margin-top: 14px; padding: 2px 0 0; }}
  }}
  .school-sec {{ margin-top: 12px; }}
  .school-sec h4 {{ font-size: 12px; font-weight: 600; color: #31586E; margin-bottom: 2px; }}
  .open-hint {{ font-size: 11px; color: #a5a29a; padding: 2px 2px 0; }}

  footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #E3E1D8;
    font-size: 12px; color: #a5a29a; line-height: 1.9; }}
  @media (prefers-reduced-motion: reduce) {{ .today {{ animation: none; }} }}
</style>
</head>
<body>
<div class="page">
<header>
  <h1>北京小升初 · 官方信源台账</h1>
  <div class="meta">构建于 {built_at}，每 6 小时自动更新</div>
</header>

<div class="season">
  <div class="track">
    <div class="hot" style="left:31%;width:28%"></div>
    <div class="stop" style="left:31%"><i></i><b>市政策</b><em>4 月中</em></div>
    <div class="stop" style="left:36%"><i></i><b>区细则</b><em>4 月底</em></div>
    <div class="stop" style="left:42%"><i></i><b>信息采集</b><em>5 月</em></div>
    <div class="stop" style="left:47%"><i></i><b>派位</b><em>6 月</em></div>
    <div class="stop" style="left:55%"><i></i><b>录取</b><em>7 月</em></div>
    <div class="today" style="left:{today_pct:.0f}%"><b>今天</b><i></i></div>
  </div>
  <div class="season-note">{season_note}</div>
</div>
"""


def item_li(it: dict, prev_keys: set) -> str:
    is_new = (it.get("id") or it.get("link")) not in prev_keys
    new = '<span class="n-new">NEW</span>' if is_new else ""
    kind = it.get("tag", "")
    date = f'<span class="date">{it["date"]}</span>' if it.get("date") else ""
    return (
        f'<li>{new}<span class="kind">{kind}</span>'
        f'<a href="{it["link"]}" target="_blank">{it["title"]}</a>{date}</li>'
    )


def section(title: str, items: list, prev_keys: set, max_show: int = 5) -> str:
    if not items:
        return f'<div class="school-sec"><h4>{title}</h4><ul><li class="empty">暂无数据</li></ul></div>'
    top_lis = "".join(item_li(it, prev_keys) for it in items[:max_show])
    more = ""
    if len(items) > max_show:
        rest_lis = "".join(item_li(it, prev_keys) for it in items[max_show:])
        more = f'<li style="display:block"><details><summary class="open-hint" style="cursor:pointer">其余 {len(items) - max_show} 条</summary><ul style="margin-top:4px">{rest_lis}</ul></details></li>'
    return f'<div class="school-sec"><h4>{title} · {len(items)} 条</h4><ul>{top_lis}{more}</ul></div>'


def build_page(data: dict, prev_keys: set, built_at: str) -> str:
    jw, moe = data["市教委"], data["教育部"]

    # 时间轴：今天在学年周期里的位置（1月=0%，12月≈92%）
    now = datetime.now(timezone(timedelta(hours=8)))
    today_pct = (now.month + now.day / 31) / 12 * 100
    if 8 <= now.month <= 12 or now.month <= 3:
        season_note = "当前处于招生季空窗期。政策集中发布于每年 4 至 7 月，届时本页各区行的更新徽章即为信号。"
    else:
        season_note = "招生季进行中，政策更新频繁，注意各区 NEW 标记。"

    parts = [HTML_HEAD.format(built_at=built_at, today_pct=today_pct, season_note=season_note)]

    # 市级头条
    parts.append('<h2>市级</h2><div class="city">')
    for name, items in (("北京市教委 · 通知公告", jw), ("教育部 · 公告公示", moe)):
        if items:
            top = items[0]
            top_new = '<span class="n-new">NEW</span>' if top["link"] not in prev_keys else ""
            parts.append(
                f'<div><h3>{name} · {len(items)} 条</h3>'
                f'<div class="headline">{top_new}<a href="{top["link"]}" target="_blank">{top["title"]}</a></div>'
                f'<ul>{"".join(item_li(it, prev_keys) for it in items[1:6])}</ul></div>'
            )
        else:
            parts.append(f'<div><h3>{name}</h3><ul><li class="empty">拉取失败</li></ul></div>')
    parts.append("</div>")

    # 区台账
    parts.append('<h2>分区台账</h2><div class="ledger">')
    for 区名, fid in DISTRICTS.items():
        d = data["区级"][区名]
        policies = d["政策"]
        gov = d["动态"]
        schools = d["学校"]
        n_new = sum(1 for it in policies if (it.get("id") or it.get("link")) not in prev_keys)
        latest = policies[0]["title"] if policies else "（无数据）"
        school_label = f"{len(schools)} 校" if schools else ""
        new_badge = f'<span class="n-new">{n_new} 新</span>' if n_new else ""
        official_sections = section("区招生政策", policies, prev_keys, max_show=4)
        if gov:
            name, items = gov
            official_sections += section(f"{name} · 教育动态", items, prev_keys, max_show=4)
        school_sections = ""
        for 校名, 栏目 in schools.items():
            for 栏名, items in 栏目.items():
                school_sections += section(f"{校名} · {栏名}", items, prev_keys, max_show=4)
        if not school_sections:
            school_sections = '<p class="column-empty">暂无学校动态</p>'

        parts.append(
            f'<details class="row"{" open" if (schools or n_new) else ""}><summary>'
            f'<span class="d-name">{区名}</span>'
            f'<span class="d-count">{len(policies)} 条</span>'
            f'<span class="d-latest">{latest}</span>'
            f'<span class="d-side">{new_badge}{school_label}</span>'
            f"</summary>"
            f'<div class="row-body"><div class="district-columns">'
            f'<section class="district-column district-column--official">'
            f'<h3 class="column-title">区级信息</h3>{official_sections}</section>'
            f'<section class="district-column district-column--schools">'
            f'<h3 class="column-title">学校动态</h3>{school_sections}</section>'
            f'</div></div></details>'
        )
    parts.append("</div>")

    src_domains = sorted({
        re.sub(r"^https?://(www\.)?", "", it["link"]).split("/")[0]
        for sec in data["区级"].values()
        for it in (sec["动态"][1] if sec["动态"] else [])
    })
    parts.append(
        "<footer>信源：yjrx.bjedu.cn（18 区招生政策）｜ jw.beijing.gov.cn ｜ moe.gov.cn ｜ "
        "rdfz.cn ｜ qhfz.edu.cn ｜ bjsdfz.com ｜ cnuhs.cn"
        + (f" ｜ 区教委：{' ｜ '.join(src_domains)}" if src_domains else "")
        + "<br>多数学校无独立官网或页面动态渲染，公众号渠道经 wewe-rss 另行接入，不在本台账。</footer>"
    )
    return "".join(parts) + "</div></body></html>"


def main():
    built_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    prev_keys = load_prev_keys()

    区级 = {}
    for 区名, fid in DISTRICTS.items():
        try:
            政策 = fetch_yjrx(fid)
        except Exception:
            政策 = []
        动态 = None
        if 区名 in DISTRICT_GOV_SPECS:
            name, specs = DISTRICT_GOV_SPECS[区名]
            items = []
            for spec in specs:
                try:
                    for it in parse_spec(spec):
                        it["src"] = "区教委"
                        items.append(it)
                except Exception:
                    pass
            动态 = (name, items) if items else None
        学校 = {}
        configured = {校名 for 校名, _ in SCHOOL_SPECS.get(区名, [])}
        for 校名 in SCHOOL_CATALOG.get(区名, []):
            if 校名 not in configured:
                学校[校名] = {"学校信息": [{
                    "title": "学校信息入口（动态栏目待接入）",
                    "link": "https://yjrx.bjedu.cn/",
                    "tag": "信源状态", "kp": "待接入", "src": "学校"
                }]}
        for 校名, 栏目 in SCHOOL_SPECS.get(区名, []):
            学校[校名] = {}
            for 栏名, spec in 栏目:
                try:
                    学校[校名][栏名] = parse_spec(spec)
                except Exception:
                    学校[校名][栏名] = []
        if 区名 in SCHOOL_GOV_FEEDS:
            feed = SCHOOL_GOV_FEEDS[区名]
            try:
                feed_items = parse_spec(feed["spec"])
                relevant = re.compile(r"教育|学校|中学|开学|教师|招生|中考|高考|校园|学子|学生|少年")
                feed_items = [it for it in feed_items if relevant.search(it["title"])][:24]
                for it in feed_items:
                    it["src"] = "区级官方"
                assigned = assign_school_feed_items(
                    feed_items, feed["aliases"], fetch_article_text, detail_limit=3
                )
                merge_school_feed_items(学校, assigned)
            except Exception:
                pass
        merge_school_seed_items(学校, SCHOOL_OFFICIAL_SEEDS.get(区名, {}))
        区级[区名] = {"政策": 政策, "动态": 动态, "学校": 学校}

    # 单一路信源短暂不可达时，不应让整次构建失败；页面会以空列表展示该路。
    try:
        市教委 = fetch_jw_notice()
    except Exception:
        市教委 = []
    try:
        教育部 = fetch_moe_notice()
    except Exception:
        教育部 = []
    data = {
        "市教委": 市教委,
        "教育部": 教育部,
        "区级": 区级,
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(
        json.dumps({"built_at": built_at, "data": data}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOCS / "index.html").write_text(build_page(data, prev_keys, built_at), encoding="utf-8")

    d_online = sum(1 for d in 区级.values() if d["政策"])
    g_online = sum(1 for d in 区级.values() if d["动态"])
    print(
        f"built: {built_at} | 市教委 {len(data['市教委'])} | 教育部 {len(data['教育部'])} | "
        f"区在线 {d_online}/18 | 区教委 {g_online} | 学校 {sum(len(d['学校']) for d in 区级.values())} 所"
    )


if __name__ == "__main__":
    main()
