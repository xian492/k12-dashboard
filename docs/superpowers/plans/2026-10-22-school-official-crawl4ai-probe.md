# 学校官网 Crawl4AI 小样本探测实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用 Crawl4AI 对少量北京学校官网进行探测，验证官网访问、栏目发现和动态链接抽取，不改变现有看板发布链路。

**Architecture:** 新增一个独立的学校官网探测器，输入学校官网配置，使用 Crawl4AI 加载首页并提取同域链接；纯函数负责过滤、归一化和候选栏目评分，运行结果写成可审阅的 JSON 报告。第一阶段不接入 `tools/build.py`，不修改学校动态展示。

**Tech Stack:** Python 3.12、Crawl4AI 0.9.5、Playwright/Chromium、现有 `unittest` 测试框架。

**Spec:** `docs/superpowers/specs/2026-10-22-school-official-crawl4ai-design.md`

## Global Constraints

- 本阶段只处理学校官方官网，不处理论坛、家长社区、公众号或其他第三方信源。
- 不抓取需要登录、验证码或绕过访问控制的内容。
- 不无限制遍历学校域名；每校只探测官网入口及有限的同域候选栏目。
- 不默认使用 LLM 生成或改写学校新闻。
- 单个学校失败不影响其他学校。
- 第一阶段不修改现有看板、RSS 和官方信源构建逻辑。

## Review Focus

- 官网重定向到新域名：应保留最终 URL，并依据最终域名判断同域链接。
- 页面只有导航没有新闻：应返回空候选栏目，而不是把导航当作动态。
- 相对链接、查询参数和重复链接：应归一化并去重。
- JS 加载失败或站点超时：应记录失败状态并继续其他学校。
- 外链、登录、备案和联系我们页面：应被过滤，不进入候选栏目。

### Task 1: 建立学校官网探测配置和纯函数

**Files:**
- Create: `tools/school_crawler.py`
- Test: `tests/test_school_crawler.py`

**Interfaces:**
- Produces `SCHOOL_PROBE_SPECS`，包含 5～7 所北京学校的 `school`、`district`、`homepage` 和 `allowed_hosts`。
- Produces `normalize_url(raw_url: str, base_url: str) -> str`。
- Produces `extract_internal_links(links: list[dict], base_url: str, allowed_hosts: set[str]) -> list[dict]`。
- Produces `rank_section_candidates(links: list[dict]) -> list[dict]`。

- [ ] **Step 1: Write failing tests**

  在 `tests/test_school_crawler.py` 中测试：相对 URL 绝对化、同域过滤、外链过滤、登录/备案/联系我们过滤、重复链接去重，以及“新闻/通知/招生/校园动态”等栏目关键词优先排序。

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `python3 -m unittest tests.test_school_crawler -v`

  Expected: FAIL，因为 `tools.school_crawler` 和目标函数尚不存在。

- [ ] **Step 3: Implement the minimal pure functions**

  使用 `urllib.parse.urljoin` 和 `urlparse`；允许配置的官方子域名，拒绝其他域名；只返回包含有效标题和 HTTP(S) URL 的记录。关键词排序只用于候选栏目发现，不把链接直接判定为学校动态。

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run: `python3 -m unittest tests.test_school_crawler -v`

  Expected: PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add tests/test_school_crawler.py tools/school_crawler.py
  git commit -m "feat: add school website probe helpers"
  ```

### Task 2: 接入 Crawl4AI 首页探测

**Files:**
- Modify: `tools/school_crawler.py`
- Test: `tests/test_school_crawler.py`

**Interfaces:**
- Produces `async probe_school(crawler, spec: dict) -> dict`，返回 `school`、`homepage`、`final_url`、`status`、`candidate_sections`、`items_found`、`error` 和 `checked_at`。
- Produces `async probe_schools(specs: list[dict]) -> list[dict]`，限制并发为 2～4 个学校，并隔离单校异常。

- [ ] **Step 1: Write failing tests**

  增加不依赖真实网络的异步测试，使用最小 crawler stub 返回成功、重定向、失败三种结果，验证结果字段完整、失败学校不会抛出到批量调用方，以及候选栏目来自同域链接。

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `python3 -m unittest tests.test_school_crawler -v`

  Expected: FAIL，因为异步探测接口尚未实现。

- [ ] **Step 3: Implement Crawl4AI integration**

  使用一个共享的 `AsyncWebCrawler`，为每校创建独立 `CrawlerRunConfig`，启用同域链接过滤、有限页面超时和缓存；从 `result.links` 或等价的 Crawl4AI 结果字段提取候选栏目。对 `result.success=False`、超时和异常统一转换为失败报告，不重试到阻塞整个批次。

- [ ] **Step 4: Run focused tests and then the full suite**

  Run: `python3 -m unittest tests.test_school_crawler -v`

  Expected: PASS。

  Run: `python3 -m unittest discover -s tests -v`

  Expected: 现有测试和新测试全部 PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add tests/test_school_crawler.py tools/school_crawler.py
  git commit -m "feat: probe school websites with Crawl4AI"
  ```

### Task 3: 增加本地探测命令和报告输出

**Files:**
- Modify: `tools/school_crawler.py`
- Create: `tools/probe_school_websites.py`
- Test: `tests/test_school_crawler.py`

**Interfaces:**
- CLI: `python tools/probe_school_websites.py --output /tmp/school-probe.json`。
- 报告为 JSON 数组，每个学校一条结果；失败结果也保留。

- [ ] **Step 1: Write failing tests**

  测试报告序列化保留成功、失败和时间字段，并验证 CLI 参数缺失时给出非零退出码；测试不得访问真实学校官网。

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `python3 -m unittest tests.test_school_crawler -v`

  Expected: FAIL，因为 CLI 和报告函数尚未实现。

- [ ] **Step 3: Implement the CLI**

  使用 `argparse`，默认输出到 `reports/school-probe.json`；创建父目录，使用 UTF-8 和 `ensure_ascii=False` 写入；运行结束时打印成功数、失败数和候选栏目数。

- [ ] **Step 4: Run a real small-sample probe**

  Run: `source .venv/bin/activate && python tools/probe_school_websites.py --output /tmp/school-probe.json`

  Expected: Crawl4AI 能完成样本学校探测；即使个别学校失败，命令整体仍成功，并在 `/tmp/school-probe.json` 记录失败原因。

- [ ] **Step 5: Review the report manually**

  检查每所学校的最终 URL、候选栏目和失败原因，确认没有把首页导航、联系我们、备案或外链识别成内容栏目。

- [ ] **Step 6: Run the full suite**

  Run: `python3 -m unittest discover -s tests -v`

  Expected: 全部 PASS；本地探测报告不提交到仓库。

- [ ] **Step 7: Commit**

  ```bash
  git add tests/test_school_crawler.py tools/school_crawler.py tools/probe_school_websites.py
  git commit -m "feat: add school website probe command"
  ```

## Out of Scope for This Probe

- 不接入 `tools/build.py`。
- 不修改 GitHub Actions。
- 不生成学校动态或 RSS 条目。
- 不抓取候选栏目下的文章详情页。
- 不迁移或删除现有 `SCHOOL_SPECS`。

