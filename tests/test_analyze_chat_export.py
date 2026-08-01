import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.chat_export_core import is_voice_message


class AnalyzeChatExportTest(unittest.TestCase):
    def test_generates_public_dashboard_outputs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        sample_src = repo_root / "tests" / "fixtures" / "conversations.sample.json"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_dir = temp / "input"
            output_dir = temp / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sample_src, input_dir / "conversations.json")

            cmd = [
                sys.executable,
                str(repo_root / "src" / "analyze_chat_export.py"),
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
                "--timezone",
                "Asia/Tokyo",
                "--rebuild",
            ]
            completed = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, msg=f"script failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")

            expected_files = (
                "parsed_summary.json",
                "monthly_summary.md",
                "conversations_index.csv",
                "category_monthly.csv",
                "category_daily.csv",
                "keywords_monthly.csv",
                "monthly_user_messages.csv",
                "monthly_user_messages_by_mode.csv",
                "monthly_conversations.csv",
                "monthly_active_days.csv",
                "daily_user_messages.csv",
                "daily_user_messages_by_mode.csv",
                "daily_hourly_user_messages.csv",
                "daily_hourly_user_messages_by_mode.csv",
                "daily_conversations.csv",
                "dashboard.html",
                "dashboard_summary.json",
                "dashboard_conversations.json",
                "dashboard_daily.json",
                "dashboard_categories.json",
            )
            for filename in expected_files:
                self.assertTrue((output_dir / filename).exists(), f"{filename} was not generated")

            self.assertFalse((output_dir / "dashboard_codex_match.json").exists())
            self.assertFalse((output_dir / "out").exists())

            parsed = json.loads((output_dir / "parsed_summary.json").read_text(encoding="utf-8"))
            stats = parsed["meta"]["stats"]
            self.assertEqual(stats["total_conversation_objects"], 3)
            self.assertEqual(stats["total_unique_messages"], 5)
            self.assertEqual(stats["total_duplicate_messages_skipped"], 5)
            self.assertEqual(stats["total_conversations"], 2)
            self.assertIn(stats.get("token_estimation_method"), ("tiktoken:o200k_base", "char_fallback_v1"))

            monthly = {row["month"]: row for row in parsed["monthly"]}
            self.assertEqual(monthly["2024-01"]["user_messages"], 2)
            self.assertEqual(monthly["2024-02"]["user_messages"], 1)
            self.assertEqual(monthly["2024-01"]["non_voice_messages"], 2)
            self.assertEqual(monthly["2024-01"]["voice_messages"], 0)
            self.assertEqual(monthly["2024-02"]["non_voice_messages"], 0)
            self.assertEqual(monthly["2024-02"]["voice_messages"], 1)
            self.assertEqual(monthly["2024-01"]["peak_daily_user_messages"], 2)
            self.assertEqual(monthly["2024-01"]["peak_daily_date"], "2024-01-01")

            summary_payload = json.loads((output_dir / "dashboard_summary.json").read_text(encoding="utf-8"))
            self.assertIn("meta", summary_payload)
            self.assertIn("monthly", summary_payload)
            self.assertNotIn("conversation_index", summary_payload)

            daily_payload = json.loads((output_dir / "dashboard_daily.json").read_text(encoding="utf-8"))
            self.assertIn("daily", daily_payload)
            for row in daily_payload["daily"]:
                self.assertIn("non_voice_messages", row)
                self.assertIn("voice_messages", row)
                self.assertIn("total_tokens_est", row)

            dashboard_html = (output_dir / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("dashboard_summary.json", dashboard_html)
            self.assertIn("ChatGPT 利用ダッシュボード", dashboard_html)
            self.assertIn("countModeSelect", dashboard_html)
            self.assertIn("音声を除く", dashboard_html)
            self.assertNotIn("Codex", dashboard_html)


class VoiceMessageDetectionTest(unittest.TestCase):
    def test_detects_bidirectional_voice_metadata(self) -> None:
        self.assertTrue(is_voice_message({"metadata": {"bidi_voice_mode_message": True}}))

    def test_detects_incoming_audio_transcription_only(self) -> None:
        incoming = {"content": {"parts": [{"content_type": "audio_transcription", "direction": "in"}]}}
        outgoing = {"content": {"parts": [{"content_type": "audio_transcription", "direction": "out"}]}}
        self.assertTrue(is_voice_message(incoming))
        self.assertFalse(is_voice_message(outgoing))


if __name__ == "__main__":
    unittest.main()
