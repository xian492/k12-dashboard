# 全量学校官网 Crawl4AI 接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有学校目录中的全部官网纳入 Crawl4AI 采集，并把稳定抽取到的学校动态接入现有看板、RSS 和 GitHub Pages 定时部署。

**Architecture:** 复用现有学校目录作为唯一入口，自动生成每校允许域名；Crawl4AI 先探测首页和候选栏目，再抓取有限数量的文章详情页。采集结果经过学校归属、日期、过滤和去重后，作为 `build.py` 的学校动态输入；无法抓取的学校保留官网入口和健康状态，不阻断整体构建。

**Tech Stack:** Python 3.12、Crawl4AI 0.9.5、Playwright/Chromium、现有标准库构建脚本、`unittest`、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-10-22-school-official-crawl4ai-design.md`

## Global Constraints

- 本阶段只处理学校官方官网，不处理论坛、家长社区、公众号或其他第三方信源。
- 不抓取需要登录、验证码或绕过访问控制的内容。
- 不无限制遍历学校域名；每校只抓官网入口、最多 5 个候选栏目和每栏有限的最近文章。
- 不默认使用 LLM 生成或改写学校新闻。
- 单个学校失败不影响其他学校、官方区级信源和页面发布。
- 没有真实动态时只保留学校官网入口，不生成占位信息。
- GitHub Actions 使用 Python 3.12，并缓存 Crawl4AI 浏览器依赖。

## Review Focus

- 学校目录中的 HTTP、历史域名和不可访问链接：应记录失败，不让构建失败。
- 官网跳转到官方新域名或子域名：应保留最终 URL，并允许最终官方域名的同域链接。
- 首页把文章详情链接和栏目链接混在一起：应只把栏目页作为栏目候选。
- 列表页没有日期或详情页日期格式不统一：应保留条目并正确标记日期来源。
- Crawl4AI 运行时间过长或浏览器安装失败：应输出可诊断错误，并让已有官方数据照常发布。

### Task 1: 从现有学校目录生成全量 Crawl4AI 配置

**Files:**
- Modify: `tools/school_crawler.py`
- Modify: `tools/probe_school_websites.py`
- Test: `tests/test_school_crawler.py`

**Interfaces:**
- Produces `build_school_probe_specs(catalog: dict) -> list[dict]`。
- Each spec contains `school`, `district`, `homepage`, `allowed_hosts`, `enabled`。
- Consumes the existing `build.SCHOOL_CATALOG` and preserves the exact school homepage configured there.
- The probe CLI consumes the generated full catalog specs instead of the six-school sample list.

- [ ] **Step 1: Write failing tests**

  测试能从代表性区县目录生成所有学校配置、保留学校和区县、从主页提取初始 host、过滤空链接和 `javascript:` 链接，并保留重复学校只出现一次。

- [ ] **Step 2: Run focused tests to verify failure**

  Run: `.venv/bin/python -m unittest tests.test_school_crawler -v`

  Expected: FAIL，因为全量配置生成接口尚未存在。

- [ ] **Step 3: Implement catalog-to-spec generation**

  使用 `urllib.parse.urlparse` 解析主页 host；允许 `www` 与非 `www` 形式以及明确的官方子域名；无 HTTP(S) 主页的学校设为 `enabled=False`，但保留在结果中供健康报告使用。

- [ ] **Step 4: Run focused and full tests**

  Run: `.venv/bin/python -m unittest discover -s tests -v`

  Expected: 全部 PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add tests/test_school_crawler.py tools/school_crawler.py
  git commit -m "feat: derive crawler specs from school catalog"
  ```

### Task 2: 抓取栏目页和文章详情

**Files:**
- Modify: `tools/school_crawler.py`
- Test: `tests/test_school_crawler.py`

**Interfaces:**
- Produces `async crawl_school_updates(crawler, spec: dict) -> dict`。
- Produces `extract_article_links(links: list[dict], section_url: str, limit: int = 10) -> list[dict]`。
- Produces `normalize_school_item(item: dict, spec: dict, source_url: str) -> dict | None`。
- Result contains `updates`, `status`, `error`, `candidate_sections`, `checked_at`。

- [ ] **Step 1: Write failing tests**

  测试从栏目页链接中排除导航和外链、限制最近文章数量、抽取详情页标题/日期/原链接、日期缺失时标记 `date_source=crawl`，以及详情页失败时保留列表标题但不伪造正文。

- [ ] **Step 2: Run focused tests to verify failure**

  Run: `.venv/bin/python -m unittest tests.test_school_crawler -v`

  Expected: FAIL，因为文章抽取接口尚未存在。

- [ ] **Step 3: Implement bounded two-level crawl**

  首页探测最多使用 5 个栏目；每栏最多抓 10 个文章链接；详情页只访问同一允许域名。使用 Crawl4AI 的 CSS 结构化提取和通用链接启发式，不启用 LLM。每校设置独立超时，详情页异常只影响该条目。

- [ ] **Step 4: Run focused and full tests**

  Run: `.venv/bin/python -m unittest discover -s tests -v`

  Expected: 全部 PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add tests/test_school_crawler.py tools/school_crawler.py
  git commit -m "feat: crawl school update details"
  ```

### Task 3: 接入现有构建和 RSS

**Files:**
- Modify: `tools/build.py`
- Modify: `tools/school_crawler.py`
- Modify: `tests/test_build.py`
- Modify: `tests/test_school_crawler.py`

**Interfaces:**
- Produces `collect_crawl4ai_school_updates() -> tuple[dict, dict]`，分别返回按学校归属的动态和学校健康报告。
- `build.py` 只合并成功且经过过滤的学校动态；现有 `SCHOOL_SPECS` 和区级官方补充继续作为回退。

- [ ] **Step 1: Write failing integration tests**

  测试 Crawl4AI 动态能进入对应学校、不覆盖已有可靠官方动态、失败学校不产生占位条目、健康报告可序列化，并且学校官网导航信息不进入 RSS。

- [ ] **Step 2: Run focused tests to verify failure**

  Run: `.venv/bin/python -m unittest tests.test_build tests.test_school_crawler -v`

  Expected: FAIL，因为 `build.py` 尚未调用 Crawl4AI 学校采集。

- [ ] **Step 3: Implement isolated build integration**

  在构建过程中调用学校采集；按学校名和区县合并结果；采集异常转为健康报告，不向上抛出阻断官方构建。将健康报告写入 `docs/school-crawler-health.json`，学校动态继续使用现有页面和 RSS 渲染路径。

- [ ] **Step 4: Run the full suite**

  Run: `.venv/bin/python -m unittest discover -s tests -v`

  Expected: 全部 PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add tools/build.py tools/school_crawler.py tests/test_build.py tests/test_school_crawler.py
  git commit -m "feat: integrate Crawl4AI school updates into dashboard"
  ```

### Task 4: 修改 GitHub Actions 并验证干净构建

**Files:**
- Modify: `.github/workflows/build.yml`
- Create: `requirements-crawl4ai.txt`
- Modify: `.gitignore`
- Test: `tests/test_build.py`

**Interfaces:**
- Actions 在 Ubuntu runner 上使用 Python 3.12，安装固定的 Crawl4AI 版本，运行 `crawl4ai-setup`，缓存 Playwright/Chromium 目录后执行现有构建和 Pages 发布。
- 本地临时探测报告、Crawl4AI 日志、浏览器缓存和 Python 缓存不得进入提交。

- [ ] **Step 1: Write failing workflow/config tests**

  测试依赖文件包含 `crawl4ai==0.9.5`，工作流包含 Python 3.12、依赖安装、`crawl4ai-setup`、缓存步骤，并保留 Pages 上传和部署步骤。

- [ ] **Step 2: Run focused tests to verify failure**

  Run: `.venv/bin/python -m unittest tests.test_build -v`

  Expected: FAIL，因为当前工作流没有 Crawl4AI 安装配置。

- [ ] **Step 3: Implement dependency and workflow setup**

  使用 `actions/setup-python@v5` 和 `actions/cache@v4`；安装依赖后执行浏览器 setup；保留现有权限、并发控制、构建提交和 Pages 发布步骤。

- [ ] **Step 4: Run a local full build and test suite**

  Run: `.venv/bin/python -m unittest discover -s tests -v && .venv/bin/python tools/build.py`

  Expected: 测试全绿，构建完成并生成 `docs/index.html`、`docs/feed.xml` 和健康报告。

- [ ] **Step 5: Commit**

  ```bash
  git add .github/workflows/build.yml requirements-crawl4ai.txt .gitignore tests/test_build.py
  git commit -m "ci: run Crawl4AI school crawler in Pages build"
  ```

### Task 5: 全量探测、人工抽查和发布前验证

**Files:**
- Modify: `tools/school_crawler.py` only when probe findings require source-specific rules
- Create: local `/tmp/all-school-probe.json` only; do not commit

- [ ] **Step 1: Run all-school probe locally**

  Run: `.venv/bin/python tools/probe_school_websites.py --output /tmp/all-school-probe.json`

  Expected: 所有目录学校都有结果；失败学校包含错误原因；单个失败不影响其他学校。

- [ ] **Step 2: Summarize health metrics**

  统计官网访问成功数、发现栏目数、发现动态数、重定向数和连续失败候选；抽查至少 10 所学校的标题、日期和链接是否真实属于该校。

- [ ] **Step 3: Run the final suite and build**

  Run: `.venv/bin/python -m unittest discover -s tests -v && .venv/bin/python tools/build.py`

  Expected: 全部 PASS，页面不出现占位动态，健康报告生成。

- [ ] **Step 4: Commit only source/config changes**

  不提交 `/tmp` 报告、浏览器缓存、日志、`docs/data.json` 或 Python 缓存。

## Rollout Boundary

本计划会把全量学校纳入一次构建尝试，但只有成功识别并通过过滤的内容进入看板。任何学校官网失败、结构不识别或需要登录时，保留其官网导航并在健康报告中记录，不阻塞 GitHub Pages 发布。
