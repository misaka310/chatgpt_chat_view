import importlib.util
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path


class CheckEnvironmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "scripts" / "check_environment.py"
        spec = importlib.util.spec_from_file_location("check_environment", module_path)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_exact_requirements_match_installed_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            requirements = Path(temp_name) / "requirements.txt"
            requirements.write_text("alpha==1.2.3\nbeta==4.5.6  # pinned\n", encoding="utf-8")
            installed = {"alpha": "1.2.3", "beta": "4.5.6"}
            self.assertEqual(
                self.module.environment_mismatches(requirements, installed.__getitem__),
                [],
            )

    def test_missing_and_wrong_versions_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            requirements = Path(temp_name) / "requirements.txt"
            requirements.write_text("alpha==1.2.3\nbeta==4.5.6\n", encoding="utf-8")

            def installed(name: str) -> str:
                if name == "beta":
                    raise PackageNotFoundError(name)
                return "9.9.9"

            mismatches = self.module.environment_mismatches(requirements, installed)
            self.assertEqual(len(mismatches), 2)
            self.assertIn("installed 9.9.9, expected 1.2.3", mismatches[0])
            self.assertIn("missing (expected 4.5.6)", mismatches[1])

    def test_non_exact_requirement_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            requirements = Path(temp_name) / "requirements.txt"
            requirements.write_text("alpha>=1.0\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                self.module.parse_exact_requirements(requirements)


if __name__ == "__main__":
    unittest.main()
