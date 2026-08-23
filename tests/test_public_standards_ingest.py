import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_public_standards_index.py"


class PublicStandardsIngestTest(unittest.TestCase):
    def test_builds_labeled_chunks_from_an_official_public_preview(self):
        self.assertTrue(SCRIPT.exists(), "public standards ingest script is missing")

        with tempfile.TemporaryDirectory() as temporary_directory:
            work = Path(temporary_directory)
            fixtures = work / "fixtures"
            output = work / "output"
            fixtures.mkdir()

            sources = [
                {
                    "family_id": "is-800",
                    "query": "IS 800",
                    "designation_regex": "^IS 800\\s*:",
                    "pilot_module": "structural_steel_design",
                }
            ]
            sources_path = work / "sources.json"
            sources_path.write_text(json.dumps(sources), encoding="utf-8")

            (fixtures / "is-800-search.html").write_text(
                """
                <html><body><ul>
                  <li>
                    <a href="BIS_Preview.aspx?id=800">Preview</a>
                    <span id="lblstdno_rptr">IS 800 : 2007</span>
                    <span class="standard-title">General Construction in Steel - Code of Practice</span>
                    <span id="lblstatus">Active</span>
                    <span id="lblreaff">2017</span>
                  </li>
                  <li>
                    <a href="BIS_Preview.aspx?id=8000_1_2019">Preview</a>
                    <span id="lblstdno_rptr">IS 8000 : Part 1 : 2019</span>
                    <span class="standard-title">Unrelated standard</span>
                    <span id="lblstatus">Active</span>
                  </li>
                </ul></body></html>
                """,
                encoding="utf-8",
            )
            (fixtures / "800-preview.html").write_text(
                """
                <html><head><script>ignored script text</script></head><body>
                  <p><b>IS 800 : 2007 General Construction in Steel - Code of Practice</b></p>
                  <p><b>1.1 Scope</b></p>
                  <p>This public preview covers general construction using hot rolled steel sections.</p>
                </body></html>
                """,
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--sources",
                    str(sources_path),
                    "--output-dir",
                    str(output),
                    "--fixture-dir",
                    str(fixtures),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            manifest_records = [
                json.loads(line)
                for line in (output / "MANIFEST.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(manifest_records), 1)
            self.assertEqual(manifest_records[0]["designation"], "IS 800 : 2007")
            self.assertEqual(manifest_records[0]["data_origin"], "public_official")
            self.assertEqual(manifest_records[0]["usage"], "academic_noncommercial")
            self.assertEqual(manifest_records[0]["access_type"], "official_public_preview")
            self.assertEqual(
                manifest_records[0]["content_scope"],
                "public_preview_or_metadata_not_full_standard",
            )

            chunks = [
                json.loads(line)
                for line in (output / "INDEX.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertGreaterEqual(len(chunks), 1)
            combined_text = " ".join(chunk["text"] for chunk in chunks)
            self.assertIn("hot rolled steel sections", combined_text)
            self.assertNotIn("ignored script text", combined_text)
            self.assertNotIn("IS 8000", combined_text)
            self.assertTrue(
                all(chunk["source_url"].endswith("BIS_Preview.aspx?id=800") for chunk in chunks)
            )

    def test_fails_when_a_configured_family_has_no_matching_bis_entry(self):
        self.assertTrue(SCRIPT.exists(), "public standards ingest script is missing")

        with tempfile.TemporaryDirectory() as temporary_directory:
            work = Path(temporary_directory)
            fixtures = work / "fixtures"
            output = work / "output"
            fixtures.mkdir()

            sources_path = work / "sources.json"
            sources_path.write_text(
                json.dumps(
                    [
                        {
                            "family_id": "is-800",
                            "query": "IS 800",
                            "designation_regex": "^IS 800\\s*:",
                            "pilot_module": "structural_steel_design",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (fixtures / "is-800-search.html").write_text(
                """
                <html><body><ul><li>
                  <a href="BIS_Preview.aspx?id=8000_1_2019">Preview</a>
                  <span id="lblstdno_rptr">IS 8000 : Part 1 : 2019</span>
                  <span class="standard-title">Unrelated standard</span>
                  <span id="lblstatus">Active</span>
                </li></ul></body></html>
                """,
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--sources",
                    str(sources_path),
                    "--output-dir",
                    str(output),
                    "--fixture-dir",
                    str(fixtures),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No matching BIS entry for configured family is-800", result.stderr)


if __name__ == "__main__":
    unittest.main()
