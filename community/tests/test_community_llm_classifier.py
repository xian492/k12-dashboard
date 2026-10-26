"""LLM 分类器单测：mock API 响应，不打真实网络。"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock
from tempfile import TemporaryDirectory

TOOLS = Path(__file__).resolve().parents[1] / "tools"
_spec = importlib.util.spec_from_file_location(
    "community_llm_classifier", TOOLS / "community_llm_classifier.py"
)
clf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clf)


class LlmClassifierTests(unittest.TestCase):
    def _records(self):
        return [
            {"link": "https://x/1", "title": "孩子作业写得慢", "content_type": "其他", "stage": []},
            {"link": "https://x/2", "title": "海淀小升初派位规则", "content_type": "政策与流程", "stage": ["小升初"]},
        ]

    def test_needs_llm_flags_low_confidence_only(self):
        recs = self._records()
        self.assertTrue(clf.needs_llm(recs[0]))
        self.assertFalse(clf.needs_llm(recs[1]))

    def test_classify_applies_llm_result_and_caches(self):
        fake = (
            '[{"id": "0", "content_type": "亲子生活", "stage": "综合", "events": ["家庭教育"]}]'
        )
        with TemporaryDirectory() as tmp:
            with mock.patch.object(clf, "CACHE_PATH", Path(tmp) / "cache.json"), \
                 mock.patch.object(clf, "_api_config", lambda: ("http://fake", "k", "m")), \
                 mock.patch.object(clf, "_call_llm", lambda *a, **k: fake):
                recs = self._records()
                updated, status = clf.classify_records(recs)
                self.assertIn("applied 1", status)
                self.assertEqual(recs[0]["content_type"], "亲子生活")
                self.assertEqual(recs[0]["stage"], ["综合"])
                self.assertEqual(recs[0]["event_type"], ["家庭教育"])
                self.assertTrue(recs[0].get("llm_classified"))
                # 高置信条目不动
                self.assertEqual(recs[1]["content_type"], "政策与流程")
                # 第二次调用走缓存，不再请求 API
                calls = []
                with mock.patch.object(clf, "_call_llm", lambda *a, **k: calls.append(1) or fake):
                    clf.classify_records(self._records())
                self.assertEqual(calls, [])

    def test_parse_rejects_invalid_labels(self):
        raw = '[{"id": "0", "content_type": "乱来", "stage": "也乱来", "events": ["x"]}]'
        out = clf._parse_response(raw, ["0"])
        self.assertEqual(out, {})

    def test_negative_cache_prevents_retry(self):
        """LLM 未返回的条目写负面缓存，重跑不再计费。"""
        with TemporaryDirectory() as tmp:
            with mock.patch.object(clf, "CACHE_PATH", Path(tmp) / "cache.json"), \
                 mock.patch.object(clf, "_api_config", lambda: ("http://fake", "k", "m")), \
                 mock.patch.object(clf, "_call_llm", lambda *a, **k: "not json"):
                clf.classify_records(self._records())
                cache = json.loads((Path(tmp) / "cache.json").read_text())
                self.assertEqual(len(cache), 1)
                self.assertIsNone(list(cache.values())[0]["content_type"])


if __name__ == "__main__":
    unittest.main()
