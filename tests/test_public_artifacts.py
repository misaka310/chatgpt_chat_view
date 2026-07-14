import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class PublicArtifactsTest(unittest.TestCase):
    def test_static_demo_contains_only_needed_synthetic_assets(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            generated = temp / "generated"
            published = temp / "published"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "scripts" / "build_sample_output.py"),
                    "--output-dir",
                    str(generated),
                    "--publish-dir",
                    str(published),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertEqual(
                {path.name for path in published.iterdir()},
                {"index.html", "dashboard.html", "gpt_3h_limit.html", "dashboard_summary.json", "dashboard_daily.json"},
            )
            self.assertFalse((published / "conversations.json").exists())
            self.assertFalse((published / "input").exists())
            dashboard = (published / "dashboard.html").read_text(encoding="utf-8")
            limit = (published / "gpt_3h_limit.html").read_text(encoding="utf-8")
            self.assertIn("Synthetic sample data / 合成サンプルデータ", dashboard)
            self.assertIn("Synthetic sample data / 合成サンプルデータ", limit)
            self.assertIn('href="gpt_3h_limit.html"', dashboard)
            self.assertIn("dashboard.html", limit)
            self.assertIn("dashboard_summary.json", dashboard)
            self.assertIn("dashboard_daily.json", dashboard)
            json.loads((published / "dashboard_summary.json").read_text(encoding="utf-8"))

    def test_benchmark_smoke_writes_deterministic_result(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_name:
            report = Path(temp_name) / "benchmark.json"
            completed = subprocess.run(
                [sys.executable, str(repo_root / "scripts" / "benchmark_large_export.py"), "--messages", "100", "--report-file", str(report)],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(payload["success"])
            self.assertEqual(payload["messages"], 100)
            self.assertEqual(payload["conversations"], 1)
            self.assertGreater(payload["input_file_bytes"], 0)
            self.assertGreater(payload["output_bytes"], 0)

    def test_local_server_uses_loopback_address(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "scripts" / "open_dashboard.py"
        spec = importlib.util.spec_from_file_location("open_dashboard", module_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        captured = {}

        class FakeServer:
            def __init__(self, address, handler):
                captured["address"] = address

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                captured["closed"] = True

        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name)
            (output / "dashboard.html").write_text("ok", encoding="utf-8")
            current_dir = Path.cwd()
            try:
                with patch.object(module, "ThreadingHTTPServer", FakeServer), patch.object(module.webbrowser, "open"):
                    module.serve(output, 8733, "dashboard.html")
            finally:
                os.chdir(current_dir)
        self.assertEqual(captured["address"][0], "127.0.0.1")
        self.assertTrue(captured["closed"])


if __name__ == "__main__":
    unittest.main()
