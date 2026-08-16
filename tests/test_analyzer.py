import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from specspan.analyzer import analyze, impact, load_changed_files
from specspan.reporting import markdown_report, write_bundle


PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "tests" / "fixtures" / "sample"
DEMO = PROJECT / "examples" / "demo"


class AnalyzerTests(unittest.TestCase):
    def test_detects_traceability_failures(self):
        artifact = analyze(str(FIXTURE), "specs")
        rules = {item["rule"] for item in artifact["findings"]}
        self.assertTrue(
            {
                "duplicate-requirement",
                "contradictory-constraint",
                "broken-dependency",
                "dependency-cycle",
                "broken-annotation",
                "orphan-requirement",
                "unverified-requirement",
            }.issubset(rules)
        )
        req1 = next(item for item in artifact["graph"]["traceability"] if item["requirement_id"] == "REQ-001")
        self.assertTrue(req1["verified"])
        self.assertIn("src/app.py", req1["code_paths"])
        self.assertIn("tests/test_app.py", req1["test_paths"])

    def test_analysis_is_deterministic_and_relative(self):
        first = analyze(str(FIXTURE), "specs")
        second = analyze(str(FIXTURE), "specs")
        self.assertEqual(first, second)
        self.assertFalse(any(str(FIXTURE) in item["path"] for item in first["requirements"]))

    def test_impact_maps_dependencies_without_git(self):
        artifact = analyze(str(DEMO), "specs")
        result = impact(artifact, ["./src/authorization.py"])
        identifiers = [item["requirement_id"] for item in result["impacted"]]
        self.assertEqual(identifiers, ["REQ-AUDIT-001", "REQ-CORE-001", "REQ-TRANSFER-001"])
        core = next(item for item in result["impacted"] if item["requirement_id"] == "REQ-CORE-001")
        self.assertTrue(core["direct"])
        audit = next(item for item in result["impacted"] if item["requirement_id"] == "REQ-AUDIT-001")
        self.assertFalse(audit["direct"])

    def test_impact_excludes_evidence_for_nonexistent_requirements(self):
        artifact = analyze(str(DEMO), "specs")
        artifact["evidence"].append(
            {
                "requirement_id": "REQ-MISSING-999",
                "kind": "code",
                "path": "src/broken.py",
                "line": 1,
            }
        )
        result = impact(artifact, ["src/broken.py"])
        self.assertEqual(result["impacted"], [])
        self.assertEqual(result["summary"]["direct_requirements"], 0)

    def test_changed_file_loader_accepts_json_and_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.json"
            path.write_text('["./src/a.py", "tests/test_a.py"]', encoding="utf-8")
            self.assertEqual(load_changed_files(str(path)), ["src/a.py", "tests/test_a.py"])
            path.write_text("# comment\n./src/a.py\nsrc/b.py\n", encoding="utf-8")
            self.assertEqual(load_changed_files(str(path)), ["src/a.py", "src/b.py"])

    def test_changed_file_loader_rejects_invalid_json_operands_and_paths(self):
        invalid = (
            '[7, null, {"path": "src/a.py"}]',
            '{"path": "src/a.py"}',
            '[""]',
            '["/absolute.py"]',
            '["../outside.py"]',
            '["C:/absolute.py"]',
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.json"
            for content in invalid:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "changed"):
                        load_changed_files(str(path))
        with self.assertRaisesRegex(ValueError, "relative"):
            impact(analyze(str(DEMO), "specs"), ["../outside.py"])

    def test_bundle_contains_all_formats(self):
        artifact = analyze(str(DEMO), "specs")
        impact_value = impact(artifact, ["src/authorization.py"])
        with tempfile.TemporaryDirectory() as temp:
            output = write_bundle(artifact, temp, impact_value)
            for name in ("specspan.json", "traceability.csv", "findings.sarif", "impact.json", "report.md", "report.html", "checksums.sha256"):
                self.assertTrue((output / name).exists(), name)
            value = json.loads((output / "specspan.json").read_text(encoding="utf-8"))
            self.assertEqual(value["schema_version"], "specspan/v1")

    def test_csv_neutralizes_formula_shaped_untrusted_cells(self):
        artifact = analyze(str(DEMO), "specs")
        row = artifact["graph"]["traceability"][0]
        row["status"] = "=2+2"
        row["spec_path"] = " @SUM(1,1)"
        row["code_paths"] = ["+cmd|' /C calc'!A0"]
        with tempfile.TemporaryDirectory() as temp:
            output = write_bundle(artifact, temp)
            rows = list(csv.reader(io.StringIO((output / "traceability.csv").read_text(encoding="utf-8"))))
        data = rows[1]
        self.assertIsNotNone(data)
        self.assertTrue(data[1].startswith("'="))
        self.assertTrue(data[2].startswith("' "))
        self.assertTrue(data[3].startswith("'+"))

    def test_empty_existing_spec_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "specs").mkdir()
            artifact = analyze(str(root), "specs")
            finding = next(
                item for item in artifact["findings"] if item["rule"] == "no-requirements"
            )
            self.assertEqual(finding["level"], "error")
            self.assertEqual(finding["path"], "specs")
            self.assertEqual(artifact["summary"]["errors"], 1)

    def test_fenced_markdown_examples_are_not_requirements_or_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            specs.mkdir()
            (specs / "requirements.md").write_text(
                "```markdown\n"
                "# REQ-FAKE-001: Example only\n"
                "Depends-On: REQ-MISSING-001\n"
                "```\n\n"
                "# REQ-REAL-001: Live requirement\n"
                "Status: active\n"
                "~~~text\n"
                "Depends-On: REQ-MISSING-002\n"
                "~~~\n"
                "Must: Remain real\n",
                encoding="utf-8",
            )
            artifact = analyze(str(root), "specs")
            self.assertEqual(
                [item["id"] for item in artifact["requirements"]], ["REQ-REAL-001"]
            )
            self.assertFalse(
                any(item["rule"] == "broken-dependency" for item in artifact["findings"])
            )

    def test_cycle_message_follows_real_directed_edges(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            specs.mkdir()
            (specs / "cycle.md").write_text(
                "# REQ-A: A\nDepends-On: REQ-C\n\n"
                "# REQ-B: B\nDepends-On: REQ-A\n\n"
                "# REQ-C: C\nDepends-On: REQ-B\n",
                encoding="utf-8",
            )
            artifact = analyze(str(root), "specs")
            finding = next(
                item for item in artifact["findings"] if item["rule"] == "dependency-cycle"
            )
            self.assertEqual(
                finding["message"], "Dependency cycle: REQ-A -> REQ-C -> REQ-B -> REQ-A."
            )
            edges = {
                (item["from"], item["to"])
                for item in artifact["graph"]["dependencies"]
            }
            self.assertTrue(
                {
                    ("REQ-A", "REQ-C"),
                    ("REQ-C", "REQ-B"),
                    ("REQ-B", "REQ-A"),
                }.issubset(edges)
            )

    def test_symlink_files_and_directories_are_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "root"
            specs = root / "specs"
            tests = root / "tests"
            outside = base / "outside"
            specs.mkdir(parents=True)
            tests.mkdir()
            outside.mkdir()
            (specs / "real.md").write_text(
                "# REQ-REAL-001: Real requirement\nStatus: active\n",
                encoding="utf-8",
            )
            (outside / "external.md").write_text(
                "# REQ-OUTSIDE-001: External requirement\nStatus: active\n",
                encoding="utf-8",
            )
            (outside / "external_test.py").write_text(
                "# @spec REQ-REAL-001\n", encoding="utf-8"
            )
            try:
                (specs / "outside.md").symlink_to(outside / "external.md")
                (tests / "test_external.py").symlink_to(outside / "external_test.py")
                (root / "linked-dir").symlink_to(outside, target_is_directory=True)
                root_link = base / "root-link"
                root_link.symlink_to(root, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest("symbolic links are unavailable: %s" % exc)
            artifact = analyze(str(root), "specs")
            self.assertEqual(
                [item["id"] for item in artifact["requirements"]], ["REQ-REAL-001"]
            )
            trace = artifact["graph"]["traceability"][0]
            self.assertFalse(trace["verified"])
            self.assertEqual(trace["test_paths"], [])
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                analyze(str(root_link), "specs")

    def test_non_regular_source_files_are_skipped_without_reading(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFOs are unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            specs.mkdir()
            (specs / "real.md").write_text(
                "# REQ-REAL-001: Real requirement\nStatus: active\n",
                encoding="utf-8",
            )
            os.mkfifo(str(root / "hang.py"))
            artifact = analyze(str(root), "specs")
            self.assertEqual(artifact["summary"]["evidence_links"], 0)

    def test_markdown_report_neutralizes_untrusted_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            specs.mkdir()
            (specs / "real.md").write_text(
                "# REQ-REAL-001: Real requirement\nStatus: active\n",
                encoding="utf-8",
            )
            source = root / "evil` | forged |\n\n## Injected trace.py"
            source.write_text("# @spec REQ-REAL-001\n", encoding="utf-8")
            report = markdown_report(analyze(str(root), "specs"))
            self.assertNotIn("## Injected trace", report)
            self.assertNotIn("| forged |", report)
            self.assertIn("&#96;", report)


if __name__ == "__main__":
    unittest.main()
