# K12 信源看板

[在线查看](https://xian492.github.io/k12-dashboard/)

北京 K12 官方信息入口与动态看板，附家长社区信源视图，GitHub Pages 托管。

当前覆盖：

- 北京市教委、教育部及北京 18 个区的官方信息
- 区教委与学校动态
- 149 个学校官网或官方入口
- 学校及区级微信公众号 ID
- 社区信源看板：北京/上海/广州三城市论坛的升学讨论线索（标注"待官方核验"）

## 更新机制

**抓取只在本地跑，CI 只负责部署。** 原因：GitHub 托管 runner 在海外，区教委
与多数学校站拒境外流量（实测 CI 上区在线 0/18，本地 18/18），海外抓取产出的
看板大面积空缺。

| 环节 | 在哪跑 | 触发 |
|---|---|---|
| 官方信源 + 社区全量抓取 | 本地 `tools/local_refresh.sh` | launchd 定时（北京 02/08/14/20 点）或手动 |
| 提交推送 `docs/` | 同上（脚本末尾自动） | 抓取完成后 |
| Pages 部署 | GitHub Actions `frontend-build.yml` | push 到 main（docs 变更） |

质量护栏：`local_refresh.sh` 在区在线 <14/18 或学校 <100 所时中止推送，
避免把故障期的降级数据发上线。应急时可在 Actions 手动触发 `Build dashboard`
（仅海外可达的市级信源可用，区级/学校数据会缺失）。

## 本地构建

```bash
.venv/bin/python tools/build.py            # 完整构建：抓取全部信源并重建页面
.venv/bin/python tools/build.py --offline  # 仅重渲染页面：用既有快照，不联网不抓取
bash tools/local_refresh.sh                # 定时脚本：抓取+护栏+提交推送（--skip-forum 跳过论坛）
```

纯前端改动：本地跑 `--offline` 重出页面后提交，推送由
`frontend-build.yml` 轻量部署，不触发全量抓取。

## 社区信源工作区

论坛、家长社区和地方生活论坛的采集与分析独立放在 [`community/`](community/)，
有自己的 [README](community/README.md)、分析方案、工具链和测试，产出经
`community_forum_adapter.py` 适配后并入看板社区视图，不进入官方 RSS。

## 目录结构

```text
.github/workflows/build.yml           应急全量构建（手动触发；海外抓取有缺失）
.github/workflows/frontend-build.yml  Pages 部署（不抓取，push 即部署）
tools/build.py                        官方信源、学校目录与页面构建
tools/school_crawler.py               学校官网动态抓取与链接筛选
tools/local_refresh.sh                本地定时刷新入口（抓取+护栏+提交）
tools/com.k12-dashboard.local-refresh.plist  launchd 调度配置
community/                            社区信源采集与分析（独立 README）
docs/index.html                       看板页面（已渲染产物，随仓库部署）
docs/搭建记录.md                       看板数据覆盖与筛选原则的详细说明
docs/设计方案-信息置信度与时效性.md     置信度三层模型设计
docs/research-信息可信度与时效性验证.md 上述设计的文献调研笔记
docs/分析-社区信源层溯源去重与聚簇.md   社区层数据画像与问题定义
docs/superpowers/                     开发过程的设计稿与执行计划存档
```

## 版本控制约定

入库：代码、测试、报告与设计文档、看板已渲染页面（`docs/index.html`）、
论坛原始抓取存档（`community/data/community_forum_posts.jsonl`，重抓会被
站点限流，不可简单再生）。

不入库（`.gitignore`）：本地环境（`.venv/`、`.uv-python/`）、全部可再生
中间产物（`docs/data.json`、`community/data/` 各级清洗富集 JSON）。这些
由 `local_refresh.sh` 重跑即可生成。

## 测试

```bash
for f in tests/test_*.py community/tests/test_*.py; do .venv/bin/python "$f"; done
```

## 工作边界

看板只聚合公开信息，不采集需要登录的内容，不绕过验证码或反爬措施；社区
内容统一标注"待官方核验"，不进入官方 RSS。
