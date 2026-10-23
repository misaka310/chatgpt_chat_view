from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sites_public_artifact_verifier", ROOT / "scripts" / "verify_sites_public.py")
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class RscBuildIdArtifactTests(unittest.TestCase):
    def test_accepts_vinext_rsc_build_hex_identity(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "server" / "RSC_BUILD_ID"
            path.parent.mkdir()
            path.write_text("1a2b3c4d5e6f77889900aabbccddeeff\n", encoding="utf-8")
            verifier.verify_artifact_file_types(root, [path])

    def test_rejects_invalid_rsc_identity_and_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "server" / "RSC_BUILD_ID"
            path.parent.mkdir()
            for value in ("", "not-a-build-id", "a" * 31, "a" * 33, "a" * 32 + "\nPRIVATE TITLE"):
                with self.subTest(value=value):
                    path.write_text(value, encoding="utf-8")
                    with self.assertRaisesRegex(SystemExit, "invalid server/RSC_BUILD_ID artifact"):
                        verifier.verify_artifact_file_types(root, [path])

    def test_rejects_unknown_extensionless_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "server" / "OTHER_BUILD_ID"
            path.parent.mkdir()
            path.write_text("a" * 32, encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "unapproved artifact type"):
                verifier.verify_artifact_file_types(root, [path])


if __name__ == "__main__":
    unittest.main()
