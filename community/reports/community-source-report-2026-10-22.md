# 社区信源一次性巡检报告

> 生成时间：2026-10-22 17:04:29 +0800。本报告对《community/sources/论坛与社区信源.md》中的公开入口各抓取一次，重点判断入口是否可访问、页面是否有可读内容、是否暴露内部链接，以及后续是否值得继续做分页和详情页抓取。

## 一、结论摘要

本次共检查 **38** 个去重入口，其中 **32 个（84.2%）可以继续抓取**，**1 个（2.6%）受到访问限制**，**5 个（13.2%）请求失败**。

> 注意：入口巡检成功不等于内容质量已验证，也不等于已经抓完该社区的全部历史帖子、分页和回复。

### 主要判断

- **可继续深挖**：有正文或内部链接的入口共 32 个；其中内部链接较多的来源适合优先配置分页和详情页抓取。
- **需要专用解析**：有 2 个入口虽然返回成功，但链接很少或页面更像结构化导航，不能直接套用论坛列表解析。
- **访问受限**：有 1 个入口触发反爬、验证码、登录或页面内容不足提示。
- **请求失败**：有 5 个入口发生超时或浏览器导航错误，需要单独复查网络和站点状态。

## 二、结果分组

### 优先继续抓取的入口

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 适合的下一步 |
|---|---|---|---:|---:|---|
| 家在深圳 / 学龄教育 | [https://bbs.szhome.com/580030.html](https://bbs.szhome.com/580030.html) | 成功 | 40851 | 621 | 配置分页和帖子详情页抓取 |
| 得意生活 / 教育板块 | [https://www.deyi.com/forum-79-1.html](https://www.deyi.com/forum-79-1.html) | 成功 | 44590 | 394 | 配置分页和帖子详情页抓取 |
| 千帆育儿 / 小学教育 | [https://www.qianfanedu.cn/forum-2-7.html](https://www.qianfanedu.cn/forum-2-7.html) | 成功 | 45694 | 333 | 配置分页和帖子详情页抓取 |
| 千帆育儿 / 中学教育 | [https://qianfanedu.cn/forum.php?fid=36&filter=typeid&mobile=no&mod=forumdisplay&typeid=13](https://qianfanedu.cn/forum.php?fid=36&filter=typeid&mobile=no&mod=forumdisplay&typeid=13) | 成功 | 44393 | 314 | 配置分页和帖子详情页抓取 |
| 妈妈网 / 全国问答 | [https://www.mama.cn/ask/](https://www.mama.cn/ask/) | 成功 | 30886 | 261 | 配置分页和帖子详情页抓取 |
| 綦江在线 / 教育板块 | [https://www.qj023.com/forum-164-2.html](https://www.qj023.com/forum-164-2.html) | 成功 | 30310 | 195 | 配置分页和帖子详情页抓取 |
| 苏州通论坛 / 首页 | [https://www.suzhoutong.cc/](https://www.suzhoutong.cc/) | 成功 | 38490 | 175 | 配置分页和帖子详情页抓取 |
| 江阴论坛 / 招生讨论 | [https://bbs.jysq.net/thread-14100935-1-1.html](https://bbs.jysq.net/thread-14100935-1-1.html) | 成功 | 34521 | 175 | 配置分页和帖子详情页抓取 |

### 需要专用解析的入口

| 社区/名称 | 原始链接 | 页面特征 | 建议 |
|---|---|---|---|
| 北京小升初网 / 家长社群 | [https://www.xschu.com/zt/shequn/](https://www.xschu.com/zt/shequn/) | 116 字符、0 个内部链接 | 解析页面内嵌数据或正文结构 |
| 北京小升初升学索引 / 首页 | [https://xiaoshengchu.org/](https://xiaoshengchu.org/) | 6789 字符、0 个内部链接 | 解析页面内嵌数据或正文结构 |

### 受限或失败的入口

| 社区/名称 | 原始链接 | 状态 | 原因 |
|---|---|---|---|
| 百度贴吧 / 贴吧首页 | [https://tieba.baidu.com/](https://tieba.baidu.com/) | 受限/反爬 | Blocked by anti-bot protection: HTTP 403 with HTML content (2572 bytes) |
| 学鹿教育社区 / 首页 | [https://www.xuelu.co/](https://www.xuelu.co/) | 请求失败 | Blocked by anti-bot protection: Structural: minimal_text on small page (137 bytes, 19 chars visible) |
| 旺旺网 / 初中与小升初择校 | [https://ww123.net/forumdisplay.php?fid=36](https://ww123.net/forumdisplay.php?fid=36) | 请求失败 | Unexpected error in _crawl_web at line 779 in _crawl_web (.venv/lib/python3.12/site-packages/crawl4ai/async_crawler_strategy.py): Error: Failed on navigating ACS-GOTO: Page.goto: Timeout 60000ms exceeded. Call log:   - navigating to "https: |
| 深圳妈妈网 / 学龄教育 | [https://m.szmama.com/forum-506-1.html](https://m.szmama.com/forum-506-1.html) | 请求失败 | Blocked by anti-bot protection: Structural: no_content_elements on small page (147 bytes, 108 chars visible) |
| 沈阳 e 度论坛 / 论坛介绍 | [https://sy.zhongkao.com/e/20121130/50b85f6b7d5da.shtml](https://sy.zhongkao.com/e/20121130/50b85f6b7d5da.shtml) | 请求失败 | Blocked by anti-bot protection: Structural: minimal_text on small page (160 bytes, 19 chars visible) |
| 西安 e 度论坛 / 论坛介绍 | [https://xa.zhongkao.com/e/20130225/512adab084bfb.shtml](https://xa.zhongkao.com/e/20130225/512adab084bfb.shtml) | 请求失败 | Blocked by anti-bot protection: Structural: minimal_text on small page (160 bytes, 19 chars visible) |

### 状态定义

| 状态 | 含义 |
|---|---|
| success | 入口成功返回可见内容或内部链接 |
| empty | 请求成功但没有可提取正文和内部链接 |
| blocked | 命中反爬、验证码、登录或访问拒绝提示 |
| failed | 请求或浏览器执行失败 |

## 三、来源明细

以下按原信源文档的章节归类。每行同时保留社区名称、页面名称和可点击的原始链接，便于直接回到社区页面。

### 二、全国性入口

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 家长之家 / 首页 | [https://www.parentshome.cn/](https://www.parentshome.cn/) | 成功 | 9689 | 65 | 1.29s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 家长之家 / 发现 | [https://www.parentshome.cn/explore/](https://www.parentshome.cn/explore/) | 成功 | 9768 | 63 | 1.33s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 家长之家 / 问题列表 | [https://www.parentshome.cn/questions/recommend-32.html](https://www.parentshome.cn/questions/recommend-32.html) | 成功 | 12012 | 78 | 1.23s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 百度贴吧 / 贴吧首页 | [https://tieba.baidu.com/](https://tieba.baidu.com/) | 受限/反爬 | 1 | 0 | 0.37s | Blocked by anti-bot protection: HTTP 403 with HTML content (2572 bytes) |
| 知乎 / 话题入口 | [https://www.zhihu.com/topic](https://www.zhihu.com/topic) | 成功 | 1260 | 13 | 2.91s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 伴苗家长论坛 / 首页 | [https://www.kebanapp.com/](https://www.kebanapp.com/) | 成功 | 2832 | 3 | 2.57s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 学鹿教育社区 / 首页 | [https://www.xuelu.co/](https://www.xuelu.co/) | 请求失败 | 28 | 0 | 1.68s | Blocked by anti-bot protection: Structural: minimal_text on small page (137 bytes, 19 chars visible) |
| 妈妈网 / 全国问答 | [https://www.mama.cn/ask/](https://www.mama.cn/ask/) | 成功 | 30886 | 261 | 3.57s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

### 三、地方论坛与城市社区 / 北京

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 北京小升初网 / 政策资讯 | [https://www.xschu.com/zhengcezixun/](https://www.xschu.com/zhengcezixun/) | 成功 | 19449 | 83 | 5.86s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 北京小升初网 / 家长经验 | [https://www.xschu.com/jiachang](https://www.xschu.com/jiachang) | 成功 | 5703 | 13 | 5.78s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 北京小升初网 / 家长社群 | [https://www.xschu.com/zt/shequn/](https://www.xschu.com/zt/shequn/) | 成功 | 116 | 0 | 5.01s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 水木社区 / 儿童教育版 | [https://www.newsmth.net/nForum/board/ChildEducation](https://www.newsmth.net/nForum/board/ChildEducation) | 成功 | 2222 | 23 | 4.43s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 北京小升初信息网 / 北京小升初 | [https://www.xscxx.com/xiaoshengchu/](https://www.xscxx.com/xiaoshengchu/) | 成功 | 12658 | 115 | 5.20s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 北京小升初信息网 / 中学招生 | [https://www.xscxx.com/chuzhong/zhaosheng/](https://www.xscxx.com/chuzhong/zhaosheng/) | 成功 | 8645 | 68 | 5.60s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 邻友圈 / 公开帖子示例 | [https://api.linyouquan.net/v1/threads/6a3b7f8ad0f8df110a668702](https://api.linyouquan.net/v1/threads/6a3b7f8ad0f8df110a668702) | 成功 | 4084 | 11 | 6.29s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 回龙观社区网 / 文化讨论区 | [https://bbs.hlgnet.com/frame.php?bbscate=0&boardid=1](https://bbs.hlgnet.com/frame.php?bbscate=0&boardid=1) | 成功 | 27103 | 136 | 6.75s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 芍药居社区网 / 入学政策版 | [https://www.shaoyaojuwang.com/forum-6-1.html](https://www.shaoyaojuwang.com/forum-6-1.html) | 成功 | 19606 | 97 | 6.47s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 北京小升初升学索引 / 首页 | [https://xiaoshengchu.org/](https://xiaoshengchu.org/) | 成功 | 6789 | 0 | 10.64s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 北京小升初网 / 平台入口页 | [https://www.xschu.com/qhy/wordBox/xsc.html](https://www.xschu.com/qhy/wordBox/xsc.html) | 成功 | 9942 | 13 | 6.64s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 水木社区 / 学区房板 | [https://www.newsmth.net/nForum/board/SchoolEstate](https://www.newsmth.net/nForum/board/SchoolEstate) | 成功 | 17008 | 107 | 6.98s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

### 三、地方论坛与城市社区 / 上海

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 千帆育儿 / 首页 | [https://www.qianfanedu.cn/](https://www.qianfanedu.cn/) | 成功 | 15590 | 103 | 7.25s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 千帆育儿 / 小学教育 | [https://www.qianfanedu.cn/forum-2-7.html](https://www.qianfanedu.cn/forum-2-7.html) | 成功 | 45694 | 333 | 7.36s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 千帆育儿 / 中学教育 | [https://qianfanedu.cn/forum.php?fid=36&filter=typeid&mobile=no&mod=forumdisplay&typeid=13](https://qianfanedu.cn/forum.php?fid=36&filter=typeid&mobile=no&mod=forumdisplay&typeid=13) | 成功 | 44393 | 314 | 7.80s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 旺旺网 / 初中与小升初择校 | [https://ww123.net/forumdisplay.php?fid=36](https://ww123.net/forumdisplay.php?fid=36) | 请求失败 | 0 | 0 | 67.30s | Unexpected error in _crawl_web at line 779 in _crawl_web (.venv/lib/python3.12/site-packages/crawl4ai/async_crawler_strategy.py): Error: Failed on navigating AC |

### 三、地方论坛与城市社区 / 广州与广东

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 广州妈妈网 / 家有小学生 | [https://www.gzmama.com/forum-42-1.html](https://www.gzmama.com/forum-42-1.html) | 成功 | 2513 | 36 | 8.72s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 家在深圳 / 学龄教育 | [https://bbs.szhome.com/580030.html](https://bbs.szhome.com/580030.html) | 成功 | 40851 | 621 | 8.95s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 深圳妈妈网 / 学龄教育 | [https://m.szmama.com/forum-506-1.html](https://m.szmama.com/forum-506-1.html) | 请求失败 | 109 | 0 | 9.49s | Blocked by anti-bot protection: Structural: no_content_elements on small page (147 bytes, 108 chars visible) |

### 三、地方论坛与城市社区 / 成都与四川

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 壹牛家长圈 / 首页 | [https://www.16jzq.com/](https://www.16jzq.com/) | 成功 | 25232 | 153 | 53.70s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 我考网 / 首页 | [https://wokaowang.com/](https://wokaowang.com/) | 成功 | 12552 | 48 | 10.92s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

### 三、地方论坛与城市社区 / 武汉与湖北

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 得意生活 / 教育板块 | [https://www.deyi.com/forum-79-1.html](https://www.deyi.com/forum-79-1.html) | 成功 | 44590 | 394 | 52.98s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 悦来教育 / 首页 | [https://www.wuhanyuelai.com/](https://www.wuhanyuelai.com/) | 成功 | 11487 | 80 | 14.72s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

### 三、地方论坛与城市社区 / 杭州与浙江

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 杭州19楼 / 中学教育论坛 | [https://www.19lou.com/theme-thread-15-36938-1](https://www.19lou.com/theme-thread-15-36938-1) | 成功 | 15852 | 104 | 15.55s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

### 三、地方论坛与城市社区 / 重庆

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 重庆妈妈网 / 重庆初升高话题 | [https://go.cqmmgo.com/newtag-thread-782852-1](https://go.cqmmgo.com/newtag-thread-782852-1) | 成功 | 8223 | 36 | 16.24s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

### 三、地方论坛与城市社区 / 苏州与江苏

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 苏州通论坛 / 首页 | [https://www.suzhoutong.cc/](https://www.suzhoutong.cc/) | 成功 | 38490 | 175 | 40.07s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

### 三、地方论坛与城市社区 / 南京、西安、沈阳、天津、郑州、长沙、济南与青岛

| 社区/名称 | 原始链接 | 状态 | 页面字符数 | 内部链接 | 抓取耗时 | 说明 |
|---|---|---|---:|---:|---:|---|
| 沈阳 e 度论坛 / 论坛介绍 | [https://sy.zhongkao.com/e/20121130/50b85f6b7d5da.shtml](https://sy.zhongkao.com/e/20121130/50b85f6b7d5da.shtml) | 请求失败 | 28 | 0 | 40.38s | Blocked by anti-bot protection: Structural: minimal_text on small page (160 bytes, 19 chars visible) |
| 西安 e 度论坛 / 论坛介绍 | [https://xa.zhongkao.com/e/20130225/512adab084bfb.shtml](https://xa.zhongkao.com/e/20130225/512adab084bfb.shtml) | 请求失败 | 28 | 0 | 40.65s | Blocked by anti-bot protection: Structural: minimal_text on small page (160 bytes, 19 chars visible) |
| 江阴论坛 / 招生讨论 | [https://bbs.jysq.net/thread-14100935-1-1.html](https://bbs.jysq.net/thread-14100935-1-1.html) | 成功 | 34521 | 175 | 41.34s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |
| 綦江在线 / 教育板块 | [https://www.qj023.com/forum-164-2.html](https://www.qj023.com/forum-164-2.html) | 成功 | 30310 | 195 | 42.29s | 入口有可见正文或内部链接，可继续做分页/详情页抓取。 |

## 四、后续建议

1. 先对“优先继续抓取”的入口增加分页和详情页抓取，形成统一的帖子记录。
2. 对水木社区、升学索引等结构特殊的来源单独编写解析器，不用通用论坛规则硬套。
3. 对受限来源保留人工入口，不尝试绕过验证码、登录或反爬。
4. 对成功入口增加发布时间、标题、正文、作者、回复数和原始链接字段，再进行去重和增量更新。

## 五、范围说明

本次只巡检文档中明确列出的公开入口，不自动登录、不绕过验证码、不抓取私密群组，也没有递归抓取每个入口下的全部分页和文章详情。
