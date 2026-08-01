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
                source.write_text("[{}]", encoding="utf-8")
                changed = {
                    "version": 1,
                    "inputs": self.module.fingerprint_files([source], input_dir),
                }
                self.assertFalse(self.module.analysis_is_current(changed))


if __name__ == "__main__":
    unittest.main()
