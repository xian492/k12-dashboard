# 官方与社区双信源看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有北京 K12 官方看板中增加社区信源视图，并通过 GitHub Actions 每 6 小时自动抓取、清洗、导出和部署社区数据。

**Architecture:** 保持官方 `data.json` 和 `feed.xml` 不变，社区链路从 `community/data/community_beijing_enriched.json` 生成独立的 `docs/community-data.json`。现有页面增加前端下拉切换，社区采集失败时不覆盖上一次成功快照，也不阻断官方看板构建。

**Tech Stack:** Python 3.12、Crawl4AI 0.9.5、现有静态 HTML/CSS/JavaScript、GitHub Actions、unittest。

**Spec:** `docs/superpowers/specs/2026-10-22-community-dashboard-design.md`

## Global Constraints

- 每轮最多访问 6 个入口页 + 420 个详情页，共 426 个页面。
- 首期自动入口只包括北京小升初网、水木社区·儿童教育、北京小升初信息网、回龙观社区网、芍药居社区网和北京小升初升学索引。
- 社区数据不写入官方 `docs/data.json` 官方条目结构，不写入官方 `docs/feed.xml`。
- 社区视图必须显示“社区线索，未经官方核验”的边界提示。
- 只访问公开页面，不登录、不绕过验证码、付费墙、会员限制或反爬措施。
- 社区失败时保留上一次成功展示快照，官方看板仍必须可以构建和部署。
- `docs/community-data.json` 只保存前端展示字段，不保存完整正文、作者资料、联系方式或群入口。

## Review Focus

- 社区展示 JSON 缺失、损坏或有效记录为 0 时，旧快照不被覆盖；测试归入任务 2。
- 单个社区来源超时或反爬时，其他来源和官方页面仍能继续；测试归入任务 3。
- 社区内容不能混入官方 RSS；测试归入任务 4。
- 页面切换后官方内容保持现状，社区视图显示明确边界提示；测试归入任务 4。
- 社区导出不得携带完整正文、用户资料、联系方式和群入口；测试归入任务 1。

---

### Task 1: 社区看板展示数据导出

**Files:**
- Create: `community/tools/community_dashboard_export.py`
- Create: `community/tests/test_community_dashboard_export.py`
- Modify: `community/README.md`

**Interfaces:**
- Consumes: `community/data/community_beijing_enriched.json` records with `analysis_eligible`.
- Produces: `export_dashboard_data(records: list[dict], generated_at: str) -> dict` and a CLI that writes `docs/community-data.json` atomically.

- [ ] **Step 1: Write failing tests**

  Add tests for: selecting only `analysis_eligible=true`; preserving source/title/link/date/type/stage/event/region candidates; adding `verification_status="待官方核验"` and `community_notice=true`; excluding `body_text`, author fields, contact fields, group fields and arbitrary extra fields; rejecting zero eligible records.

- [ ] **Step 2: Run exporter tests and verify failure**

  Run: `python3 -m unittest community.tests.test_community_dashboard_export -v`
  Expected: FAIL because the exporter module and interface do not exist.

- [ ] **Step 3: Implement `export_dashboard_data` and atomic CLI export**

  Use a fixed allowlist of display fields. Write to a temporary sibling file and replace the target only after JSON serialization and validation succeed. Include `generated_at`, `region`, `record_count`, `records`, and `status="success"` in the envelope.

- [ ] **Step 4: Run exporter tests**

  Run: `python3 -m unittest community.tests.test_community_dashboard_export -v`
  Expected: PASS.

- [ ] **Step 5: Document the new display snapshot**

  Update `community/README.md` with the exporter command, `docs/community-data.json` role, and the distinction between full analysis data and the public display projection.

- [ ] **Step 6: Commit**

  ```bash
  git add community/tools/community_dashboard_export.py community/tests/test_community_dashboard_export.py community/README.md
  git commit -m "feat: export community dashboard snapshot"
  ```

### Task 2: Community pipeline orchestration and failure protection

**Files:**
- Create: `community/tools/community_pipeline.py`
- Create: `community/tests/test_community_pipeline.py`
- Modify: `community/tools/community_crawler.py: crawl_beijing` only if needed for bounded candidate output
- Modify: `community/tools/community_content_crawler.py` only if needed for bounded detail input

**Interfaces:**
- Consumes: six configured source entries and the existing crawler/cleaner/enricher/exporter modules.
- Produces: `run_community_pipeline(...) -> dict` with `status`, `generated_at`, `entry_pages`, `detail_pages_attempted`, `valid_records`, `errors`, and `output_path`.

- [ ] **Step 1: Write failing pipeline tests**

  Test the exact page caps: xschu 100, newsmth 50, xscxx 120, hlgnet 50, shaoyaojuwang 100, xiaoshengchu-index 0. Test that a source exception is recorded without stopping other sources. Test that zero valid records or invalid JSON does not replace an existing snapshot.

- [ ] **Step 2: Run pipeline tests and verify failure**

  Run: `python3 -m unittest community.tests.test_community_pipeline -v`
  Expected: FAIL because the orchestration interface does not exist.

- [ ] **Step 3: Implement bounded pipeline**

  Keep network calls in the existing crawler modules. The orchestrator should use a temporary working directory, cap candidate details per source before detail crawling, run cleaner/enricher/exporter, validate the projected JSON, and only then atomically publish the snapshot. Preserve the existing snapshot on any failure and return structured status rather than raising for an individual source.

- [ ] **Step 4: Run pipeline tests**

  Run: `python3 -m unittest community.tests.test_community_pipeline -v`
  Expected: PASS.

- [ ] **Step 5: Run a local dry run against existing data**

  Run the pipeline in no-network/local-input mode against the existing Beijing JSONL and verify it produces the same 150 eligible records without changing the raw or clean files.

- [ ] **Step 6: Commit**

  ```bash
  git add community/tools/community_pipeline.py community/tests/test_community_pipeline.py community/tools/community_crawler.py community/tools/community_content_crawler.py
  git commit -m "feat: orchestrate bounded community refresh"
  ```

### Task 3: GitHub Actions integration and refresh metadata

**Files:**
- Modify: `.github/workflows/build.yml`
- Modify: `tools/build.py` only for reading the community snapshot/status, not for crawling community pages
- Create: `community/tests/test_community_workflow_contract.py` if workflow contract tests are needed

**Interfaces:**
- Consumes: `run_community_pipeline` CLI and the existing official build command.
- Produces: a Pages artifact containing the current official files plus `docs/community-data.json` and a community status file.

- [ ] **Step 1: Write failing contract tests**

  Assert that the workflow keeps the 6-hour cron, installs Crawl4AI before community crawling, invokes the community pipeline, then invokes the official build. Assert that community failure is non-blocking and the official build step still runs.

- [ ] **Step 2: Run contract tests and verify failure**

  Run: `python3 -m unittest community.tests.test_community_workflow_contract -v`
  Expected: FAIL until the workflow contains the required commands and failure handling.

- [ ] **Step 3: Modify workflow**

  Add a community refresh step using a temporary working directory and `continue-on-error`/structured status handling. Do not let a failed community run delete the checked-in or previously generated snapshot. Keep the existing official build and Pages upload steps intact.

- [ ] **Step 4: Add status metadata**

  Emit `docs/community-status.json` with last successful time, current status, attempted pages, valid records, and error summaries. The official build must tolerate a missing community snapshot on the first run.

- [ ] **Step 5: Run workflow contract tests**

  Run: `python3 -m unittest community.tests.test_community_workflow_contract -v`
  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add .github/workflows/build.yml tools/build.py community/tests/test_community_workflow_contract.py
  git commit -m "ci: refresh community sources every six hours"
  ```

### Task 4: Dual-view dashboard UI

**Files:**
- Modify: `tools/build.py` in `HTML_HEAD`, page rendering, and new community rendering helpers
- Modify: `tests/test_build.py`
- Modify: `community/README.md` and `docs/搭建记录.md`

**Interfaces:**
- Consumes: `docs/community-data.json` and optional `docs/community-status.json`.
- Produces: one static `docs/index.html` with official and community views controlled by a select element.

- [ ] **Step 1: Write failing UI/build tests**

  Test that generated HTML contains the official/community selector, community boundary warning, source/title/link fields, and status metadata. Test that official district content remains present. Test that `build_feed` output contains no community record links.

- [ ] **Step 2: Run UI tests and verify failure**

  Run: `python3 -m unittest tests.test_build -v`
  Expected: FAIL for the new selector and community view assertions.

- [ ] **Step 3: Implement community rendering helpers**

  Add a small renderer for grouped community records. Keep the existing official HTML unchanged except for the selector and view containers. Use escaped JSON/HTML values and render community links with source names, dates, labels, and the “待官方核验” status.

- [ ] **Step 4: Implement client-side view switching**

  Default to official view, switch without navigation, preserve the selection in the URL hash or query string, and show a graceful empty/error state when the community snapshot is absent or failed.

- [ ] **Step 5: Run UI/build tests**

  Run: `python3 -m unittest tests.test_build -v`
  Expected: PASS, with existing official tests still passing.

- [ ] **Step 6: Commit**

  ```bash
  git add tools/build.py tests/test_build.py community/README.md docs/搭建记录.md
  git commit -m "feat: add official and community dashboard views"
  ```

### Task 5: End-to-end verification and handoff

**Files:**
- Modify: `community/reports/社区内容采集报告-2026-10-22.md` if final counts or pipeline notes change
- Modify: `community/README.md` with final run and deployment instructions

- [ ] **Step 1: Run all unit tests**

  Run: `python3 -m unittest discover -s community/tests -v && python3 -m unittest discover -s tests -v`
  Expected: all tests pass.

- [ ] **Step 2: Run static local export/build verification**

  Generate `docs/community-data.json`, build the page from existing local snapshots without network access, and verify `docs/index.html`, `docs/community-data.json`, and `docs/community-status.json` exist and contain valid JSON/HTML.

- [ ] **Step 3: Verify data boundaries**

  Check that no `community` record appears in `docs/feed.xml`, that the community projection has no `body_text` or user fields, and that official HTML still contains the existing district sections.

- [ ] **Step 4: Run `git diff --check` and review generated output**

  Inspect the page source and sample community cards for broken links, missing dates, incorrect source names, and misleading official styling.

- [ ] **Step 5: Commit final documentation/test adjustments**

  ```bash
  git add community/reports/社区内容采集报告-2026-10-22.md community/README.md docs/community-data.json docs/community-status.json
  git commit -m "docs: finalize community dashboard operations"
  ```
