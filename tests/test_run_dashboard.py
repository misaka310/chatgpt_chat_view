import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RunDashboardTest(unittest.TestCase):
    def test_direct_pipeline_generates_dashboard(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        sample_src = repo_root / "tests" / "fixtures" / "conversations.sample.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_dir = temp / "input"
            output_dir = temp / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sample_src, input_dir / "conversations.json")

            commands = [
                [sys.executable, str(repo_root / "src" / "analyze_chat_export.py"), "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--timezone", "Asia/Tokyo", "--rebuild"],
                [sys.executable, str(repo_root / "src" / "analyze_gpt_3h_limit.py"), "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--timezone", "Asia/Tokyo", "--threshold", "160", "--window-hours", "3"],
                [sys.executable, str(repo_root / "scripts" / "patch_3h_html.py"), "--output-dir", str(output_dir)],
                [sys.executable, str(repo_root / "scripts" / "inject_3h_into_dashboard.py"), "--output-dir", str(output_dir)],
                [sys.executable, str(repo_root / "scripts" / "patch_dashboard_daily_chart.py"), "--output-dir", str(output_dir)],
            ]
            for cmd in commands:
                completed = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
                self.assertEqual(completed.returncode, 0, msg=f"script failed:\ncmd: {cmd}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")

            self.assertTrue((output_dir / "dashboard.html").exists())
            self.assertTrue((output_dir / "gpt_3h_limit.html").exists())
            self.assertFalse((output_dir / "index.html").exists())

            dashboard_html = (output_dir / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("ChatGPT 利用ダッシュボード", dashboard_html)
            self.assertIn("3時間160チェック", dashboard_html)
            self.assertIn("dashboard-layout-fit:start", dashboard_html)

            limit_html = (output_dir / "gpt_3h_limit.html").read_text(encoding="utf-8")
            self.assertIn("ダッシュボードに戻る", limit_html)
            self.assertNotIn("false", limit_html)

            summary = json.loads((output_dir / "dashboard_summary.json").read_text(encoding="utf-8"))
            self.assertIn("monthly", summary)


if __name__ == "__main__":
    unittest.main()
