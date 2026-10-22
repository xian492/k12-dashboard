#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K12 官方信源看板构建脚本 v5。

v5 布局：按区分组。市级置顶；区卡片 = 区招生政策(yjrx) + 区教委动态 + 该区学校官网（按校名合并）。
信源：yjrx 18 区 + 市教委 + 教育部 + 学校官网/区教委官网（配置驱动，见 SCHOOL_SPECS / DISTRICT_GOV_SPECS）。

用法：python3 build.py（无第三方依赖）
"""
import json
import re
import asyncio
from html import escape
import importlib.util
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
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

def _school(homepage: str, *wechats: str) -> dict:
    """学校导航元数据；仅用于页面入口，不参与抓取。"""
    return {"homepage": homepage, "wechats": tuple(wechat.strip() for wechat in wechats)}


# 太星网络“北京小升初 · 关注网站”页面中的学校网站（2026-10-22 核对）。
# 名称按当前看板做了少量规范化；被来源页相对地址包裹的链接已还原为学校域名。
TAIXING_SCHOOL_DIRECTORY = {
    "海淀区": {
        "北京市上地实验学校": _school("http://www.shd101.com/", "SHD-101"),
        "北京市清河中学": _school("http://www.qhzhx.com/cms/", "gh_602f6abe1511"),
        "北京市十一学校龙樾实验中学": _school("http://www.shiyilongyue.com/", "shiyilongyue"),
        "人大附中北大附小联合实验学校": _school("http://www.bjkedi.com/", "gh_2d9df47d6711"),
        "交大附中": _school("http://www.bfjdfz.net/", "bfjdfz62116381"),
        "海淀教师进修学校附属实验学校": _school("http://www.eshttc.cn/index.html", "eshttc1998"),
        "北京理工大学附属中学分校": _school("http://www.lgfzfx.com.cn/", "bjlgfzfx"),
        "北京市第十九中学": _school("http://www.bj19zx.cn/Domain/1", "bj19zx"),
        "清华附中": _school("http://www.qhfz.edu.cn/", "qhfz1915"),
        "北京外国语大学附属中学": _school("http://www.bjwgydxfszx.com/", "bwfzwx"),
        "北京市十一学校": _school("http://www.bnds.cn/", "BNDS11", "BNDSOpenDay"),
        "人大附中": _school("http://www.rdfz.cn/", "rdfz1950"),
        "北京市第二十中学": _school("https://www.bj20zx.com/", "bj20zxchuzhongbu"),
        "北京市北达资源中学": _school("http://bdzy.pku.edu.cn/", "bjbdzyzx"),
        "北京市育英中学": _school("http://www.yyzx.org/", "gh_6f16daf5de56"),
        "人大附中翠微学校": _school("http://www.rdfzcw.cn/", "rdfzcwxx"),
        "北京市第五十七中学": _school("http://www.57class.net/", "Beijing57HighSchool"),
        "首都师范大学第二附属中学": _school("http://www.cnu2school.bjedu.cn/cms/home/", "ssdefz"),
        "北京市海淀实验中学": _school("http://www.hdsyzx.com/", "hd_syzx"),
        "首师大附中": _school("http://www.cnuschool.org/", "shoudushidafuzhong"),
        "北京科技大学附属中学": _school("http://www.bjgyfz.bjedu.cn/"),
        "北京市中关村中学": _school("http://www.hdzgczx.bjedu.cn/", "bj_zgczx"),
        "北京大学附属中学": _school("http://www.pkuschool.edu.cn/", "bdfz_czb"),
        "中国人民大学附属中学分校": _school("http://www.fx.rdfz.cn/", "rdfz_fx"),
        "一零一中学": _school("http://www.beijing101.com/", "gh_370ef0e1df58"),
        "人大附中西山学校": _school("http://www.rdfzxishan.cn/site/default.aspx?PageID=1", "rdfzxsxx"),
        "北京市师达中学": _school("http://www.bjsdschool.cn/", "bjsdschool"),
        "清华大学附属中学永丰学校": _school("http://www.qhfzyf.cn/cms/cms/index.jsp", "qhfzyf"),
        "北京航空航天大学实验学校": _school("http://www.bhfz.com/", "gh_47986a3ab603"),
        "北京市建华实验学校": _school("http://www.bjjh.org.cn/", "jianhuaxuexiao"),
        "北京市海淀外国语学校": _school("https://www.bjfles.com/", "bjfles"),
        "清华大学附属实验学校": _school("http://www.qhfz.edu.cn/"),
        "北京市中关村外国语学校": _school("http://www.zgcschool.cn/", "zgcschool"),
        "北京市21世纪国际学校": _school("http://www.21cis.com.cn/", "beijing21CIS"),
        "北京市十一学校一分校": _school("http://www.bndsyfx.cn/", "gh_6c980402807c"),
        "北京理工大学附属中学": _school("http://www.lgfz.com.cn/", "gh_b10333b941dd"),
        "北外附属外国语学校": _school("https://www.bwfx.com.cn/", "gh_dece8e1310f5"),
        "北京市育英学校": _school("http://www.yuying.org.cn/", "mini-yyxx"),
        "八一学校": _school("http://www.bayims.cn/", "jizhezhan-81", "weixin81xsh"),
    },
    "朝阳区": {
        "北京师范大学朝阳附属中学": _school("http://www.bsdcyfz.com/", "bsdcyfz"),
        "北京市第八十中学管庄分校": _school("http://www.bj80gz.com/"),
        "东北师范大学附属中学朝阳学校": _school("http://www.msannucy.com/", "msannucy"),
        "北京中学": _school("http://www.beijingacademy.com.cn/cms/", "BeijingAcademy"),
        "北京市第八十中学": _school("http://www.bj80.com/", "beijing80zx"),
        "中国人民大学附属中学朝阳学校": _school("http://www.rdfzcy.cn/SitePages/Home.aspx", "rdfzcy2010"),
        "北京师范大学三帆中学朝阳学校": _school("http://career.bnu.edu.cn/front/zpxx.jspa?tid=103970", "sanfancy2012"),
        "北京市陈经纶中学分校": _school("http://cjlfx.bjchyedu.cn/"),
        "北京市陈经纶中学分校实验学校": _school("http://cfsyxx.bjchyedu.cn/", "cjlfxsyxx"),
        "北京市和平街第一中学": _school("http://www.phs.bj.cn/", "hepingjieyizhong"),
        "北京市朝阳区人大附中朝阳分校": _school("http://www.rdfzcygj.cn/", "rdfzcygj-dy"),
        "陈经纶中学": _school("http://www.bjcjl.net/", "bjcjl_dyh"),
        "日坛中学": _school("http://rtzx.bjchyedu.cn/", "rtjyjt"),
        "工大附中": _school("http://www.bjgdfz.com/", "bjgdfz"),
        "清华大学附属中学朝阳学校": _school("http://qhfzcyxx.bjchyedu.cn/index.shtml", "qhfzcyxx"),
        "朝阳外国语学校": _school("http://www.cyfls.net/", "chaoyangwaiguoyu"),
        "北京拔萃双语学校": _school("http://www.bacui.cn/", "bacuichuzhongbu"),
    },
    "西城区": {
        "北京市第十三中学分校": _school("http://www.bj13zfx.com/cms/", "bj13zfx"),
        "北师大附属实验中学分校": _school("http://www.sdsz.com.cn/", "SDSZer"),
        "北京市三帆中学": _school("http://www.sanfan.cn/", "sanfanzhongxue"),
        "北京市第一六一中学": _school("http://www.bj161zhx.org/", "bj161hs"),
        "北京市第四中学": _school("http://bhsf.lezhiyun.com/cms/bjsz/index.htm", "bhsf-cn"),
        "北京市第一五六中学": _school("http://bj156.xchjw.cn/homepage/index.jsp"),
        "北京市第八中学": _school("http://www.no8ms.bj.cn/cms/home/", "bjno8ms"),
        "北京市第三十五中学": _school("http://www.bj35.com/site/default.aspx?PageID=1", "bj35czb"),
        "北京市铁路第二中学": _school("http://www.bjt2z.cn/", "gh_b8296095ddd8"),
        "北京市第五十六中学": _school("http://www.bj56zhx.org/"),
        "北京市西城外国语学校": _school("http://www.xjfls.org/index.aspx"),
        "北师大附中": _school("http://www.bjsdfz.com/", "gh_2abce13e7fca"),
        "北京市第十五中学": _school("http://www.bj15.cn/index.php/Home/Index/index", "bj15middleschool"),
        "北京市第十四中学": _school("http://www.bj14.com.cn/", "bj14zx"),
        "北京市回民学校": _school("https://www.bjhmxx.com/", "bjhmxxx"),
        "北京市华夏女子中学": _school("http://www.hxgs.net/", "gh_cccd3a87bc87"),
        "北京市宣武外国语实验学校": _school("http://www.flesedu.com/", "flesedu"),
        "北京师范大学亚太实验学校": _school("http://www.yataischool.net/sportal17/gotoHome.do", "bnuaps"),
        "北京市正泽学校": _school("http://www.bjzzschool.com/"),
    },
    "东城区": {
        "北京市第二中学分校": _school("http://www.2zfx.com/", "gh_e58623c6777c"),
        "北京市第五中学分校": _school("http://www.bjwzfx.com.cn/", "bjwzfx_wxpt"),
        "北京市文汇中学": _school("http://www.wenhui1997.com/", "wenhuizhongxue"),
        "北京市第十一中学分校": _school("http://www.bjsdsyf.com/", "gh_f93e0b56510d"),
        "北京市第二十二中学": _school("http://www.bj22z.com/", "gh_be67aa40fc21"),
        "北京市第一六六中学": _school("http://www.bj166z.cn/", "bj166z"),
        "北京市东直门中学": _school("http://www.dzmzx.com.cn/", "bjsdzmzx"),
        "北京市第六十五中学": _school("http://www.bj65z.com/"),
        "北京市第二十五中学": _school("http://www.bj25schooledu.com.cn/", "bj25schooledu"),
        "北京市第一七一中学": _school("http://www.171sch.com/", "bjsdyqyzx"),
        "北京市第五十五中学": _school("http://www.bj55.cn/", "bj55hs"),
        "中央工艺美术学院附属中学": _school("http://www.gmfzh.com/", "gmfzhong"),
        "北京市广渠门中学": _school("http://www.gqmms.com/", "BJGQMMS"),
        "北京市第五十中学": _school("http://www.bj50.com/"),
        "北京汇文中学": _school("http://www.pka.edu.cn/", "bjhwzx"),
        "北京市景山学校": _school("http://www.bjjsschool.net/", "bjjsschool"),
    },
    "丰台区": {
        "北京市第十二中学": _school("http://www.bj12hs.com.cn/", "gh_1093c15cd389"),
        "北京市丰台第二中学": _school("http://www.bjf2.ftedu.cn/bxn-cms/cms/", "bjft2z"),
        "首都师范大学附属丽泽中学": _school("http://www.lzms.cn/", "lizejunpeng"),
        "北京市第八中学怡海分校": _school("http://yhjyzx.ftbj.net/", "BJBZYHFX"),
        "北京市第十中学": _school("http://www.bj10z.com.cn/", "bjd10z"),
        "北京市第十八中学": _school("http://www.bj18.net/cms/", "bjd18z"),
        "中国人民大学附属中学丰台学校": _school("http://www.rdfzftxx.cn/", "gh_31b5c4aa5d7c"),
    },
    "昌平区": {
        "北京王府学校": _school("http://www.brs.edu.cn/", "BRS2003"),
        "北京市昌平区第一中学": _school("http://www.cpyz.org.cn/"),
        "北京市昌平区第二中学": _school("http://www.bjcpez.net/", "bjcpez"),
        "北京市昌平区回龙观中学": _school("http://www.hlgzhx.net/"),
    },
    "大兴区": {
        "北京亦庄实验中学": _school("http://www.bjeaedu.com/", "gh_63b555440ff4"),
        "北京市大兴区第七中学": _school("http://www.bjdxqz.cn/cms/"),
        "北京市大兴区第三中学": _school("http://www.dxqdszx.cn/cms/"),
    },
    "顺义区": {
        "牛栏山一中实验学校": _school("http://syxx.nlsyz.com.cn/", "gh_434358b22e4e"),
    },
    "通州区": {
        "首都师范大学附属中学通州校区": _school("http://www.cnuschool.org/tz/", "gh_4dab6e6f5bec"),
        "北京市通州区潞河中学": _school("https://www.luhe.cn/", "gh_7149f8b3d49d"),
        "人大附中通州校区": _school("http://www.rdfztzxq.cn/", "rtxchh"),
        "北京理工大学附属中学通州校区": _school("http://www.lgfztzschool.cn/", "gh_0a29a4c2d678"),
    },
    "石景山区": {
        "北京市第九中学分校": _school("http://fz.sjsedu.cn/", "bjjzjyjt"),
        "北京景山学校远洋分校": _school("http://jsyy.sjsedu.cn/", "bjjsyy2007"),
        "北京市京源学校": _school("http://jyxx.sjsedu.cn/", "jyxxedu"),
        "北大附中石景山学校": _school("http://bdfz.sjsedu.cn/"),
    },
}


DISTRICT_WECHATS = {
    "东城区": (("东教印象", "dcedunews"), ("东城区教育招生考试中心", "dckszx"), ("东城区教育工会", "gh_ba83f782a257")),
    "西城区": (("西城区教育考试中心", "gh_a45720a76f9a"),),
    "朝阳区": (("北京朝阳教育", "educhaoyang"),),
    "海淀区": (("海淀教育", "jybxwb"),),
    "丰台区": (("丰台教育", "ftjyxw"), ("丰台招生考试中心", "gh_cbba2ffc7b6b")),
    "石景山区": (("石景山教育", "bj-sjsjw"),),
    "门头沟区": (("门头沟教育", "mtgjy2014"),),
    "房山区": (("房山教育", "gh_1515f1b7b399"),),
    "通州区": (("通州区教委", "tongzhoujiaowei"),),
    "顺义区": (("顺义教委", "shunyijiaowei"), ("顺义区教育招生考试中心", "syjyzskszx")),
    "昌平区": (("昌平教育", "cpqjywyh"),),
    "大兴区": (("兴教时讯", "dxjyxcxjsx"),),
    "平谷区": (("平谷教育", "pinggujiaoyu"),),
    "怀柔区": (("怀柔教育", "huairoujiaoyu"),),
    "密云区": (("密云教育", "miyunjiaowei"),),
    "延庆区": (("延庆教育", "yanqingjiaoyu"),),
    "燕山地区": (("北京燕山教育", "beijingyanshanjiaoyu"),),
}


CITY_HOMEPAGES = {
    "北京市教委 · 通知公告": "https://jw.beijing.gov.cn/",
    "教育部 · 公告公示": "https://www.moe.gov.cn/",
    "全市学校信息": "https://jw.beijing.gov.cn/",
}

DISTRICT_HOMEPAGES = {
    "东城区": "https://www.bjdch.gov.cn/",
    "西城区": "https://www.bjxch.gov.cn/",
    "朝阳区": "https://www.bjchy.gov.cn/",
    "海淀区": "https://www.bjhdedu.cn/",
    "丰台区": "https://www.bjft.gov.cn/",
    "石景山区": "https://www.bjsjs.gov.cn/",
    "门头沟区": "https://www.bjmtg.gov.cn/",
    "房山区": "https://www.bjfsh.gov.cn/",
    "通州区": "https://www.bjtzh.gov.cn/",
    "顺义区": "https://www.bjshy.gov.cn/",
    "昌平区": "https://www.bjchp.gov.cn/",
    "大兴区": "https://www.bjdx.gov.cn/",
    "平谷区": "https://www.bjpg.gov.cn/",
    "怀柔区": "https://www.bjhr.gov.cn/",
    "密云区": "https://www.bjmy.gov.cn/",
    "延庆区": "https://www.bjyq.gov.cn/",
    "燕山地区": "https://www.bjfsh.gov.cn/",
    "经济技术开发区": "https://kfqgw.beijing.gov.cn/",
}


# 学校目录：先保证每个区有代表性学校入口；有稳定官网解析规则的学校
# 继续使用 SCHOOL_SPECS，太星目录只增加导航入口，不增加抓取任务。
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

for _district, _schools in TAIXING_SCHOOL_DIRECTORY.items():
    for _school_name in _schools:
        if _school_name not in SCHOOL_CATALOG[_district]:
            SCHOOL_CATALOG[_district].append(_school_name)

# 学校名点击入口。优先使用学校独立官网；没有稳定独立站的学校，使用
# 所属区政府/教委的官方学校目录或教育专题页，保证目录中的每所学校都有官方入口。
# 这些链接只用于导航，不参与新闻抓取，也不写入 RSS。
_DONGCHENG_SCHOOLS = "https://www.bjdch.gov.cn/zwgk/sjgk/sjxz/jyws/202303/t20230302_3030150.html"
_MENTOUGOU_SCHOOLS = "https://www.bjmtg.gov.cn/bjmtg/c103090/202212/98ad071c7593457fb0c202a9a0b7353d.shtml"
_FANGSHAN_EDU = "https://www.bjfsh.gov.cn/zhxw/bmdt/index.shtml"
_TONGZHOU_SCHOOLS = "https://www.bjtzh.gov.cn/bjtz/zwgk/tjsj/sjkf/2026052215435127308/index.shtml"
_SHUNYI_EDU = "https://www.bjshy.gov.cn/"
_CHANGPING_EDU = "https://www.bjchp.gov.cn/"
_DAXING_EDU = "https://www.bjdx.gov.cn/bjsdxqrmzf/zhyw/bmdt66/index.html"
_PINGGU_EDU = "https://www.bjpg.gov.cn/"
_HUAIROU_EDU = "https://www.bjhr.gov.cn/zjhr/bxsh/jykj/jyzx/"
_MIYUN_EDU = "https://www.bjmy.gov.cn/ywdt/gzdt/"
_YANQING_EDU = "https://www.bjyq.gov.cn/"
_YANSHAN_EDU = "https://www.bjfsh.gov.cn/zwgk/qmzqb/ghjh_2674/index_bm.shtml"
_BDA_EDU = "https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/"

# 这些地址是学校缺少独立官网时提供的官方导航入口，不是学校官网。
# 它们可以用于页面跳转，但不得交给学校爬虫，否则区政府综合信息会被误归到具体学校。
SCHOOL_NAVIGATION_FALLBACKS = {
    "北京市第二中学": _DONGCHENG_SCHOOLS,
    "北京市第五中学": _DONGCHENG_SCHOOLS,
    "北京市大峪中学": _MENTOUGOU_SCHOOLS,
    "北京市门头沟区实验中学": _MENTOUGOU_SCHOOLS,
    "首都师范大学附属中学永定分校": _MENTOUGOU_SCHOOLS,
    "北京市房山中学": _FANGSHAN_EDU,
    "北京市房山区良乡中学": _FANGSHAN_EDU,
    "北京学校": _TONGZHOU_SCHOOLS,
    "北京市昌平区实验学校": _CHANGPING_EDU,
    "北京市大兴区第一中学": _DAXING_EDU,
    "北京市大兴区兴华中学": _DAXING_EDU,
    "北京市平谷区第五中学": _PINGGU_EDU,
    "北京市平谷区马坊实验中学": _PINGGU_EDU,
    "北京市怀柔区第一中学": _HUAIROU_EDU,
    "北京市怀柔区第二中学": _HUAIROU_EDU,
    "北京市怀柔区第五中学": _HUAIROU_EDU,
    "北京市密云区第二中学": _MIYUN_EDU,
    "首都师范大学附属密云中学": _MIYUN_EDU,
    "北京师范大学密云实验中学": _MIYUN_EDU,
    "北京市延庆区第一中学": _YANQING_EDU,
    "北京市延庆区第二中学": _YANQING_EDU,
    "北京市延庆区第五中学": _YANQING_EDU,
    "北京市房山区燕山前进中学": _YANSHAN_EDU,
    "北京市房山区燕山向阳中学": _YANSHAN_EDU,
    "北京师范大学燕化附属中学": _YANSHAN_EDU,
    "北京市第二中学经开区学校": _BDA_EDU,
    "人大附中北京经济技术开发区学校": _BDA_EDU,
}

SCHOOL_HOMEPAGES = {
    # 东城
    "北京汇文中学": "http://www.pka.edu.cn/",
    # 西城
    "北京市第四中学": "https://bhsf.lezhiyun.com/",
    "北京市第八中学": "http://www.no8ms.bj.cn/",
    "北京市第十五中学": "http://www.bj15.cn/",
    "北师大附中": "https://www.bjsdfz.com/",
    # 朝阳
    "北京市第八十中学": "http://www.bj80.com/",
    "陈经纶中学": "http://www.bjcjl.net/",
    "北京中学": "https://www.beijingacademy.com.cn/",
    "朝阳外国语学校": "http://www.cyfls.net/",
    "日坛中学": "http://rtzx.bjchyedu.cn/",
    "工大附中": "http://www.bjgdfz.com/",
    # 海淀
    "人大附中": "https://www.rdfz.cn/",
    "清华附中": "https://www.qhfz.edu.cn/",
    "北京大学附属中学": "https://www.pkuschool.edu.cn/",
    "首师大附中": "https://www.cnuhs.cn/",
    "一零一中学": "https://www.beijing101.com/",
    "八一学校": "https://byxx.bjhdedu.cn/",
    "交大附中": "https://jdfz.bjhdedu.cn/",
    # 丰台
    "北京市第十二中学": "https://www2.bj12hs.com.cn/",
    "北京市第十八中学": "http://www.bj18.net/",
    "北京市丰台第二中学": "https://bjf2.ftedu.cn/ftez/",
    # 石景山
    "北京市第九中学": "http://9z.sjsedu.cn/",
    "北京市京源学校": "https://jyxx.sjsedu.cn/",
    "北京市十一学校石景山实验中学": "https://www.bndssjs.cn/",
    # 房山
    "首都师范大学附属中学房山学校": "https://www.cnuhs.cn/",
    # 通州
    "北京市通州区潞河中学": "https://www.luhe.cn/",
    "人大附中通州校区": "http://www.rdfztzxq.cn/",
    # 顺义
    "北京市顺义牛栏山第一中学": "http://www.nlsyz.com.cn/",
    "北京市顺义区第一中学": "https://bjsyyz.cn/",
    "北京市顺义区杨镇第一中学": "http://www.bjyzyz.net/",
    # 昌平
    "北京市昌平区第一中学": "http://www.cpyz.org.cn/",
    "北京市昌平区第二中学": "https://bjcpez.com.cn/",
    # 大兴
    "北京亦庄实验中学": "https://www.bjeaedu.com/",
    # 平谷
    "北京市平谷中学": "http://www.pgzx.net/",
}

SCHOOL_WECHATS = {}
for _schools in TAIXING_SCHOOL_DIRECTORY.values():
    for _school_name, _metadata in _schools.items():
        SCHOOL_HOMEPAGES[_school_name] = _metadata["homepage"]
        if _metadata["wechats"]:
            SCHOOL_WECHATS[_school_name] = _metadata["wechats"]

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


# 实时列表暂无匹配时，仅保留明确指向具体学校的官方条目。
SCHOOL_OFFICIAL_SEEDS = {
    "大兴区": {
        "北京亦庄实验中学": [_official_seed("北京亦庄实验中学2026年教育动态", "https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/202610/t20261009_4894513.html")],
    },
    "怀柔区": {
        "北京市怀柔区第一中学": [_official_seed("北京十一学校怀柔实验学校（怀柔一中）官方信息", "https://www.bjhr.gov.cn/zjhr/bxsh/jykj/jyzx/201911/t20191121_517308.html")],
        "北京市怀柔区第五中学": [_official_seed("怀柔五中入选人工智能应用场景标杆学校", "https://www.bjhr.gov.cn/zjhr/bxsh/jyzx/202602/t20260225_4539588.html")],
    },
    "密云区": {
        "北京市密云区第二中学": [_official_seed("密云二中2026年学校动态", "https://www.bjmy.gov.cn/zwgk/ztbd/xymy/xyxx/202609/t20260921_553091.html")],
    },
    "经济技术开发区": {
        "北京亦庄实验中学": [_official_seed("北京亦庄实验中学2026年教育动态", "https://kfqgw.beijing.gov.cn/zwgkkfq/zfxxgk/fdzdgknr/zdmsxx/jy/202610/t20261009_4894513.html")],
    },
}

# 不指向单一学校的名单、名录等信息按发布范围单独展示，避免误归入学校动态。
CITY_SCHOOL_INFO = [
    _official_seed(
        "北京市2026年具有招生资格的学校名单",
        "https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260519_4656965.html",
    ),
]

DISTRICT_SCHOOL_INFO = {
    "西城区": [_official_seed(
        "西城区学校地址及办学信息",
        "https://www.bjxch.gov.cn/xxgk/xxxq/pnidpv909665.html",
    )],
    "石景山区": [_official_seed(
        "石景山区2026年初中入学学校名单",
        "https://www.bjsjs.gov.cn/gongkai/zwgkpd/ztzl/2026/sjsywjyzl/xgfw/202605/t20260507_761565.shtml",
    )],
    "门头沟区": [_official_seed(
        "门头沟区初中学校官方名录",
        "https://www.bjmtg.gov.cn/bjmtg/c103090/202212/30bd097c14d04e30ad619a9eb9062521.shtml",
    )],
    "房山区": [_official_seed(
        "2026年房山区高考考点及学校信息",
        "https://www.bjfsh.gov.cn/zhxw/fsdt/202606/t20260605_40114417_fs.shtml",
    )],
    "通州区": [_official_seed(
        "通州区中小学官方信息及联系电话",
        "https://www.bjtzh.gov.cn/bjtz/zwgk/tjsj/sjkf/2026052215435127308/index.shtml",
    )],
    "大兴区": [_official_seed(
        "大兴区优质教育集团建设动态",
        "https://www.bjdx.gov.cn/bjsdxqrmzf/zhyw/bmdt66/2139180/index.html",
    )],
    "怀柔区": [_official_seed(
        "怀柔区2026年高中学校教育动态",
        "https://www.bjhr.gov.cn/zjhr/bxsh/jyzx/202609/t20260904_4850782.html",
    )],
    "密云区": [
        _official_seed(
            "密云区优质学校教育动态",
            "https://www.bjmy.gov.cn/ywdt/gzdt/202509/t20250911_511910.html",
        ),
        _official_seed(
            "密云区2026年高考考点学校信息",
            "https://www.bjmy.gov.cn/zwgk/hygq/202606/t20260603_543905.html",
        ),
    ],
    "经济技术开发区": [_official_seed(
        "经开区2026年教育领域学校信息",
        "https://kfqgw.beijing.gov.cn/zwgkkfq/tzgg/202608/t20260825_4836554.html",
    )],
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


_SCHOOL_ITEM_NOISE = re.compile(
    r"版权所有|copyright|ICP(?:备)?|公网安备|网站备案|"
    r"部门预算|部门决算|财务|审计|经费|政府采购|大宗食材采购|采购项目|"
    r"招标|比选|中标|成交公告|"
    r"^(?:义务教育入学|首页|学校首页|学校概况|学校简介|联系我们|友情链接|"
    r"通知公告|校园动态|新闻中心|招生信息)$",
    re.I,
)
_GENERIC_SCHOOL_INFO = re.compile(
    r"具有招生资格|学校名单|学校名录|地址及办学信息|官方信息及联系电话|"
    r"官方学校信息|学校官方信息$"
)
_NOISE_LINK = re.compile(r"javascript:|beian\.miit\.gov\.cn|beian\.mps\.gov\.cn", re.I)


def useful_school_item(item: dict) -> bool:
    """只保留具体学校内容，排除页脚、导航和共享学校目录。"""
    title = re.sub(r"\s+", " ", item.get("title", "")).strip()
    link = item.get("link", "")
    return not (
        _SCHOOL_ITEM_NOISE.search(title)
        or _GENERIC_SCHOOL_INFO.search(title)
        or _NOISE_LINK.search(link)
    )


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
        if useful_school_item(it):
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


def merge_crawl4ai_school_updates(schools: dict, updates_by_school: dict) -> None:
    """Merge normalized Crawl4AI school updates without creating placeholders."""
    for school, updates in updates_by_school.items():
        valid = []
        for update in updates or []:
            title = (update.get("title") or "").strip()
            link = (update.get("url") or update.get("link") or "").strip()
            if not title or not link or not link.startswith(("http://", "https://")):
                continue
            item = {
                "title": title,
                "link": link,
                "date": update.get("published_at", ""),
                "tag": tag_of(title),
                "kp": key_point(title),
                "src": "学校官网·Crawl4AI",
            }
            if useful_school_item(item):
                valid.append(item)
        if not valid:
            continue
        sections = schools.setdefault(school, {})
        sections.pop("学校信息", None)
        for item in valid:
            section_name = next(
                (u.get("category") for u in updates if u.get("url") == item["link"]),
                "学校动态",
            ) or "学校动态"
            current = sections.setdefault(section_name, [])
            seen = {existing.get("link") or existing.get("title") for existing in current}
            key = item["link"]
            if key not in seen:
                current.append(item)


def _load_school_crawler():
    """Load the optional Crawl4AI module both from CLI and test imports."""
    try:
        import school_crawler

        return school_crawler
    except ImportError:
        path = ROOT / "tools" / "school_crawler.py"
        spec = importlib.util.spec_from_file_location("school_crawler", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


async def _crawl4ai_batch(specs: list[dict]) -> list[dict]:
    crawler = _load_school_crawler()
    return await crawler.crawl_schools_updates(specs)


def collect_crawl4ai_school_updates() -> tuple[dict, list[dict]]:
    """Collect school updates without allowing Crawl4AI to break the build."""
    try:
        crawler = _load_school_crawler()
        specs = crawler.build_school_probe_specs(SCHOOL_CATALOG, SCHOOL_HOMEPAGES)
        reports = asyncio.run(_crawl4ai_batch(specs))
    except Exception as exc:
        return {}, [
            {
                "status": "failed",
                "error": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

    updates_by_district = {}
    health = []
    for report in reports:
        district = report.get("district", "")
        school = report.get("school", "")
        health.append({
            key: report.get(key)
            for key in (
                "school", "district", "homepage", "final_url", "status",
                "candidate_sections", "items_found", "error", "checked_at",
            )
            if key in report
        })
        if report.get("status") == "success" and district and school and report.get("updates"):
            updates_by_district.setdefault(district, {})[school] = report["updates"]
    return updates_by_district, health


def merge_school_seed_items(schools: dict, seeds: dict) -> None:
    """仅当学校没有真实动态时，补入已核验的官方信息条目。"""
    for school, items in seeds.items():
        items = [item for item in items if useful_school_item(item)]
        if not items:
            continue
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
<title>北京 K12 官方信源看板</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ font-variant-numeric: tabular-nums; scroll-behavior: smooth; }}
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
  .source-switcher {{ margin-left: 12px; color: #31586E; }}
  .source-switcher select {{ margin-left: 4px; padding: 3px 7px; border: 1px solid #B9B5AA;
    background: #FBFAF7; color: #212427; font-size: 12px; }}
  .community-notice {{ margin-top: 18px; padding: 10px 12px; border-left: 3px solid #B23B32;
    background: #F3F1EC; color: #6b6862; font-size: 12px; }}
  .community-meta {{ margin-top: 12px; color: #8a877e; font-size: 12px; }}
  .community-groups {{ margin-top: 12px; display: grid; grid-template-columns: 1fr; gap: 18px; }}
  .community-stage {{ border-top: 1px solid #212427; padding-top: 8px; }}
  .community-stage h3 {{ font-family: "Songti SC", "Noto Serif SC", serif; font-size: 17px;
    margin: 8px 0 2px; }}
  .community-type {{ margin-top: 12px; padding: 9px 12px 0; border-left: 2px solid #B9B5AA; }}
  .community-type h4 {{ font-size: 13px; font-weight: 600; margin-bottom: 2px; }}
  .community-item {{ padding: 9px 0; border-bottom: 1px solid #EDEBE3; }}
  .community-item a {{ color: #212427; text-decoration: none; font-size: 13px; }}
  .community-item a:hover {{ color: #31586E; text-decoration: underline; }}
  .community-item-meta {{ margin-top: 2px; color: #8a877e; font-size: 11px; }}
  .community-item-tags {{ margin-top: 3px; color: #31586E; font-size: 11px; }}
  [hidden] {{ display: none !important; }}

  /* ── 页面目录 ────────────────── */
  .page-directory {{ position: fixed;
    left: max(12px, calc((100vw - 1180px) / 2 - 132px)); top: 28px;
    width: 112px; max-height: calc(100vh - 56px); overflow-y: auto;
    padding: 9px 10px; border-left: 2px solid #B23B32;
    background: rgba(251, 250, 247, .96); z-index: 10; }}
  .page-directory strong {{ display: block; margin-bottom: 5px;
    font-family: "Songti SC", "Noto Serif SC", serif; font-size: 13px; }}
  .page-directory a {{ display: block; padding: 2px 0; color: #6b6862;
    font-size: 11px; text-decoration: none; white-space: nowrap; }}
  .page-directory a:hover, .page-directory a[aria-current="location"] {{
    color: #B23B32; font-weight: 600; }}
  @media (max-width: 1400px) {{
    .page-directory {{ position: sticky; left: auto; top: 0; width: 100%;
      max-height: none; margin-top: 10px; padding: 7px 0;
      display: flex; align-items: center; gap: 12px;
      border-left: 0; border-bottom: 1px solid #E3E1D8; overflow-x: auto; }}
    .page-directory strong {{ display: none; }}
    .page-directory a {{ flex: none; padding: 2px 0; }}
  }}

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
  .official-homepage {{ color: inherit; text-decoration: none; }}
  .official-homepage::after {{ content: " ↗"; font-size: 9px; color: #8a877e; }}
  .official-homepage:hover {{ color: #B23B32; text-decoration: underline;
    text-underline-offset: 3px; }}
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
  .school-homepage {{ color: #31586E; text-decoration: none; }}
  .school-homepage::after {{ content: " ↗"; font-size: 10px; color: #8a877e; }}
  .school-homepage:hover {{ color: #B23B32; text-decoration: underline;
    text-underline-offset: 3px; }}
  .school-wechat {{ display: block; margin-top: 2px; color: #8a877e;
    font-size: 11px; font-weight: 400; }}
  .school-wechat code, .district-wechat code {{ font-family: ui-monospace, SFMono-Regular,
    Menlo, Consolas, monospace; font-size: 10.5px; color: #6b6862; }}
  .school-entry {{ padding: 5px 0 7px; border-bottom: 1px solid #EDEBE3; }}
  .district-wechat {{ margin: 5px 0 10px; color: #8a877e; font-size: 11px;
    line-height: 1.8; }}
  .district-wechat b {{ color: #31586E; font-weight: 600; margin-right: 5px; }}
  .open-hint {{ font-size: 11px; color: #a5a29a; padding: 2px 2px 0; }}

  footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #E3E1D8;
    font-size: 12px; color: #a5a29a; line-height: 1.9; }}
</style>
</head>
<body>
<div class="page">
<header>
  <h1>北京 K12 · 官方信源看板</h1>
  <div class="meta">构建于 {built_at}，每 6 小时自动更新
    <label class="source-switcher">信源视图
      <select id="source-view" aria-label="选择信源视图">
        <option value="official">官方信源看板</option>
        <option value="community">社区信源看板</option>
      </select>
    </label>
  </div>
</header>

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


def school_homepage_link(school_name: str) -> str:
    """仅在确认有学校官网时渲染链接；区级目录不冒充学校官网。"""
    url = SCHOOL_HOMEPAGES.get(school_name)
    if not url:
        return school_name
    return (
        f'<a class="school-homepage" href="{url}" target="_blank" rel="noopener" '
        f'title="打开学校官方入口">{school_name}</a>'
    )


def school_identity(school_name: str) -> str:
    """学校官网入口及来源页列出的微信公众号。"""
    identity = school_homepage_link(school_name)
    wechats = SCHOOL_WECHATS.get(school_name, ())
    if not wechats:
        return identity
    ids = " · ".join(f"<code>{wechat}</code>" for wechat in wechats)
    return f'{identity}<span class="school-wechat">微信公众号：{ids}</span>'


def district_wechat_note(district_name: str) -> str:
    accounts = DISTRICT_WECHATS.get(district_name, ())
    if not accounts:
        return ""
    labels = " · ".join(f'{name} <code>{wechat}</code>' for name, wechat in accounts)
    return f'<div class="district-wechat"><b>官方公众号</b>{labels}</div>'


def official_homepage_link(label: str, url: str) -> str:
    return (
        f'<a class="official-homepage" href="{url}" target="_blank" '
        f'rel="noopener">{label}</a>'
    )


def _read_json_file(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def community_view(community_data: dict, community_status: dict = None) -> str:
    records = community_data.get("records", []) if community_data.get("status") == "success" else []
    status = community_status or community_data
    generated_at = escape(str(community_data.get("generated_at") or status.get("generated_at") or "未知"))
    if not records:
        return (
            '<section id="community-view" hidden><h2>社区信源</h2>'
            '<p class="community-notice">社区内容仅用于发现线索和观察家长反馈，未经官方核验，不等同于官方信息。</p>'
            '<p class="community-meta">社区数据暂不可用；官方信源看板不受影响。</p></section>'
        )
    phase_order = ("小学", "中学", "高中", "其他阶段")
    stage_to_phase = {
        "幼升小": "小学",
        "小升初": "小学",
        "中招": "小学",
        "中考": "中学",
        "初升高": "中学",
        "高中": "高中",
        "高考": "高中",
    }
    type_order = ("政策与流程", "学校动态", "家长经验", "其他类型")
    groups = {phase: {content_type: [] for content_type in type_order} for phase in phase_order}
    for record in records:
        stages = record.get("stage") or ["其他阶段"]
        if isinstance(stages, str):
            stages = [stages]
        content_type = record.get("content_type") or "其他类型"
        if content_type not in type_order:
            content_type = "其他类型"
        for stage in stages:
            stage_text = str(stage)
            phase = stage_to_phase.get(stage_text)
            if phase is None:
                if "高考" in stage_text or "高中" in stage_text or "高职" in stage_text:
                    phase = "高中"
                elif "中考" in stage_text or "初升高" in stage_text:
                    phase = "中学"
                elif "幼升小" in stage_text or "小升初" in stage_text or "中招" in stage_text:
                    phase = "小学"
                else:
                    phase = "其他阶段"
            groups[phase][content_type].append((record, stage))

    phase_html = []
    for phase in phase_order:
        type_html = []
        for content_type in type_order:
            items = groups[phase][content_type]
            if not items:
                continue
            rows = []
            for item, stage in items:
                link = escape(str(item.get("link") or ""), quote=True)
                title = escape(str(item.get("title") or "无标题"))
                date = escape(str(item.get("published_at") or "日期未知"))
                source = escape(str(item.get("source") or "未标注社区"))
                events = item.get("event_type") or []
                if isinstance(events, str):
                    events = [events]
                event_label = "、".join(str(value) for value in events) or "无"
                districts = item.get("district_candidates") or []
                if isinstance(districts, str):
                    districts = [districts]
                district_label = "、".join(str(value) for value in districts) or "—"
                rows.append(
                    f'<article class="community-item"><a href="{link}" target="_blank" rel="noopener">{title}</a>'
                    f'<div class="community-item-meta">来源：{source} · {date} · 待官方核验</div>'
                    f'<div class="community-item-tags">学段标签：{escape(str(stage))} · 事件标签：{escape(event_label)} · 区县：{escape(district_label)}</div></article>'
                )
            type_html.append(
                f'<section class="community-type"><h4>{escape(content_type)} · {len(items)} 条</h4>{"".join(rows)}</section>'
            )
        if type_html:
            total = sum(len(groups[phase][content_type]) for content_type in type_order)
            phase_html.append(
                f'<section class="community-stage"><h3>{escape(phase)} · {total} 条</h3>{"".join(type_html)}</section>'
            )
    return (
        '<section id="community-view" hidden><h2>社区信源</h2>'
        '<p class="community-notice">社区内容仅用于发现线索和观察家长反馈，未经教育部门、考试院或学校官方页面核验，不等同于官方信息。</p>'
        f'<p class="community-meta">最近成功采集：{generated_at} · 当前展示：{len(records)} 条</p>'
        f'<div class="community-groups">{"".join(phase_html)}</div></section>'
    )


def build_page(data: dict, prev_keys: set, built_at: str, community_data: dict = None, community_status: dict = None) -> str:
    jw, moe = data["市教委"], data["教育部"]
    city_school_info = data.get("市级学校信息", [])

    parts = [HTML_HEAD.format(built_at=built_at)]

    directory_links = ['<a href="#city">市级</a>']
    directory_links.extend(
        f'<a href="#district-{index:02d}">{district}</a>'
        for index, district in enumerate(DISTRICTS, start=1)
    )
    parts.append(
        '<nav class="page-directory" aria-label="页面目录">'
        '<strong>快速跳转</strong>'
        + "".join(directory_links)
        + "</nav>"
    )
    parts.append('<div id="official-view">')

    # 市级头条
    parts.append('<h2 id="city">市级</h2><div class="city">')
    for name, items in (
        ("北京市教委 · 通知公告", jw),
        ("教育部 · 公告公示", moe),
        ("全市学校信息", city_school_info),
    ):
        name_link = official_homepage_link(name, CITY_HOMEPAGES[name])
        if items:
            top = items[0]
            top_new = '<span class="n-new">NEW</span>' if top["link"] not in prev_keys else ""
            parts.append(
                f'<div><h3>{name_link} · {len(items)} 条</h3>'
                f'<div class="headline">{top_new}<a href="{top["link"]}" target="_blank">{top["title"]}</a></div>'
                f'<ul>{"".join(item_li(it, prev_keys) for it in items[1:6])}</ul></div>'
            )
        else:
            parts.append(f'<div><h3>{name_link}</h3><ul><li class="empty">拉取失败</li></ul></div>')
    parts.append("</div>")
    parts.append("</div>")
    parts.append(community_view(community_data or {}, community_status))

    # 区台账
    parts.append('<h2>分区台账</h2><div class="ledger">')
    for district_index, (区名, fid) in enumerate(DISTRICTS.items(), start=1):
        d = data["区级"][区名]
        policies = d["政策"]
        gov = d["动态"]
        general = d.get("通用信息", [])
        schools = d["学校"]
        n_new = sum(1 for it in policies if (it.get("id") or it.get("link")) not in prev_keys)
        latest = policies[0]["title"] if policies else "（无数据）"
        school_label = f"{len(schools)} 校" if schools else ""
        new_badge = f'<span class="n-new">{n_new} 新</span>' if n_new else ""
        official_sections = section("区招生政策", policies, prev_keys, max_show=4)
        if gov:
            name, items = gov
            official_sections += section(f"{name} · 教育动态", items, prev_keys, max_show=4)
        if general:
            official_sections += section("区级学校信息", general, prev_keys, max_show=4)
        school_sections = ""
        for 校名, 栏目 in schools.items():
            校名入口 = school_identity(校名)
            if not 栏目:
                school_sections += f'<div class="school-sec school-entry"><h4>{校名入口}</h4></div>'
                continue
            for 栏名, items in 栏目.items():
                school_sections += section(f"{校名入口} · {栏名}", items, prev_keys, max_show=4)
        if not school_sections:
            school_sections = '<p class="column-empty">暂无学校动态</p>'

        parts.append(
            f'<details id="district-{district_index:02d}" class="row"'
            f'{" open" if (schools or n_new) else ""}><summary>'
            f'<span class="d-name">{official_homepage_link(区名, DISTRICT_HOMEPAGES[区名])}</span>'
            f'<span class="d-count">{len(policies)} 条</span>'
            f'<span class="d-latest">{latest}</span>'
            f'<span class="d-side">{new_badge}{school_label}</span>'
            f"</summary>"
            f'<div class="row-body"><div class="district-columns">'
            f'<section class="district-column district-column--official">'
            f'<h3 class="column-title">区级信息</h3>{district_wechat_note(区名)}{official_sections}</section>'
            f'<section class="district-column district-column--schools">'
            f'<h3 class="column-title">学校入口与动态</h3>{school_sections}</section>'
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
        + "<br>仅已确认的学校官网提供点击与动态抓取；没有独立官网的学校只显示名称。"
        + "微信公众号 ID 仅作人工检索入口，不作为自动抓取源。</footer>"
    )
    parts.append("""<script>
  (() => {
    const selector = document.getElementById('source-view');
    const officialView = document.getElementById('official-view');
    const communityView = document.getElementById('community-view');
    const setSourceView = view => {
      const community = view === 'community';
      officialView.hidden = community;
      communityView.hidden = !community;
      selector.value = community ? 'community' : 'official';
      const url = new URL(window.location.href);
      url.searchParams.set('view', community ? 'community' : 'official');
      window.history.replaceState({}, '', url);
    };
    selector.addEventListener('change', event => setSourceView(event.target.value));
    setSourceView(new URLSearchParams(window.location.search).get('view') || 'official');
  })();
  (() => {
    const links = [...document.querySelectorAll('.page-directory a')];
    const targets = links.map(link => document.querySelector(link.getAttribute('href'))).filter(Boolean);
    const activate = id => links.forEach(link => {
      if (link.getAttribute('href') === `#${id}`) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
    if (targets.length && 'IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => {
        const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) activate(visible.target.id);
      }, { rootMargin: '-15% 0px -70% 0px', threshold: [0, .1, .5] });
      targets.forEach(target => observer.observe(target));
    }
    links.forEach(link => link.addEventListener('click', () => activate(link.hash.slice(1))));
    activate(location.hash.slice(1) || 'city');
  })();
</script>""")
    return "".join(parts) + "</div></body></html>"


def build_feed(data: dict, built_at: str) -> str:
    """生成 OPML 使用的增量 RSS；排除已有独立订阅的市级通知和区招生政策。"""
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "K12 官方信源看板 · 区教委与学校动态"
    ET.SubElement(channel, "link").text = "https://xian492.github.io/k12-dashboard/"
    ET.SubElement(channel, "description").text = "北京各区教委、学校动态及市区学校综合信息"
    ET.SubElement(channel, "language").text = "zh-cn"
    built_dt = datetime.strptime(built_at, "%Y-%m-%d %H:%M").replace(
        tzinfo=timezone(timedelta(hours=8))
    )
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(built_dt)

    scoped_items = [("全市学校信息", data.get("市级学校信息", []))]
    for district_name, district in data.get("区级", {}).items():
        if district.get("动态"):
            source_name, items = district["动态"]
            scoped_items.append((f"{district_name} · {source_name}", items))
        scoped_items.append((f"{district_name} · 区级学校信息", district.get("通用信息", [])))
        for school_name, sections in district.get("学校", {}).items():
            for section_name, items in sections.items():
                scoped_items.append((f"{school_name} · {section_name}", items))

    seen = set()
    for category, items in scoped_items:
        for source_item in items:
            link = source_item.get("link", "")
            if not link or link in seen:
                continue
            seen.add(link)
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = source_item.get("title", "")
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = link
            ET.SubElement(item, "category").text = category

    ET.indent(rss, space="  ")
    return ET.tostring(rss, encoding="unicode", xml_declaration=True)


def main():
    built_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    prev_keys = load_prev_keys()
    crawl_updates, crawl_health = collect_crawl4ai_school_updates()

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
        学校 = {校名: {} for 校名 in SCHOOL_CATALOG.get(区名, [])}
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
        merge_crawl4ai_school_updates(学校, crawl_updates.get(区名, {}))
        merge_school_seed_items(学校, SCHOOL_OFFICIAL_SEEDS.get(区名, {}))
        区级[区名] = {
            "政策": 政策,
            "动态": 动态,
            "通用信息": DISTRICT_SCHOOL_INFO.get(区名, []),
            "学校": 学校,
        }

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
        "市级学校信息": CITY_SCHOOL_INFO,
        "学校官网健康": crawl_health,
        "区级": 区级,
    }
    community_data = _read_json_file(DOCS / "community-data.json")
    community_status = _read_json_file(DOCS / "community-status.json")

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(
        json.dumps({"built_at": built_at, "data": data}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOCS / "index.html").write_text(
        build_page(data, prev_keys, built_at, community_data, community_status),
        encoding="utf-8",
    )
    (DOCS / "feed.xml").write_text(build_feed(data, built_at), encoding="utf-8")
    (DOCS / "school-crawler-health.json").write_text(
        json.dumps(crawl_health, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    d_online = sum(1 for d in 区级.values() if d["政策"])
    g_online = sum(1 for d in 区级.values() if d["动态"])
    print(
        f"built: {built_at} | 市教委 {len(data['市教委'])} | 教育部 {len(data['教育部'])} | "
        f"区在线 {d_online}/18 | 区教委 {g_online} | 学校 {sum(len(d['学校']) for d in 区级.values())} 所"
    )


if __name__ == "__main__":
    main()
