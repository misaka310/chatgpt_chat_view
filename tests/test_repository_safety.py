import subprocess
import unittest
from pathlib import Path


class RepositorySafetyTest(unittest.TestCase):
    def test_no_real_input_or_output_paths_are_tracked(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        forbidden_prefixes = ("input/", "output/")
        forbidden_names = {"chat.html", "conversations.json"}
        for path in tracked:
            if path == "input/.keep":
                continue
            self.assertFalse(path.startswith(forbidden_prefixes), path)
            # Synthetic fixtures are intentionally tracked and named by their directory.
            if path in {"samples/conversations.json", "tests/fixtures/conversations.sample.json"}:
                continue
            self.assertNotIn(Path(path).name, forbidden_names, path)

    def test_public_documentation_targets_exist(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        for path in (
            "README.md",
            "SECURITY.md",
            "PRIVACY.md",
            "docs/BENCHMARKS.md",
            "scripts/build_sample_output.py",
            "scripts/benchmark_large_export.py",
            ".github/workflows/ci.yml",
            ".github/workflows/pages.yml",
        ):
            self.assertTrue((repo_root / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
