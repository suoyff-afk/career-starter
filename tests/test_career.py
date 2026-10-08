"""Tests of workspace safety and failed-build behavior; real TeX is checked separately."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts" / "career.py"


class CareerTests(unittest.TestCase):
    def load(self):
        self.assertTrue(SCRIPT.is_file(), "Missing minimal init/build entry: scripts/career.py")
        spec = importlib.util.spec_from_file_location("career", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_initialization_preserves_existing_candidate_files(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "求职资料 with spaces"
            created = module.initialize(root)
            self.assertEqual(len(created), 4)
            self.assertTrue((root / "resume/resume.tex").is_file())
            profile = root / "profile.md"
            profile.write_text("Already confirmed by user", encoding="utf-8")
            self.assertEqual(module.initialize(root), [])
            self.assertEqual(profile.read_text(encoding="utf-8"), "Already confirmed by user")

    def test_initialization_rejects_a_directory_in_place_of_a_file(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tracker.md").mkdir()
            with self.assertRaises(ValueError):
                module.initialize(root)
            self.assertFalse((root / "profile.md").exists())

    def test_missing_template_does_not_create_partial_workspace(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            with patch.object(module, "PROJECT", Path(directory) / "missing-project"):
                with self.assertRaises(FileNotFoundError):
                    module.initialize(root)
            self.assertFalse(root.exists())

    def test_cannot_initialize_in_public_project(self):
        module = self.load()
        with self.assertRaises(ValueError):
            module.initialize(PROJECT / "templates")

    def test_placeholder_blocks_final_build_and_preserves_pdf(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.initialize(root)
            final = root / "resume/resume.pdf"
            final.write_bytes(b"previous verified PDF")
            with self.assertRaises(ValueError):
                module.build(root)
            self.assertEqual(final.read_bytes(), b"previous verified PDF")

    def test_numeric_placeholder_is_blocked_before_compiler_lookup(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.initialize(root)
            (root / "resume/resume.tex").write_text("@@EXPERIENCEBULLET1@@", encoding="utf-8")
            with patch.object(module.shutil, "which", side_effect=AssertionError("Unfilled template reached compiler lookup")):
                with self.assertRaises(ValueError):
                    module.build(root)

    def test_missing_compiler_does_not_change_existing_pdf(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.initialize(root)
            (root / "resume/resume.tex").write_text("\\documentclass{article}\\begin{document}Candidate\\end{document}", encoding="utf-8")
            final = root / "resume/resume.pdf"
            final.write_bytes(b"old")
            with patch.object(module.shutil, "which", return_value=None):
                with self.assertRaises(FileNotFoundError):
                    module.build(root)
            self.assertEqual(final.read_bytes(), b"old")

    def test_compiler_failure_preserves_pdf_and_leaves_a_diagnostic(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.initialize(root)
            (root / "resume/resume.tex").write_text("\\documentclass{article}\\begin{document}Candidate\\end{document}", encoding="utf-8")
            final = root / "resume/resume.pdf"
            final.write_bytes(b"old")
            failure = subprocess.CompletedProcess(["xelatex"], 1, "Missing package", "")
            with patch.object(module.shutil, "which", return_value="xelatex"), patch.object(module.subprocess, "run", return_value=failure):
                with self.assertRaises(RuntimeError):
                    module.build(root)
            self.assertEqual(final.read_bytes(), b"old")
            self.assertIn("Missing package", (root / "resume/.build/compile.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
