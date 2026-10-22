import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


class CommunityWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_keeps_six_hour_schedule_and_runs_community_before_official_build(self):
        self.assertIn("cron: '0 */6 * * *'", self.workflow)
        community_pos = self.workflow.index("Community refresh")
        build_pos = self.workflow.index("python tools/build.py")
        self.assertLess(community_pos, build_pos)
        self.assertIn("community/tools/community_crawler.py", self.workflow)
        self.assertIn("community/tools/community_content_crawler.py", self.workflow)
        self.assertIn("community/tools/community_pipeline.py", self.workflow)
        self.assertIn("--detail-pages-attempted", self.workflow)

    def test_community_failure_is_non_blocking_and_keeps_pages_upload(self):
        community_pos = self.workflow.index("Community refresh")
        build_pos = self.workflow.index("python tools/build.py")
        upload_pos = self.workflow.index("actions/upload-pages-artifact@v3")
        self.assertIn("continue-on-error: true", self.workflow[community_pos:build_pos])
        self.assertLess(build_pos, upload_pos)
        self.assertIn("docs/community-data.json", self.workflow)
        self.assertIn("docs/community-status.json", self.workflow)


if __name__ == "__main__":
    unittest.main()
