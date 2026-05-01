import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class AnalyzeChatExportTest(unittest.TestCase):
    def test_dedup_and_outputs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        sample_src = repo_root / "tests" / "fixtures" / "conversations.sample.json"
        rules_path = repo_root / "rules" / "category_keywords.json"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_dir = temp / "input"
            output_dir = temp / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(sample_src, input_dir / "conversations.json")

            cmd = [
                sys.executable,
                str(repo_root / "analyze_chat_export.py"),
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
                "--timezone",
                "Asia/Tokyo",
                "--rules",
                str(rules_path),
                "--rebuild",
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

            parsed_path = output_dir / "parsed_summary.json"
            self.assertTrue(parsed_path.exists(), "parsed_summary.json was not generated")
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))

            stats = parsed["meta"]["stats"]
            self.assertEqual(stats["total_conversation_objects"], 3)
            self.assertEqual(stats["total_unique_messages"], 5)
            self.assertEqual(stats["total_duplicate_messages_skipped"], 5)
            self.assertEqual(stats["total_conversations"], 2)

            conv_index = {row["conversation_id"]: row for row in parsed["conversation_index"]}
            self.assertEqual(conv_index["conv-001"]["total_message_count"], 3)
            self.assertEqual(conv_index["conv-001"]["user_message_count"], 2)
            self.assertEqual(conv_index["conv-001"]["assistant_message_count"], 1)
            self.assertEqual(conv_index["conv-002"]["total_message_count"], 2)
            self.assertIn(conv_index["conv-002"]["inferred_category"], ("音声生成", "その他"))

            for filename in (
                "conversations_index.csv",
                "category_monthly.csv",
                "category_daily.csv",
                "keywords_monthly.csv",
                "dashboard.html",
            ):
                self.assertTrue((output_dir / filename).exists(), f"{filename} was not generated")


if __name__ == "__main__":
    unittest.main()
