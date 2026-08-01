import subprocess
import unittest
from pathlib import Path


class RepositorySafetyTest(unittest.TestCase):
    def test_no_real_input_output_or_sites_data_is_tracked(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        forbidden_prefixes = (
            "input/",
            "output/",
            ".ai-bridge/",
            "sites/usage-dashboard/dist/",
            "sites/usage-dashboard/.next/",
            "sites/usage-dashboard/.vinext/",
            "sites/usage-dashboard/.wrangler/",
        )
        forbidden_paths = {
            "sites/usage-dashboard/public/usage-data.json",
            "sites/usage-dashboard/.sites-build-state.json",
        }
        forbidden_names = {"chat.html", "conversations.json", "usage-data.json"}
        for path in tracked:
            if path == "input/.keep":
                continue
            self.assertFalse(path.startswith(forbidden_prefixes), path)
            self.assertNotIn(path, forbidden_paths)
            # Synthetic fixtures are intentionally tracked and named by their directory.
            if path in {"samples/conversations.json", "tests/fixtures/conversations.sample.json"}:
                continue
            self.assertNotIn(Path(path).name, forbidden_names, path)

    def test_no_nested_git_repositories_or_extra_root_files(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        nested_git = []
        for path in repo_root.rglob(".git"):
            if path == repo_root / ".git":
                continue
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", str(path)],
                cwd=repo_root,
                check=False,
            ).returncode == 0
            if not ignored:
                nested_git.append(path)
        self.assertEqual(nested_git, [])
        allowed_root_files = {
            ".gitignore",
            "LICENSE",
            "PRIVACY.md",
            "README.md",
            "requirements.txt",
            "SECURITY.md",
            "start.bat",
            "start_sites.bat",
        }
        actual_root_files = {path.name for path in repo_root.iterdir() if path.is_file()}
        self.assertEqual(actual_root_files, allowed_root_files)

    def test_startup_scripts_share_environment_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        start = (repo_root / "start.bat").read_text(encoding="utf-8")
        setup = (repo_root / "scripts" / "setup.bat").read_text(encoding="utf-8")
        marker = ".dashboard-setup-complete"
        self.assertIn(marker, start)
        self.assertIn(marker, setup)
        self.assertIn("scripts\\check_environment.py", start)

    def test_public_documentation_targets_exist(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        for path in (
            "README.md",
            "SECURITY.md",
            "PRIVACY.md",
            "docs/BENCHMARKS.md",
            "start.bat",
            "start_sites.bat",
            "scripts/start_dashboard.py",
            "scripts/check_environment.py",
            "scripts/start_sites_dashboard.py",
            "scripts/build_sites_dashboard.py",
            "scripts/verify_sites_public.py",
            "scripts/build_sample_output.py",
            "scripts/benchmark_large_export.py",
            "sites/usage-dashboard/.openai/hosting.json",
            "sites/usage-dashboard/app/page.tsx",
            ".github/workflows/ci.yml",
            ".github/workflows/pages.yml",
        ):
            self.assertTrue((repo_root / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
