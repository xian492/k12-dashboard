# 研究笔记：多源信息的可信度评级、交叉验证与时效性标注

> 调研日期：2026-10-23。调研方法：一手来源优先（论文 DOI/arXiv 原文、项目源码仓库、官方文档页面），全部经网络实际访问核验；二手来源明确标注。本笔记服务于"我给你搜到了 xxx 条信息，每条来源是哪、置信度多少、是否过期"这一用户可见功能的设计。

---

## 1. 问题定义

本项目是北京 K12 招生信息聚合看板：Python 构建脚本每 6 小时拉取多源数据，产出静态站。信源横跨四个权威层级：

| 层级 | 信源 | 特点 |
|---|---|---|
| L0 市级官方 | 市教委、教育部 | 权威但覆盖粗粒度 |
| L1 区级官方 | 各区教委门户 | 政策的一手发布方 |
| L2 半官方结构化 | 义务教育入学服务平台 yjrx（官方 JSON） | 结构化、可靠，但语义有限 |
| L3 学校自有渠道 | 学校官网静态 HTML、统一建站平台（bjhdedu.cn / bjchyedu.cn 等） | 官方性参差，页面质量低 |
| L4 社区 | 家长论坛（community/ 目录 pipeline） | 有独家情报但过期/错误率高 |

要回答的三个研究问题，对应三个成熟研究方向：

1. **来源可信度评级**（source credibility ranking）：不同来源的默认信任权重怎么定、定几分。
2. **交叉验证 / 佐证**（corroboration / fact-checking）：同一事件被多源报道时，如何判断"独立佐证"还是"互相转载"，如何呈现一致性。
3. **时效性**（temporal validity / freshness）：招生政策有强年度周期（4–7 月集中发布），去年的政策今年不适用；如何计算与展示信息的"过期程度"。

加一个问题：**置信度如何展示才不误导**（uncertainty communication）。

---

## 2. 方向一：来源可信度评级

### 2.1 工业界的来源评级体系

**NewsGuard（商业，方法论最完整）**。对每个新闻站按 9 条准则打 0–100 分：可信度类（不发布虚假内容 22 分、负责任地收集信息 18 分、有纠错机制 12.5 分、区分新闻与观点 12.5 分、不误导标题 10 分）+ 透明度类（披露所有权与资金 7.5 分、标注广告 7.5 分、公开负责人 5 分、署名与联系渠道 5 分）。每份评级配一张 "Nutrition Label"（营养标签）卡片，写明每条判定的证据。评分分档：100 高可信、75–99 总体可信、60–74 可信但有重大例外、40–59 不可靠、0–39 严重不可靠。来源：[Rating Process & Criteria（官方页面，已核验）](https://www.newsguardtech.com/ratings/rating-process-criteria/)。

**Ad Fontes Media（商业）**。可靠性、偏见两个独立维度；每篇文章由至少三名政治立场平衡（左/中/右）的分析师实时同步评分，分歧大则换第二个平衡小组重评；来源分数是文章分数的加权平均，抽样取同一时刻各来源首页文章以评估"选题性偏见"。来源：[Methodology（官方页面，已核验）](https://adfontesmedia.com/methodology/)。

**Media Bias/Fact Check（免费网站，事实性评分可借鉴）**。2025 年起新方法论：事实性 0–10 分 = 失败事实核查记录（40%）+ 引用质量（25%）+ 透明度（25%，含所有权、资金、作者、使命、地点五要素）+ 片面性（10%）；另有独立于事实性的"可信度"10 分制（事实性 0–4 + 偏见等级 0–3 + 流量与存续年限 0–3）。人工评审至少 10 条标题 + 5 篇全文。来源：[Methodology（官方页面，已核验）](https://mediabiasfactcheck.com/methodology/)。

**AllSides**：以盲测（_multipartisan blind survey_）+ 专家评审 + 社区反馈三通道定偏见等级，并给每档附"置信度"（高/中/低）。**未取得一手来源**（allsides.com 在本次调研网络下不可达，DNS 解析异常），以上为二手转述，仅作概念参考。

**Trust Project（新闻行业标准）**。8 项信任指标：Best Practices（机构准则与资金披露）、Journalist Expertise（记者资历）、Labels（新闻/观点/付费标注）、References（引用来源可核查）、Methods（报道方法）、Locally Sourced（本地在场）、Diverse Voices、Actionable Feedback（纠错机制）。覆盖机构/记者/单篇三个层面。来源：[Trust Indicators（官方页面，已核验）](https://thetrustproject.org/faq/trust-indicators/)。

**适用性判断**：NewsGuard 的"可检验的二元准则 + 加权 + 每档有证据卡片"结构最适合我们——我们的信源只有 ~20 个，完全可以人工定级并写死在配置里，不需要模型。NewsGuard/MBFC 的准则里，"资金/所有权披露"对政府网站无意义，可替换为"行政层级""是否政策一手发布方""是否可追溯政策原文链接""是否有纠错/更新记录"。MBFC 的"存续年限/流量"维度对应我们可测的"历史抓取成功率"（`school-crawler-health.json` 已有该数据）。

### 2.2 图书馆学 / 信息素养框架

- **SIFT**（Caulfield, 2019）：Stop → Investigate the source → Find better coverage → Trace claims to original context。核心理念是"重构语境"：多数核查不是证明内容错误，而是恢复被剥离的语境。来源：[SIFT: The Four Moves（作者原文，已核验）](https://hapgood.us/2019/06/19/sift-the-four-moves/)。
- **CRAAP Test**（Currency 时效性、Relevance 相关性、Authority 权威性、Accuracy 准确性、Purpose 目的），2004 年由 CSU Chico Meriam Library 的 Sarah Blakeslee 提出（Blakeslee 2004, *LOEX Quarterly* 31(3)；OpenAlex 收录，无 DOI）。**一手机构页面（csuchico.edu）本次网络下不可达**，仅确认书目信息。
- **Lateral reading**（Wineburg & McGrew）：专业事实核查者的做法不是细读页面本身，而是离开页面横向查证来源声誉。来源：[SSRN 2017 版，DOI 10.2139/ssrn.3048994](https://doi.org/10.2139/ssrn.3048994)；正式版 *Teachers College Record* 121(2), 2019, [DOI 10.1177/016146811912101102](https://doi.org/10.1177/016146811912101102)。

**适用性判断**：SIFT 的 "Trace to original context" 正是我们能给用户的最大价值——每条社区帖若能链接到它转述的官方政策原文页，信任问题就解决大半。CRAAP 把 Currency 列为五维之一，支持我们把"时效性"做成独立于可信度的第二维度。

### 2.3 信任传播（学术）

- **PageRank**（Brin & Page, 1998）：链接作为信任投票的迭代传播。*[Computer Networks and ISDN Systems 30(1–7), DOI 10.1016/s0169-7552(98)00110-x](https://doi.org/10.1016/S0169-7552(98)00110-X)*。
- **HITS**（Kleinberg, 1999）：authority/hub 双角色迭代。*[JACM 46(5), DOI 10.1145/324133.324140](https://doi.org/10.1145/324133.324140)*。注：任务书中"HILL"未找到对应算法，疑为 HITS 之误记。
- **TrustRank**（Gyöngyi, Garcia-Molina & Pedersen, 2004）：从少量人工精选的种子可信页出发做半监督信任传播，对抗 web spam。*[VLDB 2004, DOI 10.1016/b978-012088469-8/50052-8](https://doi.org/10.1016/B978-012088469-8/50052-8)*。
- **EigenTrust**（Kamvar et al., 2003）：P2P 网络中由局部信任迭代收敛全局信任分数。*[WWW 2003, DOI 10.1145/775152.775242](https://doi.org/10.1145/775152.775242)*。
- **维基百科的可靠来源分级**：可能是全球规模最大的"生产级来源分级系统"。核心原则"有事实核查与准确性声誉的、独立、已发布的来源"；关键操作规则：**通讯社转载不算多个来源**（内容农场洗稿按原始通稿对待）、UGC/论坛默认不可用（仅限"关于自身"）、聚合平台可靠性取决于被转载的原始来源。来源：[Wikipedia: Identifying reliable sources（官方方针页，已核验）](https://en.wikipedia.org/wiki/Wikipedia:Identifying_reliable_sources)。

**适用性判断**：PageRank/HITS/TrustRank 需要**链接图**和**可投票的边**，我们不满足前提——各政府门户之间基本互不链接，来源数只有 ~20 个，迭代传播没有意义。**这些方法不适合本项目，仅作背景**。但 TrustRank 的"少量人工种子 + 传播"思想有一个弱化版可用：**官方来源作为种子；社区帖链接到官方原文 = 一条可投票的边**，即"可追溯性"本身作为加分项（见 §5.2）。

### 2.4 数据集（供未来训练/校验用，当前不必上）

- **NELA-GT**（Gruppi, Horne & Adalı）：按来源标注的大规模新闻文章数据集，逐年发布（2018–2022）。[arXiv:2203.05659](https://arxiv.org/abs/2203.05659)；仓库 [MELALab/nela-gt](https://github.com/MELALab/nela-gt)。
- **FakeNewsNet**（Shu et al., 2020）：新闻内容 + 社交上下文 + 时空信息的假新闻数据集。*[Big Data 8(3), DOI 10.1089/big.2020.0062](https://doi.org/10.1089/big.2020.0062)*；仓库 [KaiDMML/FakeNewsNet](https://github.com/KaiDMML/FakeNewsNet)（已核验，1356 stars）。

**反面警示**——Zhou et al. (2021) "Hidden Biases in Unreliable News Detection Datasets"（EACL 2021）：当训练/评测集来源有重叠时，模型靠**记住"站点→标签"映射**就能得高分，干净切分下准确率掉 10%+。对工程上的教训：来源层级信号很强但不能是唯一信号，且评测任何"自动可信度"功能时必须按来源切分。*[DOI 10.18653/v1/2021.eacl-main.211](https://doi.org/10.18653/v1/2021.eacl-main.211)*。

---

## 3. 方向二：交叉验证 / 事实核查

### 3.1 结构化事实核查生态（ClaimReview）

- **ClaimReview**：schema.org 的结构化标记类型（Thing > CreativeWork > Review > ClaimReview），事实核查机构在文章页嵌入 JSON-LD，机器可读地声明"被核查的说法（claimReviewed）、核查者（author）、评级（reviewRating）"。来源：[schema.org/ClaimReview（规范原文，已核验）](https://schema.org/ClaimReview)。
- **Google Fact Check Tools API**：两个子 API——已授权用户可对自己站点读写 ClaimReview 标记；任何人可查询与 [Fact Check Explorer](https://factcheck.google.com) 相同的核查结果集，数据即全网 ClaimReview 标记的聚合，并贡献到 Data Commons（datacommons.org/factcheck/download 可下载全量）。来源：[官方开发者文档（已核验）](https://developers.google.com/fact-check/tools/api)。
- **CLEF CheckThat! Lab**：主张识别、可核查性判断、claim matching（同一说法在不同语料中配对）等任务的常设评测。Overview 论文：Elsayed et al. 2019（*[DOI 10.1007/978-3-030-28577-7_25](https://doi.org/10.1007/978-3-030-28577-7_25)*）、Barrón-Cedeño et al. 2020（*[DOI 10.1007/978-3-030-58219-7_17](https://doi.org/10.1007/978-3-030-58219-7_17)*）。官网 [checkthat.gitlab.io](https://checkthat.gitlab.io/)（本次抓取返回空页，未能核验内容，标注为"地址确认、内容未核验"）。

**关于任务书提到的 DeClarouR 与 TVFactCheck：均未找到一手来源。** DeClarouR 在 arXiv、Crossref、OpenAlex、GitHub、Hugging Face 的检索均为零结果，疑为名称有误或纯二手转述；TVFactCheck 在 OpenAlex/arXiv 检索无果。二者的实际功能（基于 ClaimReview 的声明检索）已被上面的一手来源（schema.org 规范 + Google API + CheckThat!）覆盖，不影响方案设计。

### 3.2 声明抽取与核查工具（开源）

- **ClaimBuster**（Hassan et al., PVLDB 2017）：检测"值得核查的声明"（check-worthiness）的端到端系统，提供 API、数据集与 Docker。*[DOI 10.14778/3137765.3137815](https://doi.org/10.14778/3137765.3137815)*；官网 [idir.uta.edu/claimbuster](https://idir.uta.edu/claimbuster/)（已核验，IDIR Lab, UT Arlington）。
- **FActScore**（Min et al., EMNLP 2023）：把长文本拆成原子事实，计算被可靠知识源支持的原子事实百分比——"细粒度拆解 + 逐条对照知识源"的思路可移植。*[arXiv:2305.14251](https://arxiv.org/abs/2305.14251)*；仓库 [shmsw25/FActScore](https://github.com/shmsw25/FActScore)（已核验，460 stars，官方 EMNLP 2023 实现）。
- **Hoaxy**（Shao et al., CSCW 2016, Indiana University OSoMe）：claim 检索 + 社交传播可视化平台，现并入 OSoMeNet。*[DOI 10.1145/2872518.2890098](https://doi.org/10.1145/2872518.2890098)*；仓库 [osome-iu/hoaxy-backend](https://github.com/osome-iu/hoaxy-backend)（已核验）；站点 [hoaxy.osome.iu.edu](https://hoaxy.osome.iu.edu/)（已核验，重定向至 OSoMeNet）。

### 3.3 立场检测：多源一致性的经典做法

- **Fake News Challenge Stage 1（FNC-1）**：给定一条声明（headline）与一篇文章，判 agree / disagree / discuss / unrelated——这正是"交叉验证"的形式化定义。基线论文：Riedel et al. 2017（*[arXiv:1707.03264](https://arxiv.org/abs/1707.03264)*）；复盘与数据集修正：Hanselowski et al. 2018（*[arXiv:1806.05180](https://arxiv.org/abs/1806.05180)*）。
- **Tan, Friggeri & Adamic, "Lost in Propagation?"**（ICWSM）：从源头跟踪新闻在网上的传播链路，发现事实核查往往发生在多次转载之后——佐证链上的中间节点不是独立来源。*[DOI 10.1609/icwsm.v10i1.14712](https://doi.org/10.1609/icwsm.v10i1.14712)*。

### 3.4 事件共现与新闻聚类

- **GDELT**：全球新闻事件数据库（CAMEO 编码事件表）+ 全局知识图 GKG（人物/组织/地点/主题/情感共现图，每条信息附带同文 EventID 列表）；2.0 版 15 分钟更新、65 种语言，另有 mentions 表记录每条事件被哪些报道提及。来源：[GDELT 官方文档页（已核验）](https://www.gdeltproject.org/data.html)。GDELT 证明"跨来源事件共现"是可工程化的：同一事件的多篇报道通过共现实体聚到一起。
- 学术上的对应问题是 **Topic Detection and Tracking（TDT）** 中的 first story detection / streaming clustering（如 Petrović et al. 关于 Twitter 流式首报检测的工作；Petrović, Osborne & Lavrenko, "Streaming First Story Detection with Application to Twitter", EMNLP 2013——**本次未直接核验原文**，仅 Crossref 见到相关后续论文如 McCreadie et al. 2013 [DOI 10.1109/bigdata.2013.6691620](https://doi.org/10.1109/BigData.2013.6691620)，标注为二手）。

### 3.5 真伪传播的实证结论（决定社区源策略）

- **Rubin et al. 2016**（任务书所指的 Rubin 真值标注工作）："Fake News or Truth? Using Satirical Cues to Detect Potentially Misleading News"——对新闻做真值（truth label）人工标注并研究自动判别。*[COLING 2016, DOI 10.18653/v1/w16-0802](https://doi.org/10.18653/v1/w16-0802)*。相关基础：Lukoianova & Rubin 2014, "Veracity Roadmap: Is Big Data Objective, Truthful and Credible?"（把"真实性"列为大数据质量维度）*[DOI 10.7152/acro.v24i1.14671](https://doi.org/10.7152/acro.v24i1.14671)*。
- **Vosoughi, Roy & Aral (2018, Science)**：对 Twitter 十余年全量数据的分析——**虚假消息传播得比真实消息更深、更快、更广**，且主要因为人的转发而非机器人。*[DOI 10.1126/science.aap9559](https://doi.org/10.1126/science.aap9559)*。对社区源的含义：社区热度不能当作可信度信号，甚至负相关。

**适用性判断**：我们没有 LLM 依赖也没有标注预算，所以走"轻结构化"路线——不抽取自然语言声明，而是**以"事件"为核验单元**（区 × 学校 × 学段 × 政策动作），用 GDELT 式的属性共现做聚类（纯 Python 字典 + 规则即可），用 FNC 式的四分类思想输出"佐证状态"（官方确认 / 多源一致 / 单源未证实 / 冲突）。FActScore 的"拆原子再对照"用于人工复核社区帖时对照官方政策原文。Vosoughi 结论支持我们对社区帖默认"待官方核验"并禁止热度加权。

---

## 4. 方向三：时效性（temporal validity / freshness）

### 4.1 学术：时间感知检索与知识的时间有效期

- **Kanhabua, Blanco & Nørvåg, "Temporal Information Retrieval"**（*Foundations and Trends in IR* 9(2), 2015）：时间感知检索的系统综述，覆盖时间表达式抽取、文档时间戳推断、freshness 与 coverage 两个 web 归档质量指标。*[DOI 10.1561/1500000043](https://doi.org/10.1561/1500000043)*。
- **Campos et al., "Survey of Temporal Information Retrieval and Related Applications"**（*ACM Computing Surveys* 46(2), 2014）：另一篇综述，覆盖时间感知排序与查询的时间意图分类。*[DOI 10.1145/2619088](https://doi.org/10.1145/2619088)*。
- **Dai & Davison, "Capturing page freshness for web search"**（CIKM 2010）：对网页内容随时间变化的实证分析与新鲜度建模——关键观点是 **freshness 是"内容相对其真实世界状态的时效"而非"抓取时间新"**（页面上年久未更新的旧信息抓取再新也不新鲜）。*[DOI 10.1145/1835449.1835658](https://doi.org/10.1145/1835449.1835658)*。
- **时间知识库补全（temporal KG validity）**：把"事实只在时间区间内有效"显式建模。García-Durán, Dumančić & Niepert (EMNLP 2018) 提出 YAGO11k/YAGO15k、ICEWS 系列带时间戳的知识图谱基准（*[DOI 10.18653/v1/d18-1516](https://doi.org/10.18653/v1/d18-1516)*）；Lacroix, Obozinski & Usunier (ICLR 2020) "Tensor Decompositions for Temporal Knowledge Base Completion"（*[arXiv:2004.04926](https://arxiv.org/abs/2004.04926)*，仓库 [facebookresearch/tkbc](https://github.com/facebookresearch/tkbc)，已核验）。**给我们的启发是数据模型而非算法**：每条政策信息应带 `(valid_from, valid_to)` 或"招生年度"属性，检索/展示时过滤或降权，而不是靠发布日期隐式推断。

### 4.2 工业界：freshness 排序的实践公式

- **Google Caffeine**（2010 官方博客）：专为缩短索引延迟设计的增量索引系统，官方博客公告 "Our new search index: Caffeine"。来源：[googleblog.blogspot.com（官方，已核验存在）](https://googleblog.blogspot.com/2010/06/our-new-search-index-caffeine.html)。
- **Google freshness 算法**（2011 官方博客，Nov 3）：官方原文举例：搜 "olympics" 用户要的是下一届而非 1900 年——"Google Search uses a freshness algorithm, designed to give you the most up-to-date results... the most recent information can be from the last week, day or even minute, and depending on the search terms, the algorithm needs to be able to figure out if a result from a week ago about a TV show is recent, or if a result from a week ago about breaking news is stale"。来源：[googleblog.blogspot.com（官方原文，已核验）](https://googleblog.blogspot.com/2011/11/giving-you-fresher-more-recent-search.html)。"Query Deserves Freshness (QDF)" 这一术语本身**未找到 Google 一手文档**（公开解释均来自 Search Engine Land 等二手转述），但 QDF 描述的"按查询意图分类决定新鲜度权重"机制与上述官方文章一致。
- **Hacker News 排名公式（一手源码）**：YC 官方发布的 arc3.1 发行包中 `news.arc`：

  ```scheme
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

学术文献中没有直接针对"招生政策年度周期"的时效性研究（未找到，属常识性领域知识）；最接近的是：CRAAP 把 Currency 列为第一准则（§2.2）、维基百科方针明确"医学等快速演化领域旧来源会被新证据取代"且"突发新闻首发报道常有严重错误，宜等一两天再采信"（§2.2，已核验原文）、Google freshness 博客中"上周的 TV 剧结果算新、上周的突发新闻算旧"的**按主题分时间尺度**思想。北京 K12 的实际周期：政策 4–7 月密集发布、6 月信息采集/派位，8 月后进入静默期——这意味着**时效函数必须按信息类型分别调参，而不是统一半衰期**。

---

## 5. 可落地的方案设计

约束：纯 Python 标准库（零第三方依赖）、每 6 小时离线构建、静态站展示、总信源 ~20 个、社区帖子每天数百条量级。结论先行：**用人工维护的静态来源分级表 + 规则式事件聚类 + 年度感知的时效字段**，三个模块全部可以在 `build.py` 现有流程里加 200 行以内实现。

### 5.1 来源信任权重表（人工维护的配置，非算法）

采用 NewsGuard 式"可检验准则 + 分档"，但准则换成政府场景：

| 档位 | 来源 | 默认权重 w | 判定依据（写入配置的注释） |
|---|---|---|---|
| A0 | 市教委、教育部 | 1.00 | 政策一手发布方 |
| A1 | 区教委门户 | 0.95 | 区级政策一手发布方 |
| A2 | yjrx 义务教育入学服务平台 JSON | 0.95 | 官方结构化数据 |
| B1 | 学校官网（自有域名） | 0.80 | 官方但维护随意、更新滞后 |
| B2 | 统一建站平台（bjhdedu.cn 等） | 0.65 | 官方托管但常有整站搬迁移版 |
| C1 | 社区论坛 | 0.30 | UGC，参照维基百科默认不可作事实来源 |

设计要点：

1. **档位而非连续分数**。van der Bles et al. (2019) 的结论之一是连续精确数字会被过度解读（详见 §6），且我们没有任何证据支持"0.83 与 0.85 有差别"。6 档 + 每档一句理由即可。
2. **可追溯性作为动态修正项**（TrustRank 弱化版）：帖子正文或评论中出现指向 A0–A2 域名的原始链接，w 上浮一档；这是社区数据里唯一可信的"信任投票"。
3. **历史抓取成功率进入评分**（MBFC"存续年限"维度的对应物）：`school-crawler-health.json` 已有连续 404/超时的记录，B1/B2 来源连续 10 次抓取失败 → UI 标"来源失联，数据可能过期"而非直接下线（来源失联本身就是时效性证据）。
4. **不做自动来源打分模型**。Zhou et al. (2021) 表明小规模来源集上训练的"可信度分类器"极易退化为站点记忆；我们来源太少，人工配置就是最优解。

### 5.2 交叉验证：以"事件"为单元的规则式聚类

分两步，均在现有规范化层（community/ 已有 URL/标题/时间/正文指纹去重）之上：

**第一步：转载去重（"通讯社转载不算多来源"）。** 维基百科方针的这条规则直接移植：两篇文章正文 shingle 重叠率 > 0.8（8-gram 集合的 Jaccard，纯 Python `difflib`/集合运算即可）或同 URL 域名 + 标题编辑距离 < 阈值 → 判定为转载，同簇只保留最早一篇 + 记录转载数。这是 Tan et al. "Lost in Propagation" 的工程含义：先剔除传播链中间节点，剩下的才算独立报道。

**第二步：事件聚类（GDELT 共现思想的规则版）。** 事件键 = `区 × 学校（规范化名称）× 学段 × 政策动作类型（关键词表：划片/派位/报名/材料/面谈/摇号/转学…）`；时间窗口 14 天；同键的条目归入同一事件簇。每簇计算：

```text
corroboration = {
  "independent_sources": 去转载后的来源数 n,
  "best_tier": 簇内最高来源档位,
  "status": n>=2 且含 A 档 → "官方确认"
             n>=2 同档一致   → "多源一致"
             n==1 且档位<=B  → "单源待核"
             簇内关键字段冲突 → "信息冲突"
}
```

冲突检测只做结构化字段（日期、人数、材料清单）的精确比对，正文语义冲突不检测（无 LLM 依赖）。

**第三步：社区帖的核验生命周期。** 沿用社区方案里"待官方核验"的既有设计并加两条规则：社区帖发布后 30 天内未与任何 A/B 档事件簇匹配 → 降权到归档区；匹配到 → 显示"已被官方来源佐证"并链接该簇（SIFT 的 Trace to original context，给用户的就是这个链接）。

### 5.3 时效性：按信息类型分尺度的衰减 + 招生年度字段

1. **每条信息绑定招生年度 `policy_year`**（temporal KG 的 `valid_from/valid_to` 的离散简化）：北京 K12 招生年度 ≈ 上年 9 月至当年 8 月，政策在 4–7 月发布。构建时用发布日期推断 + 关键词正则（标题含"20XX 年义务教育入学"）校正。**非当前招生年度的信息不删除但全面降权**，UI 显式标注"往年政策（20XX 年度），仅供参考"——这是本看板相对搜索引擎的最大差异点：Google freshness 解决"分钟级"新鲜度，我们的问题是"年度级"有效期。
2. **排序用的时效衰减按类型分参数**（HN 幂衰减 `score / (Δt + t0)^gravity` 的离散版）：
   - 官方政策原文：不随时间衰减，只按 `policy_year` 切换（政策是陈述性事实，参照 Dai & Davison 的"freshness 是相对真实世界状态"——政策原文在其年度内永远"新鲜"）；
   - 学校通知：半衰期约 90 天；
   - 社区帖：半衰期约 14 天（Vosoughi 传播快失效也快）；
   - 招生关键节点前（4–7 月）所有类型的时间项加权 ×2（Google freshness 博客"按主题分时间尺度"的应用）。
3. **"来源比内容更旧"检测**：B2 统一建站平台常见整站重新上线导致老内容带新时间戳；用页面内出现的政策年度（正文年份正则）与发布时间戳比对，不一致 → 标"疑似旧文重发"。

### 5.4 实现落点（不动架构）

- 数据侧：`build.py` 增加 `trust.py`（来源分级表 + corroboration 计算 + policy_year 推断），输出到 `data.json` / `community-data.json` 的每条记录上附加 `tier`、`policy_year`、`corroboration` 三个字段；聚类状态存 `_cache/events.json` 增量更新。
- 展示侧：`index.html` 渲染徽章（现有"待官方核验"文案已预留位置，见 `community_dashboard_export.py` 链路）。
- 全部用 `json/re/difflib/hashlib/datetime/collections` 标准库；事件聚类是 O(n²) 但 n 为每天数百条，6 小时构建完全可承受。

---

## 6. 加分项：置信度展示如何不误导（HCI / 不确定性传播）

- **van der Bles et al. (2019, Royal Society Open Science), "Communicating uncertainty about facts, numbers and science"**：面向公众传达数值/科学不确定性的系统综述。可借鉴结论：人们会把小数点的精确度误当准确度（**连续分数应改为档位**）；数值不确定性最好与"发生了什么/为什么不确定"的简短叙述一起给（**徽章旁必须有一句话理由**）；完全隐藏不确定性会让用户在错误时机过度信任。*[DOI 10.1098/rsos.181870](https://doi.org/10.1098/rsos.181870)（开放获取）*。
- **Pennycook, Bear, Collins & Rand (2020, Management Science), "The Implied Truth Effect"**：只在**一部分**假新闻上加警示，会让没加警示的假新闻显得更可信（人们把"无标签"误读为"已验证"）。对我们的直接设计约束：**置信度标签要么全量打、要么全不打**，绝不能只给低置信度社区帖打标签而让官方条目裸奔。*[DOI 10.1287/mnsc.2019.3478](https://doi.org/10.1287/mnsc.2019.3478)*。
- **Politi & Street (2010)**：医学共享决策中不确定性沟通的经典框架——不确定性要按"来源"分层讲（数据本身的不确定 vs 判断的不确定）。对应我们区分"来源档位"（我们判断的不确定性）与"待官方核验"（事实本身的不确定性）两个正交标签，不要混成一个总分。*[DOI 10.1111/j.1365-2753.2010.01549.x](https://doi.org/10.1111/j.1365-2753.2010.01549.x)*。
- **可视化综述**：Mehta, "Maybe, Maybe Not: A Survey on Uncertainty in Visualization"（[arXiv:2301.07687](https://arxiv.org/abs/2301.07687)）——如未来在 dashboard 里画趋势图，误差带/置信区间呈现可参考；静态站当前用不到。
- **展示形态建议**（综合上述文献）：每条信息显示——来源档位徽章（颜色三档：官方蓝 / 学校绿 / 社区黄）+ 一句话理由（NewsGuard Nutrition Label 精简版）+ "N 个独立来源"（点击展开簇内全部条目及链接）+ 发布日期与招生年度（过期标灰）+ 冲突时并列显示两方原文链接。不给 0–100 数字。

---

## 7. 参考文献

### 来源可信度评级

1. NewsGuard — Rating Process & Criteria. https://www.newsguardtech.com/ratings/rating-process-criteria/ （官方方法论：9 准则、0–100 分、Nutrition Label）
2. Ad Fontes Media — Methodology. https://adfontesmedia.com/methodology/ （平衡分析师小组 + 文章级评分聚合）
3. Media Bias/Fact Check — Methodology. https://mediabiasfactcheck.com/methodology/ （事实性 0–10 加权体系与档位）
4. The Trust Project — Trust Indicators. https://thetrustproject.org/faq/trust-indicators/ （新闻业 8 项信任指标）
5. Wikipedia — Identifying reliable sources. https://en.wikipedia.org/wiki/Wikipedia:Identifying_reliable_sources （生产级来源分级方针：转载不算多来源、UGC 默认不可用）
6. Brin & Page (1998), The Anatomy of a Large-Scale Hypertextual Web Search Engine. https://doi.org/10.1016/S0169-7552(98)00110-X （PageRank）
7. Kleinberg (1999), Authoritative Sources in a Hyperlinked Environment. https://doi.org/10.1145/324133.324140 （HITS）
8. Gyöngyi et al. (2004), Combating Web Spam with TrustRank. https://doi.org/10.1016/B978-012088469-8/50052-8 （种子信任传播）
9. Kamvar et al. (2003), The EigenTrust Algorithm. https://doi.org/10.1145/775152.775242 （信任分数迭代收敛）
10. Caulfield (2019), SIFT: The Four Moves. https://hapgood.us/2019/06/19/sift-the-four-moves/ （SIFT 信息素养方法）
11. Wineburg & McGrew (2017/2019), Lateral Reading. https://doi.org/10.2139/ssrn.3048994 （专家横向核查行为）
12. Zhou et al. (2021), Hidden Biases in Unreliable News Detection Datasets. https://doi.org/10.18653/v1/2021.eacl-main.211 （来源-标签记忆混淆的警示）

### 交叉验证 / 事实核查

13. schema.org — ClaimReview. https://schema.org/ClaimReview （声明核查的结构化标记规范）
14. Google — Fact Check Tools API. https://developers.google.com/fact-check/tools/api （ClaimReview 聚合检索）
15. Elsayed et al. (2019), CheckThat! at CLEF 2019. https://doi.org/10.1007/978-3-030-28577-7_25 （主张识别/验证评测）
16. Barrón-Cedeño et al. (2020), Overview of CheckThat! 2020. https://doi.org/10.1007/978-3-030-58219-7_17 （含 claim matching 任务）
17. Hassan et al. (2017), ClaimBuster. https://doi.org/10.14778/3137765.3137815 ；官网 https://idir.uta.edu/claimbuster/ （可核查声明识别）
18. Min et al. (2023), FActScore. https://arxiv.org/abs/2305.14251 ；代码 https://github.com/shmsw25/FActScore （原子事实对照知识源）
19. Shao et al. (2016), Hoaxy. https://doi.org/10.1145/2872518.2890098 ；代码 https://github.com/osome-iu/hoaxy-backend （声明传播追踪）
20. Riedel et al. (2017), FNC-1 Stance Detection Baseline. https://arxiv.org/abs/1707.03264 （agree/disagree/discuss/unrelated 四分类）
21. Hanselowski et al. (2018), A Retrospective Analysis of the FNC. https://arxiv.org/abs/1806.05180 （FNC 数据集问题修正）
22. GDELT Project — Data Documentation. https://www.gdeltproject.org/data.html （事件库/GKG 共现、mentions 表）
23. Rubin et al. (2016), Fake News or Truth? https://doi.org/10.18653/v1/w16-0802 （新闻真值标注）
24. Lukoianova & Rubin (2014), Veracity Roadmap. https://doi.org/10.7152/acro.v24i1.14671 （大数据真实性维度）
25. Vosoughi, Roy & Aral (2018), The Spread of True and False News Online. https://doi.org/10.1126/science.aap9559 （虚假信息传播快于真实信息）
26. Tan, Friggeri & Adamic (2016), Lost in Propagation? https://doi.org/10.1609/icwsm.v10i1.14712 （新闻传播链与核查滞后）
27. Shu et al. (2020), FakeNewsNet. https://doi.org/10.1089/big.2020.0062 ；https://github.com/KaiDMML/FakeNewsNet （假新闻多模态数据集）

### 时效性

28. Kanhabua, Blanco & Nørvåg (2015), Temporal Information Retrieval. https://doi.org/10.1561/1500000043 （时间感知检索综述）
29. Campos et al. (2014), Survey of Temporal IR. https://doi.org/10.1145/2619088 （时间意图与排序综述）
30. Dai & Davison (2010), Capturing Page Freshness for Web Search. https://doi.org/10.1145/1835449.1835658 （freshness 相对真实世界状态）
31. García-Durán et al. (2018), Learning Sequence Encoders for Temporal KG Completion. https://doi.org/10.18653/v1/d18-1516 （YAGO11k/15k、ICEWS 基准）
32. Lacroix et al. (2020), Tensor Decompositions for Temporal KG Completion. https://arxiv.org/abs/2004.04926 ；代码 https://github.com/facebookresearch/tkbc （时间区间有效事实建模）
33. Google (2010), Our New Search Index: Caffeine. https://googleblog.blogspot.com/2010/06/our-new-search-index-caffeine.html （增量索引官方公告）
34. Google (2011), Giving You Fresher, More Recent Search Results. https://googleblog.blogspot.com/2011/11/giving-you-fresher-more-recent-search.html （freshness 算法官方说明）
35. Hacker News ranking source (arc3.1 news.arc). http://www.arclanguage.org/arc3.1.tar （一手源码：score/(age+2)^1.8）
36. Reddit hot algorithm source. https://github.com/reddit-archive/reddit/blob/master/r2/r2/lib/db/_sorts.pyx （一手源码：log10 分数 + 时间项）

### 不确定性传播 / 展示

37. van der Bles et al. (2019), Communicating Uncertainty about Facts, Numbers and Science. https://doi.org/10.1098/rsos.181870 （面向公众的不确定性传达综述）
38. Pennycook, Bear, Collins & Rand (2020), The Implied Truth Effect. https://doi.org/10.1287/mnsc.2019.3478 （部分打标签的反效果）
39. Politi & Street (2010). https://doi.org/10.1111/j.1365-2753.2010.01549.x （共享决策中的不确定性沟通）
40. Mehta (2023), Maybe, Maybe Not: A Survey on Uncertainty in Visualization. https://arxiv.org/abs/2301.07687 （可视化中的不确定性综述）

### 明确未找到一手来源的项

- **DeClarouR**：arXiv / Crossref / OpenAlex / GitHub / Hugging Face 检索均为零结果，仅二手提及；其功能（ClaimReview 声明检索）由 §3.1 一手来源覆盖。
- **TVFactCheck**：OpenAlex / arXiv 检索无果，未取得一手来源。
- **AllSides 方法论页面**：域名在本次调研网络下不可达（DNS 异常），仅有二手转述。
- **CRAAP Test 官方页面**（CSU Chico Meriam Library）：同样不可达，仅确认 Blakeslee (2004), *LOEX Quarterly* 31(3) 书目。
- **Query Deserves Freshness (QDF)**：无 Google 一手文档；机制由 2011 官方 freshness 博文（文献 34）佐证。
- **"HILL"算法**：未检索到该名称的算法，疑为 HITS（文献 7）之误记。
- **TDT / first story detection（Petrović et al.）原文**：本次未能直接核验，标注为二手。
