import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "community_pipeline", ROOT / "tools" / "community_pipeline.py"
)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class CommunityPipelineTests(unittest.TestCase):
    def test_caps_detail_candidates_per_source(self):
        candidates = [
            {"source_id": "xschu", "link": f"https://example.com/{i}"}
            for i in range(130)
        ]
        candidates += [
            {"source_id": "hlgnet", "link": f"https://example.org/{i}"}
            for i in range(80)
        ]

        limited = pipeline.cap_candidates(candidates)

        self.assertEqual(sum(item["source_id"] == "xschu" for item in limited), 100)
        self.assertEqual(sum(item["source_id"] == "hlgnet" for item in limited), 50)
        self.assertEqual(pipeline.PAGE_CAPS["xiaoshengchu-index"], 0)

    def test_writes_capped_candidate_file_for_detail_crawler(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "candidates.json"
            output_path = Path(directory) / "capped.json"
            input_path.write_text(
                json.dumps([
                    {"source_id": "xschu", "link": f"https://example.com/{i}"}
                    for i in range(105)
                ]),
                encoding="utf-8",
            )

            count = pipeline.write_capped_candidates(input_path, output_path)

            self.assertEqual(count, 100)
            self.assertEqual(len(json.loads(output_path.read_text())), 100)

    def test_source_exception_is_recorded_without_stopping_other_sources(self):
        results, errors = pipeline.run_source_jobs(
            {
                "good": lambda: [{"link": "https://example.com/1"}],
                "bad": lambda: (_ for _ in ()).throw(RuntimeError("timeout")),
            }
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [{"source_id": "bad", "error": "timeout"}])

    def test_failed_export_preserves_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "bad.json"
            output_path = Path(directory) / "community-data.json"
            output_path.write_text('{"status":"success","record_count":7}\n', encoding="utf-8")
            input_path.write_text(json.dumps([]), encoding="utf-8")

            result = pipeline.run_community_pipeline(
                enriched_input=input_path,
                output_path=output_path,
                generated_at="now",
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(json.loads(output_path.read_text()) ["record_count"], 7)


if __name__ == "__main__":
    unittest.main()
