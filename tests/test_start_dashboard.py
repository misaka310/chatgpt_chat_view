import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class StartDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "scripts" / "start_dashboard.py"
        spec = importlib.util.spec_from_file_location("start_dashboard", module_path)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_unchanged_input_reuses_complete_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            input_dir = temp / "input"
            output_dir = temp / "output"
            input_dir.mkdir()
            output_dir.mkdir()
            source = input_dir / "conversations.json"
            source.write_text("[]", encoding="utf-8")
            for name in self.module.REQUIRED_OUTPUTS:
                (output_dir / name).write_text("ok", encoding="utf-8")

            state = {
                "version": 1,
                "inputs": self.module.fingerprint_files([source], input_dir),
            }
            state_path = output_dir / ".analysis-state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            with patch.object(self.module, "OUTPUT_DIR", output_dir), patch.object(
                self.module, "STATE_PATH", state_path
            ):
                self.assertTrue(self.module.analysis_is_current(state))
                (output_dir / "favicon.svg").unlink()
                self.assertFalse(self.module.analysis_is_current(state))
                (output_dir / "favicon.svg").write_text("ok", encoding="utf-8")
                source.write_text("[{}]", encoding="utf-8")
                changed = {
                    "version": 1,
                    "inputs": self.module.fingerprint_files([source], input_dir),
                }
                self.assertFalse(self.module.analysis_is_current(changed))

    def test_legacy_match_artifacts_are_removed_by_generic_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            output_dir = Path(temp_name)
            legacy_match = output_dir / "dashboard_legacy_match.json"
            unrelated = output_dir / "dashboard_summary.json"
            legacy_match.write_text("{}", encoding="utf-8")
            unrelated.write_text("{}", encoding="utf-8")

            self.assertTrue(hasattr(self.module, "cleanup_legacy_dashboard_artifacts"))
            self.module.cleanup_legacy_dashboard_artifacts(output_dir)

            self.assertFalse(legacy_match.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
