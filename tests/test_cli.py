import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mylinux_auto.cli import main


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.catalog_path = Path(self.temp_dir.name) / "repositories.json"
        self.catalog_path.write_text(
            json.dumps(
                [
                    {
                        "id": 1,
                        "name": "uv",
                        "description": "Python package manager",
                        "url": "echo install uv",
                        "category": "Python",
                    },
                    {
                        "id": 2,
                        "name": "starship",
                        "description": "Shell prompt",
                        "url": "echo install starship",
                        "category": "Shell",
                    },
                ]
            ),
            encoding="utf-8",
        )
        self.env = patch.dict(os.environ, {"REPOSITORY_FILE": str(self.catalog_path)})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp_dir.cleanup()

    def invoke(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_list_filters_by_category(self) -> None:
        result, stdout, _ = self.invoke("list", "--category", "python")

        self.assertEqual(result, 0)
        self.assertIn("uv", stdout)
        self.assertNotIn("starship", stdout)

    def test_search_matches_description_case_insensitively(self) -> None:
        result, stdout, _ = self.invoke("search", "PACKAGE")

        self.assertEqual(result, 0)
        self.assertIn("uv", stdout)
        self.assertNotIn("starship", stdout)

    def test_add_and_remove_persist_catalog(self) -> None:
        result, stdout, _ = self.invoke(
            "add", "eza", "Modern ls replacement", "cargo install eza", "Shell"
        )
        self.assertEqual(result, 0)
        self.assertIn("Added eza", stdout)

        catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(catalog[-1]["id"], 3)

        result, stdout, _ = self.invoke("remove", "3")
        self.assertEqual(result, 0)
        self.assertIn("Removed eza", stdout)
        self.assertEqual(len(json.loads(self.catalog_path.read_text(encoding="utf-8"))), 2)

    def test_install_requires_confirmation_and_runs_after_yes(self) -> None:
        with patch("builtins.input", return_value="n"):
            result, stdout, _ = self.invoke("install", "uv")
        self.assertEqual(result, 1)
        self.assertIn("cancelled", stdout)

        with patch("mylinux_auto.cli.subprocess.run") as run:
            run.return_value.returncode = 0
            result, _, _ = self.invoke("install", "uv", "--yes")

        self.assertEqual(result, 0)
        run.assert_called_once_with("echo install uv", shell=True, check=False)

    def test_invalid_catalog_reports_error(self) -> None:
        self.catalog_path.write_text("{not json", encoding="utf-8")

        result, _, stderr = self.invoke("list")

        self.assertEqual(result, 1)
        self.assertIn("Invalid JSON", stderr)


if __name__ == "__main__":
    unittest.main()
