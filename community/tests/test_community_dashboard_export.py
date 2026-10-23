import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "community_dashboard_export", ROOT / "tools" / "community_dashboard_export.py"
)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def record(**overrides):
    value = {
        "title": "北京小升初入学指南",
        "link": "https://example.com/post/1",
        "source": "示例社区",
        "region": "北京",
        "district_candidates": ["海淀区"],
        "school_candidates": ["示例中学"],
        "published_at_normalized": "2026-10-22",
        "content_type": "政策与流程",
        "stage": ["小升初"],
        "event_type": ["入学", "报名"],
        "valid_result": True,
        "analysis_eligible": True,
        "body_text": "不应输出的完整正文",
        "author": "不应输出的作者",
        "contact": "不应输出的联系方式",
        "group_qr": "不应输出的群入口",
    }
    value.update(overrides)
    return value


class CommunityDashboardExportTests(unittest.TestCase):
    def test_exports_only_eligible_records_and_public_display_fields(self):
        result = exporter.export_dashboard_data(
            [record(), record(analysis_eligible=False, link="https://example.com/post/2")],
            "2026-10-22T12:00:00+08:00",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["records"][0]["verification_status"], "待官方核验")
        self.assertTrue(result["records"][0]["community_notice"])
        self.assertNotIn("body_text", result["records"][0])
        self.assertNotIn("author", result["records"][0])
        self.assertNotIn("contact", result["records"][0])
        self.assertNotIn("group_qr", result["records"][0])

    def test_rejects_empty_eligible_sample(self):
        with self.assertRaises(exporter.ExportError):
            exporter.export_dashboard_data([record(analysis_eligible=False)], "now")

    def test_deduplicates_repeat_links_and_matching_fingerprints(self):
        fingerprinted = record(
            link="https://example.com/post/1", content_fingerprint="abc123"
        )
        result = exporter.export_dashboard_data(
            [
                fingerprinted,
                record(link="https://example.com/post/1", content_fingerprint="def456"),
                record(link="https://example.com/post/2", content_fingerprint="abc123"),
                record(link="https://example.com/post/3", content_fingerprint=""),
            ],
            "2026-10-22T12:00:00+08:00",
        )

        self.assertEqual(result["record_count"], 2)
        self.assertEqual(
            [item["link"] for item in result["records"]],
            ["https://example.com/post/1", "https://example.com/post/3"],
        )

    def test_cli_writes_valid_json_to_target(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            output_path = Path(directory) / "output.json"
            input_path.write_text(json.dumps([record()], ensure_ascii=False), encoding="utf-8")

            exporter.export_file(input_path, output_path, generated_at="now")

            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
