# 研究笔记：多源信息的可信度评级、交叉验证与时效性标注

> 调研日期：2026-10-23。调研方法：一手来源优先（论文 DOI/arXiv 原文、项目源码仓库、官方文档页面），全部经网络实际访问核验；二手来源明确标注。本笔记服务于“我给你搜到了 xxx 条信息，每条来源是哪、置信度多少、是否过期”这一用户可见功能的设计。

---

## 1. 问题定义

本项目是北京 K12 招生信息聚合看板：Python 构建脚本每 6 小时拉取多源数据，产出静态站。信源横跨四个权威层级：

| 层级 | 信源 | 特点 |
| --- | --- | --- |
| L0 市级官方 | 市教委、教育部 | 权威但覆盖粗粒度 |
| L1 区级官方 | 各区教委门户 | 政策的一手发布方 |
| L2 半官方结构化 | 义务教育入学服务平台 yjrx（官方 JSON） | 结构化、可靠，但语义有限 |
| L3 学校自有渠道 | 学校官网静态 HTML、统一建站平台（bjhdedu.cn / bjchyedu.cn 等） | 官方性参差，页面质量低 |
| L4 社区 | 家长论坛（community/ 目录 pipeline） | 有独家情报但过期/错误率高 |

要回答的三个研究问题，对应三个成熟研究方向：

1. **来源可信度评级**（source credibility ranking）：不同来源的默认信任权重怎么定、定几分。
2. **交叉验证 / 佐证**（corroboration / fact-checking）：同一事件被多源报道时，如何判断“独立佐证”还是“互相转载”，如何呈现一致性。
3. **时效性**（temporal validity / freshness）：招生政策有强年度周期（4–7 月集中发布），去年的政策今年不适用；如何计算与展示信息的“过期程度”。

加一个问题：**置信度如何展示才不误导**（uncertainty communication）。

---

## 2. 方向一：来源可信度评级

### 2.1 工业界的来源评级体系

**NewsGuard（商业，方法论最完整）**。对每个新闻站按 9 条准则打 0–100 分：可信度类（不发布虚假内容 22 分、负责任地收集信息 18 分、有纠错机制 12.5 分、区分新闻与观点 12.5 分、不误导标题 10 分）+ 透明度类（披露所有权与资金 7.5 分、标注广告 7.5 分、公开负责人 5 分、署名与联系渠道 5 分）。每份评级配一张 “Nutrition Label”（营养标签）卡片，写明每条判定的证据。评分分档：100 高可信、75–99 总体可信、60–74 可信但有重大例外、40–59 不可靠、0–39 严重不可靠。来源：[Rating Process & Criteria（官方页面，已核验）](https://www.newsguardtech.com/ratings/rating-process-criteria/)。

**Ad Fontes Media（商业）**。可靠性、偏见两个独立维度；每篇文章由至少三名政治立场平衡（左/中/右）的分析师实时同步评分，分歧大则换第二个平衡小组重评；来源分数是文章分数的加权平均，抽样取同一时刻各来源首页文章以评估“选题性偏见”。来源：[Methodology（官方页面，已核验）](https://adfontesmedia.com/methodology/)。

**Media Bias/Fact Check（免费网站，事实性评分可借鉴）**。2025 年起新方法论：事实性 0–10 分 = 失败事实核查记录（40%）+ 引用质量（25%）+ 透明度（25%，含所有权、资金、作者、使命、地点五要素）+ 片面性（10%）；另有独立于事实性的“可信度”10 分制（事实性 0–4 + 偏见等级 0–3 + 流量与存续年限 0–3）。人工评审至少 10 条标题 + 5 篇全文。来源：[Methodology（官方页面，已核验）](https://mediabiasfactcheck.com/methodology/)。

**AllSides**：以盲测（*multipartisan blind survey*）+ 专家评审 + 社区反馈三通道定偏见等级，并给每档附“置信度”（高/中/低）。**未取得一手来源**（allsides.com 在本次调研网络下不可达，DNS 解析异常），以上为二手转述，仅作概念参考。

**Trust Project（新闻行业标准）**。8 项信任指标：Best Practices（机构准则与资金披露）、Journalist Expertise（记者资历）、Labels（新闻/观点/付费标注）、References（引用来源可核查）、Methods（报道方法）、Locally Sourced（本地在场）、Diverse Voices、Actionable Feedback（纠错机制）。覆盖机构/记者/单篇三个层面。来源：[Trust Indicators（官方页面，已核验）](https://thetrustproject.org/faq/trust-indicators/)。

**适用性判断**：NewsGuard 的“可检验的二元准则 + 加权 + 每档有证据卡片”结构最适合我们——我们的信源只有 ~20 个，完全可以人工定级并写死在配置里，不需要模型。NewsGuard/MBFC 的准则里，“资金/所有权披露”对政府网站无意义，可替换为“行政层级”“是否政策一手发布方”“是否可追溯政策原文链接”“是否有纠错/更新记录”。MBFC 的“存续年限/流量”维度对应我们可测的“历史抓取成功率”（`school-crawler-health.json` 已有该数据）。

### 2.2 图书馆学 / 信息素养框架

- **SIFT**（Caulfield, 2019）：Stop → Investigate the source → Find better coverage → Trace claims to original context。核心理念是“重构语境”：多数核查不是证明内容错误，而是恢复被剥离的语境。来源：[SIFT: The Four Moves（作者原文，已核验）](https://hapgood.us/2019/06/19/sift-the-four-moves/)。
- **CRAAP Test**（Currency 时效性、Relevance 相关性、Authority 权威性、Accuracy 准确性、Purpose 目的），2004 年由 CSU Chico Meriam Library 的 Sarah Blakeslee 提出（Blakeslee 2004, *LOEX Quarterly* 31(3)；OpenAlex 收录，无 DOI）。**一手机构页面（csuchico.edu）本次网络下不可达**，仅确认书目信息。
- **Lateral reading**（Wineburg & McGrew）：专业事实核查者的做法不是细读页面本身，而是离开页面横向查证来源声誉。来源：[SSRN 2017 版，DOI 10.2139/ssrn.3048994](https://doi.org/10.2139/ssrn.3048994)；正式版 *Teachers College Record* 121(2), 2019, [DOI 10.1177/016146811912101102](https://doi.org/10.1177/016146811912101102)。

**适用性判断**：SIFT 的 “Trace to original context” 正是我们能给用户的最大价值——每条社区帖若能链接到它转述的官方政策原文页，信任问题就解决大半。CRAAP 把 Currency 列为五维之一，支持我们把“时效性”做成独立于可信度的第二维度。

### 2.3 信任传播（学术）

- **PageRank**（Brin & Page, 1998）：链接作为信任投票的迭代传播。[Computer Networks and ISDN Systems 30(1–7), DOI 10.1016/s0169-7552(98)00110-x](https://doi.org/10.1016/S0169-7552(98)00110-X)。
- **HITS**（Kleinberg, 1999）：authority/hub 双角色迭代。[JACM 46(5), DOI 10.1145/324133.324140](https://doi.org/10.1145/324133.324140)。注：任务书中“HILL”未找到对应算法，疑为 HITS 之误记。
- **TrustRank**（Gyöngyi, Garcia-Molina & Pedersen, 2004）：从少量人工精选的种子可信页出发做半监督信任传播，对抗 web spam。[VLDB 2004, DOI 10.1016/b978-012088469-8/50052-8](https://doi.org/10.1016/B978-012088469-8/50052-8)。
- **EigenTrust**（Kamvar et al., 2003）：P2P 网络中由局部信任迭代收敛全局信任分数。[WWW 2003, DOI 10.1145/775152.775242](https://doi.org/10.1145/775152.775242)。
- **维基百科的可靠来源分级**：可能是全球规模最大的“生产级来源分级系统”。核心原则“有事实核查与准确性声誉的、独立、已发布的来源”；关键操作规则：**通讯社转载不算多个来源**（内容农场洗稿按原始通稿对待）、UGC/论坛默认不可用（仅限“关于自身”）、聚合平台可靠性取决于被转载的原始来源。来源：[Wikipedia: Identifying reliable sources（官方方针页，已核验）](https://en.wikipedia.org/wiki/Wikipedia:Identifying_reliable_sources)。

**适用性判断**：PageRank/HITS/TrustRank 需要**链接图**和**可投票的边**，我们不满足前提——各政府门户之间基本互不链接，来源数只有 ~20 个，迭代传播没有意义。**这些方法不适合本项目，仅作背景**。但 TrustRank 的“少量人工种子 + 传播”思想有一个弱化版可用：**官方来源作为种子；社区帖链接到官方原文 = 一条可投票的边**，即“可追溯性”本身作为加分项（见 §5.2）。

### 2.4 数据集（供未来训练/校验用，当前不必上）

- **NELA-GT**（Gruppi, Horne & Adalı）：按来源标注的大规模新闻文章数据集，逐年发布（2018–2022）。[arXiv:2203.05659](https://arxiv.org/abs/2203.05659)；仓库 [MELALab/nela-gt](https://github.com/MELALab/nela-gt)。
- **FakeNewsNet**（Shu et al., 2020）：新闻内容 + 社交上下文 + 时空信息的假新闻数据集。[Big Data 8(3), DOI 10.1089/big.2020.0062](https://doi.org/10.1089/big.2020.0062)；仓库 [KaiDMML/FakeNewsNet](https://github.com/KaiDMML/FakeNewsNet)（已核验，1356 stars）。

**反面警示**——Zhou et al. (2021) “Hidden Biases in Unreliable News Detection Datasets”（EACL 2021）：当训练/评测集来源有重叠时，模型靠**记住“站点→标签”映射**就能得高分，干净切分下准确率掉 10%+。对工程上的教训：来源层级信号很强但不能是唯一信号，且评测任何“自动可信度”功能时必须按来源切分。[DOI 10.18653/v1/2021.eacl-main.211](https://doi.org/10.18653/v1/2021.eacl-main.211)。

---

## 3. 方向二：交叉验证 / 事实核查

### 3.1 结构化事实核查生态（ClaimReview）

- **ClaimReview**：schema.org 的结构化标记类型（Thing > CreativeWork > Review > ClaimReview），事实核查机构在文章页嵌入 JSON-LD，机器可读地声明“被核查的说法（claimReviewed）、核查者（author）、评级（reviewRating）”。来源：[schema.org/ClaimReview（规范原文，已核验）](https://schema.org/ClaimReview)。
- **Google Fact Check Tools API**：两个子 API——已授权用户可对自己站点读写 ClaimReview 标记；任何人可查询与 [Fact Check Explorer](https://factcheck.google.com) 相同的核查结果集，数据即全网 ClaimReview 标记的聚合，并贡献到 Data Commons（datacommons.org/factcheck/download 可下载全量）。来源：[官方开发者文档（已核验）](https://developers.google.com/fact-check/tools/api)。
- **CLEF CheckThat! Lab**：主张识别、可核查性判断、claim matching（同一说法在不同语料中配对）等任务的常设评测。Overview 论文：Elsayed et al. 2019（[DOI 10.1007/978-3-030-28577-7_25](https://doi.org/10.1007/978-3-030-28577-7_25)）、Barrón-Cedeño et al. 2020（[DOI 10.1007/978-3-030-58219-7_17](https://doi.org/10.1007/978-3-030-58219-7_17)）。官网 [checkthat.gitlab.io](https://checkthat.gitlab.io/)（本次抓取返回空页，未能核验内容，标注为“地址确认、内容未核验”）。

**关于任务书提到的 DeClarouR 与 TVFactCheck：均未找到一手来源。**DeClarouR 在 arXiv、Crossref、OpenAlex、GitHub、Hugging Face 的检索均为零结果，疑为名称有误或纯二手转述；TVFactCheck 在 OpenAlex/arXiv 检索无果。二者的实际功能（基于 ClaimReview 的声明检索）已被上面的一手来源（schema.org 规范 + Google API + CheckThat!）覆盖，不影响方案设计。

### 3.2 声明抽取与核查工具（开源）

- **ClaimBuster**（Hassan et al., PVLDB 2017）：检测“值得核查的声明”（check-worthiness）的端到端系统，提供 API、数据集与 Docker。[DOI 10.14778/3137765.3137815](https://doi.org/10.14778/3137765.3137815)；官网 [idir.uta.edu/claimbuster](https://idir.uta.edu/claimbuster/)（已核验，IDIR Lab, UT Arlington）。
- **FActScore**（Min et al., EMNLP 2023）：把长文本拆成原子事实，计算被可靠知识源支持的原子事实百分比——“细粒度拆解 + 逐条对照知识源”的思路可移植。[arXiv:2305.14251](https://arxiv.org/abs/2305.14251)；仓库 [shmsw25/FActScore](https://github.com/shmsw25/FActScore)（已核验，460 stars，官方 EMNLP 2023 实现）。
- **Hoaxy**（Shao et al., CSCW 2016, Indiana University OSoMe）：claim 检索 + 社交传播可视化平台，现并入 OSoMeNet。[DOI 10.1145/2872518.2890098](https://doi.org/10.1145/2872518.2890098)；仓库 [osome-iu/hoaxy-backend](https://github.com/osome-iu/hoaxy-backend)（已核验）；站点 [hoaxy.osome.iu.edu](https://hoaxy.osome.iu.edu/)（已核验，重定向至 OSoMeNet）。

### 3.3 立场检测：多源一致性的经典做法

- **Fake News Challenge Stage 1（FNC-1）**：给定一条声明（headline）与一篇文章，判 agree / disagree / discuss / unrelated——这正是“交叉验证”的形式化定义。基线论文：Riedel et al. 2017（[arXiv:1707.03264](https://arxiv.org/abs/1707.03264)）；复盘与数据集修正：Hanselowski et al. 2018（[arXiv:1806.05180](https://arxiv.org/abs/1806.05180)）。
- **Tan, Friggeri & Adamic, “Lost in Propagation?”**（ICWSM）：从源头跟踪新闻在网上的传播链路，发现事实核查往往发生在多次转载之后——佐证链上的中间节点不是独立来源。[DOI 10.1609/icwsm.v10i1.14712](https://doi.org/10.1609/icwsm.v10i1.14712)。

### 3.4 事件共现与新闻聚类

- **GDELT**：全球新闻事件数据库（CAMEO 编码事件表）+ 全局知识图 GKG（人物/组织/地点/主题/情感共现图，每条信息附带同文 EventID 列表）；2.0 版 15 分钟更新、65 种语言，另有 mentions 表记录每条事件被哪些报道提及。来源：[GDELT 官方文档页（已核验）](https://www.gdeltproject.org/data.html)。GDELT 证明“跨来源事件共现”是可工程化的：同一事件的多篇报道通过共现实体聚到一起。
- 学术上的对应问题是 **Topic Detection and Tracking（TDT）** 中的 first story detection / streaming clustering（如 Petrović et al. 关于 Twitter 流式首报检测的工作；Petrović, Osborne & Lavrenko, “Streaming First Story Detection with Application to Twitter”, EMNLP 2013——**本次未直接核验原文**，仅 Crossref 见到相关后续论文如 McCreadie et al. 2013 [DOI 10.1109/bigdata.2013.6691620](https://doi.org/10.1109/BigData.2013.6691620)，标注为二手）。

### 3.5 真伪传播的实证结论（决定社区源策略）

- **Rubin et al. 2016**（任务书所指的 Rubin 真值标注工作）：“Fake News or Truth? Using Satirical Cues to Detect Potentially Misleading News”——对新闻做真值（truth label）人工标注并研究自动判别。[COLING 2016, DOI 10.18653/v1/w16-0802](https://doi.org/10.18653/v1/w16-0802)。相关基础：Lukoianova & Rubin 2014, “Veracity Roadmap: Is Big Data Objective, Truthful and Credible?”（把“真实性”列为大数据质量维度）[DOI 10.7152/acro.v24i1.14671](https://doi.org/10.7152/acro.v24i1.14671)。
- **Vosoughi, Roy & Aral (2018, Science)**：对 Twitter 十余年全量数据的分析——**虚假消息传播得比真实消息更深、更快、更广**，且主要因为人的转发而非机器人。[DOI 10.1126/science.aap9559](https://doi.org/10.1126/science.aap9559)。对社区源的含义：社区热度不能当作可信度信号，甚至负相关。

**适用性判断**：我们没有 LLM 依赖也没有标注预算，所以走“轻结构化”路线——不抽取自然语言声明，而是**以“事件”为核验单元**（区 × 学校 × 学段 × 政策动作），用 GDELT 式的属性共现做聚类（纯 Python 字典 + 规则即可），用 FNC 式的四分类思想输出“佐证状态”（官方确认 / 多源一致 / 单源未证实 / 冲突）。FActScore 的“拆原子再对照”用于人工复核社区帖时对照官方政策原文。Vosoughi 结论支持我们对社区帖默认“待官方核验”并禁止热度加权。

---

## 4. 方向三：时效性（temporal validity / freshness）

### 4.1 学术：时间感知检索与知识的时间有效期

- **Kanhabua, Blanco & Nørvåg, “Temporal Information Retrieval”**（*Foundations and Trends in IR* 9(2), 2015）：时间感知检索的系统综述，覆盖时间表达式抽取、文档时间戳推断、freshness 与 coverage 两个 web 归档质量指标。[DOI 10.1561/1500000043](https://doi.org/10.1561/1500000043)。
- **Campos et al., “Survey of Temporal Information Retrieval and Related Applications”**（*ACM Computing Surveys* 46(2), 2014）：另一篇综述，覆盖时间感知排序与查询的时间意图分类。[DOI 10.1145/2619088](https://doi.org/10.1145/2619088)。
- **Dai & Davison, “Capturing page freshness for web search”**（CIKM 2010）：对网页内容随时间变化的实证分析与新鲜度建模——关键观点是 **freshness 是“内容相对其真实世界状态的时效”而非“抓取时间新”**（页面上年久未更新的旧信息抓取再新也不新鲜）。[DOI 10.1145/1835449.1835658](https://doi.org/10.1145/1835449.1835658)。
- **时间知识库补全（temporal KG validity）**：把“事实只在时间区间内有效”显式建模。García-Durán, Dumančić & Niepert (EMNLP 2018) 提出 YAGO11k/YAGO15k、ICEWS 系列带时间戳的知识图谱基准（[DOI 10.18653/v1/d18-1516](https://doi.org/10.18653/v1/d18-1516)）；Lacroix, Obozinski & Usunier (ICLR 2020) “Tensor Decompositions for Temporal Knowledge Base Completion”（[arXiv:2004.04926](https://arxiv.org/abs/2004.04926)，仓库 [facebookresearch/tkbc](https://github.com/facebookresearch/tkbc)，已核验）。**给我们的启发是数据模型而非算法**：每条政策信息应带 `(valid_from, valid_to)` 或“招生年度”属性，检索/展示时过滤或降权，而不是靠发布日期隐式推断。

### 4.2 工业界：freshness 排序的实践公式

- **Google Caffeine**（2010 官方博客）：专为缩短索引延迟设计的增量索引系统，官方博客公告 “Our new search index: Caffeine”。来源：[googleblog.blogspot.com（官方，已核验存在）](https://googleblog.blogspot.com/2010/06/our-new-search-index-caffeine.html)。
- **Google freshness 算法**（2011 官方博客，Nov 3）：官方原文举例：搜 “olympics” 用户要的是下一届而非 1900 年——“Google Search uses a freshness algorithm, designed to give you the most up-to-date results... the most recent information can be from the last week, day or even minute, and depending on the search terms, the algorithm needs to be able to figure out if a result from a week ago about a TV show is recent, or if a result from a week ago about breaking news is stale”。来源：[googleblog.blogspot.com（官方原文，已核验）](https://googleblog.blogspot.com/2011/11/giving-you-fresher-more-recent-search.html)。“Query Deserves Freshness (QDF)” 这一术语本身**未找到 Google 一手文档**（公开解释均来自 Search Engine Land 等二手转述），但 QDF 描述的“按查询意图分类决定新鲜度权重”机制与上述官方文章一致。
- **Hacker News 排名公式（一手源码）**：YC 官方发布的 arc3.1 发行包中 `news.arc`：
```
// Hacker News frontpage-rank（arc3.1 news.arc）
; Votes divided by the age in hours to the gravityth power.
; Would be interesting to scale gravity in a slider.
(= gravity* 1.8 timebase* 120 front-threshold* 1)
(def frontpage-rank (s (o scorefn realscore) (o gravity gravity*))
      (/ (realscore s)
         (expt (/ (+ (item-age s) timebase*) 60) gravity)))
```
即 `score / (age_hours + 2)^1.8`——**分数除以年龄的幂**（时间衰减独立于分数类型）。来源：[arclanguage.org/arc3.1.tar](http://www.arclanguage.org/arc3.1.tar) 中 `news.arc`（已下载核验，含上述源码）。
- **Reddit hot 算法（一手源码）**：Reddit 开源代码 `r2/r2/lib/db/_sorts.pyx`：`order = log10(max(abs(s), 1)) + seconds / 45000`——对数化分数 + 线性时间项。来源：[reddit-archive/reddit（GitHub，已核验）](https://github.com/reddit-archive/reddit/blob/master/r2/r2/lib/db/_sorts.pyx)。

### 4.3 招生场景的特殊性

学术文献中没有直接针对“招生政策年度周期”的时效性研究（未找到，属常识性领域知识）；最接近的是：CRAAP 把 Currency 列为第一准则（§2.2）、维基百科方针明确“医学等快速演化领域旧来源会被新证据取代”且“突发新闻首发报道常有严重错误，宜等一两天再采信”（§2.2，已核验原文）、Google freshness 博客中“上周的 TV 剧结果算新、上周的突发新闻算旧”的**按主题分时间尺度**思想。北京 K12 的实际周期：政策 4–7 月密集发布、6 月信息采集/派位，8 月后进入静默期——这意味着**时效函数必须按信息类型分别调参，而不是统一半衰期**。

---

## 5. 评测方案（按本地可测性收敛）

经本地可测性审计，评测聚焦**唯一一个错判会主动误导用户的模块——转载识别**（「N 个独立来源」徽章的正确性全押在此）；正则槽位抽取在标注转载对时顺带评测；来源档位与展示形态属设计决策，直接定案不做评测；声明匹配、冲突检测与内容 diff 延后到数据成熟。全部候选方法中，被本地实测先验否决的不再列出。

### 5.0 通用评测规范

- **数据来源**：统一从 `community-data.json` / `data.json` 取最近 2–4 周真实抓取数据抽样，不造合成数据；
- **金标准纪律**：标注时只依据文本本身与常识，不看来源档位（评级是另一个维度，防标签泄漏）；不确定样本标「存疑」单独报告，不计入主指标；
- **防泄漏实操**：标注界面仅呈现 title + 正文前段 + 域名脱敏的 link，不呈现 source 名称；
- **按来源切分报告**（Zhou et al. 2021）：额外报告「来源互不重叠的干净子集」上的指标，防止方法只是记住来源风格；
- **成本同报**：每个候选记录单条处理耗时与是否需要外部依赖，选型时成本与效果同权重；
- **判定规则**：两个方法主指标差距 < 3 个百分点时选成本低的；组合形态显著优于单方法才上组合。

### 5.1 本地数据盘点（标注池依据，2026-10-23 实测数字）

| 数据 | 规模 | 用途 |
| --- | --- | --- |
| `community_merged_enriched.json` | 821 条 · 7 源 · 3 城市（北京/上海/广州），267 条正文 ≥100 字 | 标注池 |
| 双小升初站（北京小升初网 + 北京小升初信息网） | 184 条；**6-gram Jaccard > 0.5 的跨站对：0 对** | 5.2 关键难例与先验（见下） |
| `school_candidates` 聚簇 | 1463 个学校键，**55 个跨源簇**（最大簇“人大附中”3 源 42 条） | 正例候选的生成来源 |
| `data.json` 官方快照 | 市教委 12 + 教育部 11 + 区级政策 66 + 学校栏目 507 条 | 官方裁决锚点 |
| `school-crawler-health.json` | 149 校健康记录 | 来源档位的健康度信号（5.4） |
| git 快照历史 | `index.html` 22 个提交点，6 小时节奏刚开始 | 内容 diff 的启用条件（5.5） |

### 5.2 转载识别评测（先测，核心模块）

输入一对文章，输出「转载 / 独立」二分类；同簇转载只计一个独立来源（维基百科「通讯社转载不算多来源」规则）。

**先验（已实测）**：双小升初站之间正文 n-gram **零重叠**——二者不是照搬式转载而是改写式洗稿/各自独立成文。由此排除两类候选：字面指纹类（shingle Jaccard / SimHash/MinHash）只能抓全文照搬，在改写式转载上预期召回不可用；URL/域名规则仅同源去重有效，且 enricher 的 `dedupe_records` 已覆盖同 URL 情形。本项目最难也最重要的正是改写式转载（两站同属小升初资讯生态、选题高度重合），主战场是语义指纹。

| 候选 | 做法 | 预期优点 | 预期弱点 | 依赖 |
| --- | --- | --- | --- | --- |
| D 语义指纹 | embedding 相似度 + 关键实体（校名/日期/数字）重合度加权 | 能抓改写式洗稿；实体重合防误伤独立报道 | 同事件独立报道也可能高相似，需调权 | embedding 服务 |
| E D + LLM 边界判定 | 语义指纹落入灰区的对交 LLM 判「改写自对方 or 各自独立」 | 灰区例少、按对成本低 | 判定标准需 prompt 定义清楚 | embedding + LLM |

**评测法**：

- 标注池落 `docs/eval/`，JSONL 每行 `{a_link, b_link, label(转载/独立), note}`，人工只标 label；
- 正例候选从 55 个跨源校簇内两两组合 + 53 对跨语料同标题对生成，负例随机跨校采样，目标 **100 对**；
- 每候选实现为纯函数 `classify_pair(a, b) -> bool`；阈值候选 30 对调参、70 对报告；
- 指标：精确率/召回率/F1（转载为正类）+ 按来源切分子集；重点指标为**误伤率**——独立报道被判转载，直接导致独立来源数少算。

| 候选 | 精确率 | 召回率 | F1 | 误伤率 | 结论 |
| --- | --- | --- | --- | --- | --- |
| A 域名规则 | 0.00 | 0.00 | 0.00 | 0% | 已测（2026-10-23）：标注池按跨源构造，A 永不触发；仅适用于同站去重（生产 `dedupe_records` 已覆盖） |
| B shingle Jaccard | 0.00 | 0.00 | 0.00 | 0% | 已测（2026-10-23，净化全文）：关键正例全文 8-gram 重叠仅 0.013，归档 |
| C SimHash | 0.00 | 0.00 | 0.00 | 0% | 已测（2026-10-23）：与 B 同失败模式，归档 |
| D 语义指纹 | 0.00 | 0.00 | 0.00 | 0% | 已测替身（2026-10-23，特征组合版）：正例分数排名 #13/#17，被"汇总文×汇总文"泛化实体清单压制，不可分；真 embedding 版未测 |
| E D + LLM 边界判定 | 1.00 | 1.00 | 1.00 | 0% | 已测（2026-10-26，LLM 直判）：对 21 对 v2 重叠子集 P/R/F1 全满；31 对新池判出 9 同源（含 5 对同帖双链、2 对园博园簇跨站改编、2 已知正例确认）+ 1 存疑。同池表层方法对照：A/B/C 全零，D-lite 召回 0.22。注意：判定者与 v2 金标准同为 LLM，满分为同源一致性而非独立验证——10 个新判定待人工复核 |

#### 5.3.2 候选 E 评测记录（2026-10-26）

- **判定协议**：LLM 盲判两文全文，三分类（同源/独立/存疑），判定标准写死——「同源」= 同一文章改写重发 **或** 明显改编自同一上游通知/通稿（共享具体事件锚点：同一学校+同一日期+同一动作）；**汇总文含同事件条目不算同源**（聊很多相同话题 ≠ 讲同一件事，除非核心段落共享上游）；每条判定附证据引用。
- **评测池**：31 对 = 10 召回候选（共享校名 + ≥2 个非年份特征数字的跨站对）+ 13 v2 重叠对 + 18 随机负例（从 v2 独立层抽取）。
- **对照实验**：同池跑 A/B/C/D——A/B/C 召回 0（与 5.3.1 结论一致），D-lite 召回 0.22 且只抓到同帖双链（字面相同的那类），跨站改编对依然全漏。**表层方法与 LLM 判定的召回差距 0.22 → 1.00。**
- **新发现：同帖双链**——社区帖存在 5 对「论坛视图 URL ≠ 正文视图 URL、正文逐字相同」的重复（同一帖被两条抓取链各抓一次）。这是**数据层去重缺陷**，不是报道同源性问题；应修 forum/content 两链的 URL 归一（如 Discuz thread-id 归并），而不是靠 5.3 分类器兜底。
- **金标准风险（如实记录）**：判定者与 v2 预标同为 LLM，1.00 的一致性是「方法有效性」证据而非「独立金标准验证」；10 个新同源判定 + 1 存疑待人工复核后，才可宣布候选 E 定型。
- **下一步**：人工复核 `eval/annotations/pairs_e.jsonl` 的 E002/E003/E006–E010/E013 共 8+1 对（每对附证据句，几分钟即可）；复核通过则候选 E 进生产（簇内灰区对按需调用），并顺手修同帖双链归一。

#### 5.3.1 首轮评测结论（2026-10-23）

- **评测目标已从「转载识别」重定义为「同源检测」**：本批数据中不存在互为改写转载的文章对（前 100 对预标 0 正例），但存在同事件多源报道簇（如人大附中园博园竣工 10-20 验收，两站各文）——两文各自独立成文、共享同一上游通稿，按维基百科「转载不算多来源」规则不构成独立佐证，正是「N 个独立来源」徽章要防的假阳性。
- **表层方法全灭（实证确认 §5.9 先验的最强形式）**：同一事件的改写式报道字面层几乎零共享（8-gram 重叠 1.3%）；特征组合法的失败模式是「汇总文对共享大量泛化实体清单，分数反超真同源对」。
- **金标准与评测纪律**：本轮 100 对金标准为 LLM 机器预标（2 同源 / 1 存疑 / 97 独立），与人工标注者前 20 对一致性 18/20，待人工抽查复核后方可作为正式金标准；正例仅 2 对，召回指标方差极大，本轮有效结论是「表层方法召回为 0」与误伤率。
- **下一步**：语义层是唯一可行路径——(a) 本地装中文 embedding 模型跑真·D；(b) 或按 §5.9.4 既定方式由 LLM 会话做候选 E，但金标准必须改为人工标注（防自评循环）。
- 数据集：`eval/`（gitignore，不入库），官方 118 条全文 + 社区 572 条 + 论坛 218 帖；生成与评测脚本 `eval/tools/`。

### 5.3 正则槽位抽取（顺带评测）

`school_candidates` / `district_candidates` / `stage` / `event_type` 即已实现的正则槽位抽取。在标注 5.2 转载对时自然对照双方抽取结果，增量积累 30–50 篇金标准即可计算槽位字段准确率（分字段报告），不单开标注轮次。LLM 抽取（zero-shot / few-shot + schema）不参与横评：本项目工作流中 LLM 即本地会话，无 API 计费与外部依赖，在 5.2 定型后于簇内难例上按需启用。

| 候选 | 槽位准确率 | 结论 |
| --- | --- | --- |
| A 正则槽位抽取 | — | 待测 |

### 5.4 直接决策项（不做评测）

- **来源档位**：约 27 个信源（社区 7 源 + 官方约 20 源）人工定档写死在配置——锚点 = 行政层级，动态项用 `school-crawler-health.json` 健康度。当前无长尾信源，LLM 自动评级与分层组合待长尾信源出现时再议。
- **展示形态**：选「档位徽章 + 一句话理由 + N 个独立来源（可展开簇内条目）」形态；不给 0–100 数字（连续分数会被过度解读 [37]）；**全量打标签**，规避 Implied Truth Effect [38]；区分「来源档位」与「待官方核验」两个正交标签 [39]；原型自用迭代。

### 5.5 延后项（数据未成熟）

- **内容 diff（旧文重发检测）**：启用条件为 git 快照历史 ≥ 2 周；届时历代 `index.html` / `data.json` 提交点即为现成时间序列，从 22 个提交点继续积累即可；
- **声明匹配与冲突检测**：只在 5.2 产出的簇上增量做——遇到天然冲突对（如社区中的“人朝高中搬迁辟谣”帖）再标注，不预先造池。声明匹配方法届时从规则字段键、embedding 召回 + LLM 判定中按 5.0 判定规则选型；冲突检测优先字段值精确比对（零成本），措辞冲突再上 LLM。
- **时效抽取**（招生年度 + 时间区间）：在已定型的声明上做，发布时间戳 + 标题/正文年份正则先行，自然语言时间表达（「五一后一周」）的 LLM 抽取按需启用。

### 5.6 执行顺序

```
// 执行顺序
5.2 转载识别（含 5.3 槽位顺带评测）
  └─> 声明匹配 / 冲突检测（簇上增量）
        └─> 时效抽取（在已定型声明上）
              └─> 展示原型（自用迭代）
[并行] 5.4 来源档位（人工配置，一次写死）
[挂起] 内容 diff（等快照历史 ≥ 2 周）
```

总人工标注量约 100–150 条，全部集中在唯一会主动误导用户的模块上；每模块定型后胜出方法与数字填入对应结果表。

---

## 6. 参考文献

### 来源可信度评级

1. NewsGuard — Rating Process & Criteria. [https://www.newsguardtech.com/ratings/rating-process-criteria/](https://www.newsguardtech.com/ratings/rating-process-criteria/) （官方方法论：9 准则、0–100 分、Nutrition Label）

2. Ad Fontes Media — Methodology. [https://adfontesmedia.com/methodology/](https://adfontesmedia.com/methodology/) （平衡分析师小组 + 文章级评分聚合）

3. Media Bias/Fact Check — Methodology. [https://mediabiasfactcheck.com/methodology/](https://mediabiasfactcheck.com/methodology/) （事实性 0–10 加权体系与档位）

4. The Trust Project — Trust Indicators. [https://thetrustproject.org/faq/trust-indicators/](https://thetrustproject.org/faq/trust-indicators/) （新闻业 8 项信任指标）

5. Wikipedia — Identifying reliable sources. [https://en.wikipedia.org/wiki/Wikipedia:Identifying_reliable_sources](https://en.wikipedia.org/wiki/Wikipedia:Identifying_reliable_sources) （生产级来源分级方针：转载不算多来源、UGC 默认不可用）

6. Brin & Page (1998), The Anatomy of a Large-Scale Hypertextual Web Search Engine. [https://doi.org/10.1016/S0169-7552(98)00110-X](https://doi.org/10.1016/S0169-7552(98)00110-X) （PageRank）

7. Kleinberg (1999), Authoritative Sources in a Hyperlinked Environment. [https://doi.org/10.1145/324133.324140](https://doi.org/10.1145/324133.324140) （HITS）

8. Gyöngyi et al. (2004), Combating Web Spam with TrustRank. [https://doi.org/10.1016/B978-012088469-8/50052-8](https://doi.org/10.1016/B978-012088469-8/50052-8) （种子信任传播）

9. Kamvar et al. (2003), The EigenTrust Algorithm. [https://doi.org/10.1145/775152.775242](https://doi.org/10.1145/775152.775242) （信任分数迭代收敛）

10. Caulfield (2019), SIFT: The Four Moves. [https://hapgood.us/2019/06/19/sift-the-four-moves/](https://hapgood.us/2019/06/19/sift-the-four-moves/) （SIFT 信息素养方法）

11. Wineburg & McGrew (2017/2019), Lateral Reading. [https://doi.org/10.2139/ssrn.3048994](https://doi.org/10.2139/ssrn.3048994) （专家横向核查行为）

12. Zhou et al. (2021), Hidden Biases in Unreliable News Detection Datasets. [https://doi.org/10.18653/v1/2021.eacl-main.211](https://doi.org/10.18653/v1/2021.eacl-main.211) （来源-标签记忆混淆的警示）

### 交叉验证 / 事实核查

13. schema.org — ClaimReview. [https://schema.org/ClaimReview](https://schema.org/ClaimReview) （声明核查的结构化标记规范）

14. Google — Fact Check Tools API. [https://developers.google.com/fact-check/tools/api](https://developers.google.com/fact-check/tools/api) （ClaimReview 聚合检索）

15. Elsayed et al. (2019), CheckThat! at CLEF 2019. [https://doi.org/10.1007/978-3-030-28577-7_25](https://doi.org/10.1007/978-3-030-28577-7_25) （主张识别/验证评测）

16. Barrón-Cedeño et al. (2020), Overview of CheckThat! 2020. [https://doi.org/10.1007/978-3-030-58219-7_17](https://doi.org/10.1007/978-3-030-58219-7_17) （含 claim matching 任务）

17. Hassan et al. (2017), ClaimBuster. [https://doi.org/10.14778/3137765.3137815](https://doi.org/10.14778/3137765.3137815) ；官网 [https://idir.uta.edu/claimbuster/](https://idir.uta.edu/claimbuster/) （可核查声明识别）

18. Min et al. (2023), FActScore. [https://arxiv.org/abs/2305.14251](https://arxiv.org/abs/2305.14251) ；代码 [https://github.com/shmsw25/FActScore](https://github.com/shmsw25/FActScore) （原子事实对照知识源）

19. Shao et al. (2016), Hoaxy. [https://doi.org/10.1145/2872518.2890098](https://doi.org/10.1145/2872518.2890098) ；代码 [https://github.com/osome-iu/hoaxy-backend](https://github.com/osome-iu/hoaxy-backend) （声明传播追踪）

20. Riedel et al. (2017), FNC-1 Stance Detection Baseline. [https://arxiv.org/abs/1707.03264](https://arxiv.org/abs/1707.03264) （agree/disagree/discuss/unrelated 四分类）

21. Hanselowski et al. (2018), A Retrospective Analysis of the FNC. [https://arxiv.org/abs/1806.05180](https://arxiv.org/abs/1806.05180) （FNC 数据集问题修正）

22. GDELT Project — Data Documentation. [https://www.gdeltproject.org/data.html](https://www.gdeltproject.org/data.html) （事件库/GKG 共现、mentions 表）

23. Rubin et al. (2016), Fake News or Truth? [https://doi.org/10.18653/v1/w16-0802](https://doi.org/10.18653/v1/w16-0802) （新闻真值标注）

24. Lukoianova & Rubin (2014), Veracity Roadmap. [https://doi.org/10.7152/acro.v24i1.14671](https://doi.org/10.7152/acro.v24i1.14671) （大数据真实性维度）

25. Vosoughi, Roy & Aral (2018), The Spread of True and False News Online. [https://doi.org/10.1126/science.aap9559](https://doi.org/10.1126/science.aap9559) （虚假信息传播快于真实信息）

26. Tan, Friggeri & Adamic (2016), Lost in Propagation? [https://doi.org/10.1609/icwsm.v10i1.14712](https://doi.org/10.1609/icwsm.v10i1.14712) （新闻传播链与核查滞后）

27. Shu et al. (2020), FakeNewsNet. [https://doi.org/10.1089/big.2020.0062](https://doi.org/10.1089/big.2020.0062) ；[https://github.com/KaiDMML/FakeNewsNet](https://github.com/KaiDMML/FakeNewsNet) （假新闻多模态数据集）

### 时效性

28. Kanhabua, Blanco & Nørvåg (2015), Temporal Information Retrieval. [https://doi.org/10.1561/1500000043](https://doi.org/10.1561/1500000043) （时间感知检索综述）

29. Campos et al. (2014), Survey of Temporal IR. [https://doi.org/10.1145/2619088](https://doi.org/10.1145/2619088) （时间意图与排序综述）

30. Dai & Davison (2010), Capturing Page Freshness for Web Search. [https://doi.org/10.1145/1835449.1835658](https://doi.org/10.1145/1835449.1835658) （freshness 相对真实世界状态）

31. García-Durán et al. (2018), Learning Sequence Encoders for Temporal KG Completion. [https://doi.org/10.18653/v1/d18-1516](https://doi.org/10.18653/v1/d18-1516) （YAGO11k/15k、ICEWS 基准）

32. Lacroix et al. (2020), Tensor Decompositions for Temporal KG Completion. [https://arxiv.org/abs/2004.04926](https://arxiv.org/abs/2004.04926) ；代码 [https://github.com/facebookresearch/tkbc](https://github.com/facebookresearch/tkbc) （时间区间有效事实建模）

33. Google (2010), Our New Search Index: Caffeine. [https://googleblog.blogspot.com/2010/06/our-new-search-index-caffeine.html](https://googleblog.blogspot.com/2010/06/our-new-search-index-caffeine.html) （增量索引官方公告）

34. Google (2011), Giving You Fresher, More Recent Search Results. [https://googleblog.blogspot.com/2011/11/giving-you-fresher-more-recent-search.html](https://googleblog.blogspot.com/2011/11/giving-you-fresher-more-recent-search.html) （freshness 算法官方说明）

35. Hacker News ranking source (arc3.1 news.arc). [http://www.arclanguage.org/arc3.1.tar](http://www.arclanguage.org/arc3.1.tar) （一手源码：score/(age+2)^1.8）

36. Reddit hot algorithm source. [https://github.com/reddit-archive/reddit/blob/master/r2/r2/lib/db/_sorts.pyx](https://github.com/reddit-archive/reddit/blob/master/r2/r2/lib/db/_sorts.pyx) （一手源码：log10 分数 + 时间项）

### 不确定性传播 / 展示

37. van der Bles et al. (2019), Communicating Uncertainty about Facts, Numbers and Science. [https://doi.org/10.1098/rsos.181870](https://doi.org/10.1098/rsos.181870) （面向公众的不确定性传达综述）

38. Pennycook, Bear, Collins & Rand (2020), The Implied Truth Effect. [https://doi.org/10.1287/mnsc.2019.3478](https://doi.org/10.1287/mnsc.2019.3478) （部分打标签的反效果）

39. Politi & Street (2010). [https://doi.org/10.1111/j.1365-2753.2010.01549.x](https://doi.org/10.1111/j.1365-2753.2010.01549.x) （共享决策中的不确定性沟通）

40. Mehta (2023), Maybe, Maybe Not: A Survey on Uncertainty in Visualization. [https://arxiv.org/abs/2301.07687](https://arxiv.org/abs/2301.07687) （可视化中的不确定性综述）

### 明确未找到一手来源的项

- **DeClarouR**：arXiv / Crossref / OpenAlex / GitHub / Hugging Face 检索均为零结果，仅二手提及；其功能（ClaimReview 声明检索）由 §3.1 一手来源覆盖。
- **TVFactCheck**：OpenAlex / arXiv 检索无果，未取得一手来源。
- **AllSides 方法论页面**：域名在本次调研网络下不可达（DNS 异常），仅有二手转述。
- **CRAAP Test 官方页面**（CSU Chico Meriam Library）：同样不可达，仅确认 Blakeslee (2004), *LOEX Quarterly* 31(3) 书目。
- **Query Deserves Freshness (QDF)**：无 Google 一手文档；机制由 2011 官方 freshness 博文（文献 34）佐证。
- **“HILL”算法**：未检索到该名称的算法，疑为 HITS（文献 7）之误记。
- **TDT / first story detection（Petrović et al.）原文**：本次未能直接核验，标注为二手。