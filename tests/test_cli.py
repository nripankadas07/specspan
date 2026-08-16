import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from specspan.cli import main


PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "tests" / "fixtures" / "sample"


class CliTests(unittest.TestCase):
    def test_demo_writes_impact_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(main(["demo", "--out", temp]), 0)
            self.assertTrue((Path(temp) / "impact.json").exists())
            artifact = (Path(temp) / "specspan.json").read_text(encoding="utf-8")
            self.assertIn('"name": "specspan-demo"', artifact)

    def test_fail_on_error_returns_one_after_writing_report(self):
        with tempfile.TemporaryDirectory() as temp:
            result = main(["check", str(FIXTURE), "--spec-dir", "specs", "--out", temp, "--fail-on", "error"])
            self.assertEqual(result, 1)
            self.assertTrue((Path(temp) / "report.html").exists())

    def test_missing_root_returns_two(self):
        self.assertEqual(main(["check", "missing-root"]), 2)

    def test_empty_spec_directory_fails_by_default_after_writing_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            (root / "specs").mkdir(parents=True)
            output = Path(temp) / "report"
            self.assertEqual(
                main(["check", str(root), "--spec-dir", "specs", "--out", str(output)]),
                1,
            )
            self.assertTrue((output / "report.html").exists())

    def test_impact_rejects_non_string_changed_json_with_exit_two(self):
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "changed.json"
            changed.write_text('[7, null, {"path": "src/a.py"}]', encoding="utf-8")
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                code = main(
                    [
                        "impact",
                        str(FIXTURE),
                        "--spec-dir",
                        "specs",
                        "--changed-files",
                        str(changed),
                        "--out",
                        str(Path(temp) / "report"),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertIn("non-empty relative strings", errors.getvalue())
            self.assertNotIn("Traceback", errors.getvalue())

    def test_impact_rejects_malformed_json_with_exit_two(self):
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "changed.json"
            changed.write_text('["src/a.py",]', encoding="utf-8")
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                code = main(
                    [
                        "impact",
                        str(FIXTURE),
                        "--changed-files",
                        str(changed),
                        "--out",
                        str(Path(temp) / "report"),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertIn("cannot parse changed-file JSON", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
