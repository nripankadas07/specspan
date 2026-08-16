import csv
import io
import json
import os
import errno
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from specspan import safeio
from specspan import analyzer
from specspan.analyzer import analyze, impact, load_changed_files
from specspan.reporting import markdown_report, sarif, write_bundle


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

    def test_requirement_line_parsing_is_bounded_and_strips_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            specs.mkdir()
            (specs / "requirements.md").write_text(
                "# REQ-LINEAR-001   :   Bounded parser title   \n"
                "Status   :   active   \n"
                "Must   :   preserve trimmed values   \n"
                + ("#" * 200_000)
                + "\n",
                encoding="utf-8",
            )
            artifact = analyze(str(root), "specs")
            self.assertEqual(artifact["requirements"][0]["title"], "Bounded parser title")
            self.assertEqual(artifact["requirements"][0]["status"], "active")
            self.assertEqual(
                artifact["requirements"][0]["must"], ["preserve trimmed values"]
            )

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

    def test_changed_file_loader_rejects_malformed_json_shaped_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.json"
            for content in ('["src/a.py",]', '\ufeff["src/a.py",]'):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(
                        ValueError, "cannot parse changed-file JSON"
                    ):
                        load_changed_files(str(path))

            path.write_text('\ufeff["src/a.py"]', encoding="utf-8")
            self.assertEqual(load_changed_files(str(path)), ["src/a.py"])

    def test_changed_file_loader_enforces_strict_bom_utf8_and_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.json"
            path.write_bytes(b"\xef\xbb\xbf[\"src/a.py\"]")
            self.assertEqual(load_changed_files(str(path)), ["src/a.py"])

            invalid = (
                b"\xef\xbb\xbf\xef\xbb\xbf[\"src/a.py\"]",
                b"[\"src/a.py\"]\xef\xbb\xbf",
                b"[\"src/\xff.py\"]",
                "src/\u0085.py\n".encode("utf-8"),
                b'["src/\\u0001.py"]',
                b'["src/\\u202e.py"]',
            )
            for payload in invalid:
                with self.subTest(payload=payload):
                    path.write_bytes(payload)
                    with self.assertRaisesRegex(ValueError, "changed-file|control"):
                        load_changed_files(str(path))

        artifact = analyze(str(DEMO), "specs")
        for value in ("src/\u0001.py", "src/\u0085.py", "src/\u202e.py"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "control"):
                    impact(artifact, [value])

    def test_changed_file_loader_rejects_symlinks_and_special_files_without_blocking(self):
        if not hasattr(os, "symlink") or not hasattr(os, "mkfifo"):
            self.skipTest("symbolic links and FIFOs are required")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("src/a.py\n", encoding="utf-8")
            linked = root / "linked.txt"
            linked.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "regular file"):
                load_changed_files(str(linked))

            fifo = root / "changed.fifo"
            os.mkfifo(str(fifo))
            with self.assertRaisesRegex(ValueError, "regular file"):
                load_changed_files(str(fifo))

    def test_changed_file_loader_closes_descriptor_when_fstat_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.txt"
            path.write_text("src/a.py\n", encoding="utf-8")
            opened = []
            real_open = os.open

            def record_open(*args, **kwargs):
                descriptor = real_open(*args, **kwargs)
                opened.append(descriptor)
                return descriptor

            with mock.patch.object(analyzer.os, "open", side_effect=record_open), mock.patch.object(
                analyzer.os, "fstat", side_effect=OSError("injected fstat failure")
            ):
                with self.assertRaisesRegex(ValueError, "fstat failure"):
                    load_changed_files(str(path))

            self.assertEqual(len(opened), 1)
            with self.assertRaises(OSError) as raised:
                os.fstat(opened[0])
            self.assertEqual(raised.exception.errno, errno.EBADF)

    def test_changed_file_loader_rejects_content_changed_during_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.txt"
            path.write_text("src/a.py\n", encoding="utf-8")
            real_read = os.read
            mutated = False

            def mutate_after_read(descriptor, size):
                nonlocal mutated
                payload = real_read(descriptor, size)
                if not mutated:
                    mutated = True
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write("src/b.py\n")
                return payload

            with mock.patch.object(analyzer.os, "read", side_effect=mutate_after_read):
                with self.assertRaisesRegex(ValueError, "changed while it was read"):
                    load_changed_files(str(path))

    def test_bundle_contains_all_formats(self):
        artifact = analyze(str(DEMO), "specs")
        impact_value = impact(artifact, ["src/authorization.py"])
        with tempfile.TemporaryDirectory() as temp:
            output = write_bundle(artifact, temp, impact_value)
            for name in ("specspan.json", "traceability.csv", "findings.sarif", "impact.json", "report.md", "report.html", "checksums.sha256"):
                self.assertTrue((output / name).exists(), name)
            value = json.loads((output / "specspan.json").read_text(encoding="utf-8"))
            self.assertEqual(value["schema_version"], "specspan/v1")

    def test_bundle_rejects_output_symlinks_and_fifos_without_touching_targets(self):
        if not hasattr(os, "symlink") or not hasattr(os, "mkfifo"):
            self.skipTest("symbolic links and FIFOs are required")
        artifact = analyze(str(DEMO), "specs")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            victim = root / "victim.txt"
            victim.write_text("sentinel", encoding="utf-8")
            (output / "report.md").symlink_to(victim)
            with self.assertRaisesRegex(ValueError, "non-regular"):
                write_bundle(artifact, str(output))
            self.assertEqual(victim.read_text(encoding="utf-8"), "sentinel")
            (output / "report.md").unlink()
            os.mkfifo(str(output / "report.md"))
            with self.assertRaisesRegex(ValueError, "non-regular"):
                write_bundle(artifact, str(output))
            real_output = root / "real-output"
            real_output.mkdir()
            linked_output = root / "linked-output"
            linked_output.symlink_to(real_output, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                write_bundle(artifact, str(linked_output))

            victim_directory = root / "victim-directory"
            victim_directory.mkdir()
            attacker_link = root / "attacker-link"
            attacker_link.symlink_to(victim_directory, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                write_bundle(artifact, str(attacker_link / "real-subdir"))
            self.assertFalse((victim_directory / "real-subdir").exists())

            relative_output = os.path.relpath(
                attacker_link / "relative-subdir", Path.cwd()
            )
            self.assertIn("..", Path(relative_output).parts)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                write_bundle(artifact, relative_output)
            self.assertFalse((victim_directory / "relative-subdir").exists())

            with mock.patch.object(
                safeio, "_supports_descriptor_relative_io", return_value=False
            ):
                with self.assertRaisesRegex(OSError, "descriptor-relative"):
                    write_bundle(artifact, str(attacker_link / "fallback-subdir"))
            self.assertFalse((victim_directory / "fallback-subdir").exists())

    def test_bundle_rolls_back_if_second_artifact_publication_fails(self):
        artifact = analyze(str(DEMO), "specs")
        impact_value = impact(artifact, ["src/authorization.py"])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            write_bundle(artifact, str(output), impact_value)
            for path in output.iterdir():
                path.write_text("original:%s\n" % path.name, encoding="utf-8")
            original = {path.name: path.read_bytes() for path in output.iterdir()}

            real_rename = safeio._rename_at
            publications = 0

            def fail_second(directory_fd, source, target):
                nonlocal publications
                if ".tmp-" in source and not target.startswith("."):
                    publications += 1
                    if publications == 2:
                        raise OSError("injected second publication failure")
                return real_rename(directory_fd, source, target)

            with mock.patch.object(safeio, "_rename_at", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "second publication"):
                    write_bundle(artifact, str(output), impact_value)

            restored = {path.name: path.read_bytes() for path in output.iterdir()}
            self.assertEqual(restored, original)
            self.assertFalse(
                any(".tmp-" in path.name or ".bak-" in path.name for path in output.iterdir())
            )

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

    def test_deep_dependency_graph_does_not_recurse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            specs.mkdir()
            count = 1500
            lines = []
            for index in range(count):
                lines.append("# REQ-%04d: Node %d\n" % (index, index))
                if index + 1 < count:
                    lines.append("Depends-On: REQ-%04d\n" % (index + 1))
                lines.append("Status: draft\n\n")
            (specs / "chain.md").write_text("".join(lines), encoding="utf-8")
            artifact = analyze(str(root), "specs")
            self.assertEqual(artifact["summary"]["unique_requirements"], count)
            self.assertEqual(artifact["summary"]["errors"], 0)

    def test_sarif_percent_encodes_paths_as_uri_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            specs.mkdir()
            (specs / "real.md").write_text("# REQ-REAL: Real\n", encoding="utf-8")
            (root / "risk#fragment\u202e.py").write_text(
                "# @spec REQ-MISSING\n", encoding="utf-8"
            )
            result = sarif(analyze(str(root), "specs"))
            finding = next(
                item for item in result["runs"][0]["results"] if item["ruleId"] == "broken-annotation"
            )
            uri = finding["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            self.assertEqual(uri, "risk%23fragment%E2%80%AE.py")

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
