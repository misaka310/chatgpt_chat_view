import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


def ts_utc(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc).timestamp())


class AnalyzeGpt3hLimitTest(unittest.TestCase):
    def test_detects_161_user_messages_inside_three_hours(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_dir = temp / "input"
            output_dir = temp / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            base_ts = ts_utc(2026, 6, 1, 0, 0, 0)
            mapping = {}
            for idx in range(161):
                mapping[f"m{idx:03d}"] = {
                    "id": f"n{idx:03d}",
                    "message": {
                        "id": f"msg-{idx:03d}",
                        "author": {"role": "user"},
                        "create_time": base_ts + idx * 60,
                        "content": {"parts": [f"message {idx}"]},
                    },
                }

            data = [
                {
                    "conversation_id": "limit-test",
                    "title": "3h limit burst",
                    "mapping": mapping,
                }
            ]
            (input_dir / "conversations.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )

            cmd = [
                sys.executable,
                str(repo_root / "analyze_gpt_3h_limit.py"),
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
                "--timezone",
                "Asia/Tokyo",
                "--threshold",
                "160",
                "--window-hours",
                "3",
            ]
            completed = subprocess.run(
                cmd,
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"script failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )

            summary_path = output_dir / "gpt_3h_limit_summary.json"
            self.assertTrue(summary_path.exists(), "summary JSON was not generated")
            report = json.loads(summary_path.read_text(encoding="utf-8"))
            summary = report["summary"]
            self.assertEqual(summary["total_user_messages_counted"], 161)
            self.assertEqual(summary["max_3h_user_messages"], 161)
            self.assertTrue(summary["reached_threshold"])
            self.assertTrue(summary["exceeded_threshold"])
            self.assertEqual(summary["over_threshold_by"], 1)

            for filename in (
                "gpt_3h_limit_summary.md",
                "gpt_3h_limit_monthly.csv",
                "gpt_3h_limit_daily.csv",
                "gpt_3h_limit_windows.csv",
            ):
                self.assertTrue((output_dir / filename).exists(), f"{filename} was not generated")

            with (output_dir / "gpt_3h_limit_daily.csv").open("r", encoding="utf-8", newline="") as f:
                daily_rows = list(csv.DictReader(f))
            self.assertEqual(len(daily_rows), 1)
            self.assertEqual(daily_rows[0]["max_3h_user_messages"], "161")
            self.assertEqual(daily_rows[0]["exceeded_threshold"], "True")

    def test_exact_160_reaches_but_does_not_exceed_threshold(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_dir = temp / "input"
            output_dir = temp / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            base_ts = ts_utc(2026, 6, 1, 0, 0, 0)
            mapping = {
                f"m{idx:03d}": {
                    "id": f"n{idx:03d}",
                    "message": {
                        "id": f"msg-{idx:03d}",
                        "author": {"role": "user"},
                        "create_time": base_ts + idx * 60,
                        "content": {"parts": [f"message {idx}"]},
                    },
                }
                for idx in range(160)
            }
            data = [{"conversation_id": "limit-test", "title": "exact limit", "mapping": mapping}]
            (input_dir / "conversations.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )

            cmd = [
                sys.executable,
                str(repo_root / "analyze_gpt_3h_limit.py"),
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
                "--timezone",
                "Asia/Tokyo",
            ]
            completed = subprocess.run(
                cmd,
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"script failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            report = json.loads((output_dir / "gpt_3h_limit_summary.json").read_text(encoding="utf-8"))
            summary = report["summary"]
            self.assertEqual(summary["max_3h_user_messages"], 160)
            self.assertTrue(summary["reached_threshold"])
            self.assertFalse(summary["exceeded_threshold"])
            self.assertEqual(summary["over_threshold_by"], 0)


if __name__ == "__main__":
    unittest.main()
