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
                "--codex-sessions-root",
                str(temp / "empty_codex_sessions"),
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
            self.assertIn(
                stats.get("token_estimation_method"),
                ("tiktoken:o200k_base", "char_fallback_v1"),
            )

            conv_index = {row["conversation_id"]: row for row in parsed["conversation_index"]}
            self.assertEqual(conv_index["conv-001"]["total_message_count"], 3)
            self.assertEqual(conv_index["conv-001"]["user_message_count"], 2)
            self.assertEqual(conv_index["conv-001"]["assistant_message_count"], 1)
            self.assertEqual(conv_index["conv-002"]["total_message_count"], 2)
            self.assertEqual(conv_index["conv-002"]["inferred_category"], "音声生成")

            monthly = {row["month"]: row for row in parsed["monthly"]}
            self.assertAlmostEqual(monthly["2024-01"]["avg_per_elapsed_day"], 2 / 31, places=6)
            self.assertAlmostEqual(monthly["2024-01"]["avg_per_active_day"], 2.0, places=6)
            self.assertAlmostEqual(monthly["2024-01"]["median_daily_user_messages"], 0.0, places=6)
            self.assertEqual(monthly["2024-01"]["peak_daily_user_messages"], 2)
            self.assertEqual(monthly["2024-01"]["peak_daily_date"], "2024-01-01")
            self.assertAlmostEqual(monthly["2024-02"]["avg_per_elapsed_day"], 1.0, places=6)
            self.assertAlmostEqual(monthly["2024-02"]["avg_per_active_day"], 1.0, places=6)
            self.assertAlmostEqual(monthly["2024-02"]["median_daily_user_messages"], 1.0, places=6)
            self.assertEqual(monthly["2024-02"]["peak_daily_user_messages"], 1)
            self.assertEqual(monthly["2024-02"]["peak_daily_date"], "2024-02-01")

            jan = monthly["2024-01"]
            required_token_keys = (
                "user_tokens_est",
                "assistant_tokens_est",
                "system_tokens_est",
                "tool_tokens_est",
                "total_tokens_est",
                "avg_user_tokens_est",
                "avg_tokens_per_active_day_est",
            )
            for key in required_token_keys:
                self.assertIn(key, jan)
                self.assertGreaterEqual(jan[key], 0)
            self.assertEqual(
                jan["total_tokens_est"],
                jan["user_tokens_est"]
                + jan["assistant_tokens_est"]
                + jan["system_tokens_est"]
                + jan["tool_tokens_est"]
                + jan.get("other_tokens_est", 0),
            )
            self.assertAlmostEqual(
                jan["avg_user_tokens_est"],
                jan["user_tokens_est"] / jan["user_messages"],
                places=6,
            )
            self.assertAlmostEqual(
                jan["avg_tokens_per_active_day_est"],
                jan["total_tokens_est"] / jan["active_days"],
                places=6,
            )

            for filename in (
                "conversations_index.csv",
                "category_monthly.csv",
                "category_daily.csv",
                "keywords_monthly.csv",
                "dashboard.html",
                "dashboard_summary.json",
                "dashboard_conversations.json",
                "dashboard_daily.json",
                "dashboard_categories.json",
                "dashboard_codex_match.json",
                "out/codex_chat_match_2026-04_summary.md",
                "out/codex_chat_match_2026-04_chat_prompts.csv",
                "out/codex_chat_match_2026-04_codex_prompts.csv",
                "out/codex_chat_match_2026-04_matches.csv",
                "out/codex_chat_match_2026-04_unmatched_chat.csv",
                "out/codex_chat_match_2026-04_unmatched_codex.csv",
            ):
                self.assertTrue((output_dir / filename).exists(), f"{filename} was not generated")

            summary_payload = json.loads((output_dir / "dashboard_summary.json").read_text(encoding="utf-8"))
            self.assertIn("meta", summary_payload)
            self.assertIn("monthly", summary_payload)
            self.assertNotIn("conversation_index", summary_payload)

            conversations_payload = json.loads((output_dir / "dashboard_conversations.json").read_text(encoding="utf-8"))
            self.assertIn("items", conversations_payload)
            self.assertEqual(len(conversations_payload["items"]), 2)
            self.assertEqual(conversations_payload["total"], 2)

            daily_payload = json.loads((output_dir / "dashboard_daily.json").read_text(encoding="utf-8"))
            self.assertIn("daily", daily_payload)
            self.assertIn("daily_top_conversations", daily_payload)

            categories_payload = json.loads((output_dir / "dashboard_categories.json").read_text(encoding="utf-8"))
            self.assertIn("category_monthly", categories_payload)
            self.assertIn("keywords_monthly", categories_payload)

            codex_match_payload = json.loads((output_dir / "dashboard_codex_match.json").read_text(encoding="utf-8"))
            self.assertIn("summary", codex_match_payload)
            self.assertIn("matches", codex_match_payload)

            dashboard_html = (output_dir / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("dashboard_summary.json", dashboard_html)
            self.assertIn("会話一覧を読み込む", dashboard_html)
            self.assertIn("Codex照合を読み込む", dashboard_html)
            self.assertNotIn('<script id="data" type="application/json">', dashboard_html)

    def test_codex_match_filters_agents_injection(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        rules_path = repo_root / "rules" / "category_keywords.json"
        conversation_src = repo_root / "tests" / "fixtures" / "conversations.codex_match.sample.json"
        codex_sessions = repo_root / "tests" / "fixtures" / "codex_sessions"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_dir = temp / "input"
            output_dir = temp / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(conversation_src, input_dir / "conversations.json")

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
                "--codex-sessions-root",
                str(codex_sessions),
                "--codex-match-month",
                "2026-04",
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

            parsed = json.loads((output_dir / "parsed_summary.json").read_text(encoding="utf-8"))
            summary = parsed["codex_match"]["summary"]
            self.assertEqual(summary["chat_codex_prompt_count"], 1)
            self.assertEqual(summary["codex_user_prompt_count"], 1)
            self.assertEqual(summary["matched_prompt_count"], 1)
            self.assertEqual(summary["chat_only_prompt_count"], 0)
            self.assertEqual(summary["codex_only_prompt_count"], 0)
            self.assertEqual(summary["exact_match_count"], 1)
            self.assertEqual(summary["near_match_count"], 0)


if __name__ == "__main__":
    unittest.main()
