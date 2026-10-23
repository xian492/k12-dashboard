import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
FRONTEND_WORKFLOW = ROOT / ".github" / "workflows" / "frontend-build.yml"
LOCAL_REFRESH = ROOT / "tools" / "local_refresh.sh"
PLIST = ROOT / "tools" / "com.k12-dashboard.local-refresh.plist"


class CommunityWorkflowContractTests(unittest.TestCase):
    """新架构契约：抓取在本地定时跑，CI 只部署。

    GitHub 托管 runner 在海外，区教委与多数学校站拒境外流量（实测
    CI 区在线 0/18），因此 build.yml 去掉了定时与推送触发；全链路
    刷新由 local_refresh.sh（launchd 调度）执行并提交 docs/，由
    frontend-build.yml 部署。
    """

    def test_build_workflow_is_manual_only(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("cron:", workflow)
        # 应急通道仍保留社区步骤顺序：社区在官方构建之前
        community_pos = workflow.index("Community refresh")
        build_pos = workflow.index("python tools/build.py")
        self.assertLess(community_pos, build_pos)
        self.assertIn("--detail-pages-attempted", workflow)

    def test_local_refresh_runs_full_chain_with_guard_and_push(self):
        script = LOCAL_REFRESH.read_text(encoding="utf-8")
        # 社区链路顺序与 CI 应急通道一致
        for tool in (
            "community/tools/community_crawler.py",
            "community/tools/community_content_crawler.py",
            "community/tools/community_content_cleaner.py",
            "community/tools/community_content_enricher.py",
            "community/tools/community_forum_crawler.py",
            "community/tools/community_forum_adapter.py",
            "community/tools/community_pipeline.py",
            "tools/build.py",
        ):
            self.assertIn(tool, script)
        crawler_pos = script.index("community_crawler.py")
        build_pos = script.index("tools/build.py")
        self.assertLess(crawler_pos, build_pos)
        # 质量护栏：低于阈值不推送
        self.assertIn("guard FAILED", script)
        # 抓取完成后自动提交推送，由 frontend-build.yml 部署
        self.assertIn("git push origin main", script)

    def test_launchd_schedules_refresh_four_times_daily(self):
        plist = PLIST.read_text(encoding="utf-8")
        self.assertEqual(plist.count("<key>Hour</key>"), 4)
        self.assertIn("local_refresh.sh", plist)

    def test_frontend_workflow_deploys_committed_docs(self):
        workflow = FRONTEND_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/upload-pages-artifact@v3", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        # 只部署已提交的 docs/：不执行构建或抓取步骤
        self.assertNotIn("run: python tools/build.py", workflow)
        self.assertNotIn("requirements-crawl4ai", workflow)


if __name__ == "__main__":
    unittest.main()
