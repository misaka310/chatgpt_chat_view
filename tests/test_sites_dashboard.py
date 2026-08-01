import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SitesDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]
        module_path = cls.repo_root / "scripts" / "start_sites_dashboard.py"
        spec = importlib.util.spec_from_file_location("start_sites_dashboard", module_path)
        assert spec and spec.loader
        cls.start_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.start_module)

    def setUp(self) -> None:
        self.repo_root = self.__class__.repo_root

    def make_private_output(self, root: Path) -> Path:
        private_output = root / "private-output"
        private_output.mkdir(parents=True)
        summary = {
            "meta": {
                "generated_at": "2026-02-03T10:20:30+09:00",
                "timezone": "Asia/Tokyo",
                "input_files": [r"C:\private\chat.html"],
                "stats": {"total_conversations": 4},
            },
            "monthly": [
                {
                    "month": "2026-01",
                    "user_messages": 10,
                    "non_voice_messages": 8,
                    "voice_messages": 2,
                    "active_days": 2,
                    "non_voice_active_days": 2,
                    "voice_active_days": 2,
                    "conversations": 3,
                    "total_tokens_est": 1000,
                },
                {
                    "month": "2026-02",
                    "user_messages": 7,
                    "non_voice_messages": 5,
                    "voice_messages": 2,
                    "active_days": 1,
                    "non_voice_active_days": 1,
                    "voice_active_days": 1,
                    "conversations": 2,
                    "total_tokens_est": 700,
                },
            ],
        }
        daily = {
            "meta": {"generated_at": "2026-02-03T10:20:30+09:00", "timezone": "Asia/Tokyo"},
            "daily": [
                {
                    "date": "2026-01-02",
                    "month": "2026-01",
                    "day": 2,
                    "user_messages": 6,
                    "non_voice_messages": 5,
                    "voice_messages": 1,
                    "conversations": 2,
                    "total_tokens_est": 600,
                    "daily_top_conversations": [{"conversation_id": "private-id-1", "title": "PRIVATE TITLE ONE"}],
                },
                {
                    "date": "2026-01-03",
                    "month": "2026-01",
                    "day": 3,
                    "user_messages": 4,
                    "non_voice_messages": 3,
                    "voice_messages": 1,
                    "conversations": 1,
                    "total_tokens_est": 400,
                },
                {
                    "date": "2026-02-01",
                    "month": "2026-02",
                    "day": 1,
                    "user_messages": 7,
                    "non_voice_messages": 5,
                    "voice_messages": 2,
                    "conversations": 2,
                    "total_tokens_est": 700,
                },
            ],
        }
        conversations = {
            "conversations": [
                {"conversation_id": "private-id-1", "title": "PRIVATE TITLE ONE"},
                {"conversation_id": "private-id-2", "title": "PRIVATE TITLE TWO"},
            ]
        }
        (private_output / "dashboard_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (private_output / "dashboard_daily.json").write_text(json.dumps(daily), encoding="utf-8")
        (private_output / "dashboard_conversations.json").write_text(json.dumps(conversations), encoding="utf-8")
        return private_output

    def test_node_version_parser_enforces_semantic_triplet(self) -> None:
        self.assertEqual(self.start_module.parse_node_version("v22.13.0"), (22, 13, 0))
        self.assertEqual(self.start_module.parse_node_version("23.1.2-beta.1"), (23, 1, 2))
        with self.assertRaises(SystemExit):
            self.start_module.parse_node_version("unknown")

    def test_builder_emits_only_allowlisted_numeric_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            private_output = self.make_private_output(temp)
            public_root = temp / "public"
            public_root.mkdir()
            shutil.copy2(self.repo_root / "assets" / "favicon.svg", public_root / "favicon.svg")
            data_file = public_root / "usage-data.json"

            build = subprocess.run(
                [
                    sys.executable,
                    str(self.repo_root / "scripts" / "build_sites_dashboard.py"),
                    "--private-output-dir",
                    str(private_output),
                    "--data-file",
                    str(data_file),
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(build.returncode, 0, msg=build.stderr)

            payload = json.loads(data_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["totals"]["sent_messages"], 17)
            self.assertEqual(payload["totals"]["non_voice_messages"], 13)
            self.assertEqual(payload["totals"]["voice_messages"], 4)
            self.assertEqual(payload["totals"]["active_days"], 3)
            self.assertEqual(payload["totals"]["non_voice_active_days"], 3)
            self.assertEqual(payload["totals"]["voice_active_days"], 3)
            self.assertEqual(payload["totals"]["conversation_count"], 4)
            self.assertEqual(payload["monthly"][0]["month"], "2026-01")
            self.assertEqual(len(payload["daily"]), 59)
            self.assertEqual(payload["daily"][0]["date"], "2026-01-01")
            self.assertEqual(payload["daily"][0]["sent_messages"], 0)
            self.assertEqual(payload["daily"][-1]["date"], "2026-02-28")
            public_text = data_file.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE TITLE", public_text)
            self.assertNotIn("private-id", public_text)
            self.assertNotIn("chat.html", public_text)
            self.assertNotIn("C:\\", public_text)

            verify = subprocess.run(
                [
                    sys.executable,
                    str(self.repo_root / "scripts" / "verify_sites_public.py"),
                    "--public-source",
                    str(public_root),
                    "--private-output-dir",
                    str(private_output),
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, msg=verify.stderr or verify.stdout)

    def test_scanner_rejects_private_marker_and_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            private_output = self.make_private_output(temp)
            public_root = temp / "public"
            public_root.mkdir()
            shutil.copy2(self.repo_root / "assets" / "favicon.svg", public_root / "favicon.svg")
            data_file = public_root / "usage-data.json"
            subprocess.run(
                [
                    sys.executable,
                    str(self.repo_root / "scripts" / "build_sites_dashboard.py"),
                    "--private-output-dir",
                    str(private_output),
                    "--data-file",
                    str(data_file),
                ],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (public_root / "leak.txt").write_text("PRIVATE TITLE ONE", encoding="utf-8")
            verify = subprocess.run(
                [
                    sys.executable,
                    str(self.repo_root / "scripts" / "verify_sites_public.py"),
                    "--public-source",
                    str(public_root),
                    "--private-output-dir",
                    str(private_output),
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(verify.returncode, 0)
            self.assertNotIn("PRIVATE TITLE ONE", verify.stdout + verify.stderr)


if __name__ == "__main__":
    unittest.main()
