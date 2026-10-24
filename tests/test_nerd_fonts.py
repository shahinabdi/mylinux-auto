import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mla.cli import main
from mla.packages import load_catalog
from mla.scripts import nerd_fonts


class NerdFontTests(unittest.TestCase):
    def test_catalog_contains_all_nerd_font_assets(self) -> None:
        packages = {package.name: package for package in load_catalog()}

        for asset in ("FiraCode", "Go-Mono", "Hack", "Meslo", "JetBrainsMono", "Ubuntu"):
            with self.subTest(asset=asset):
                self.assertEqual(packages[asset].font_asset, asset)

    def test_install_downloads_extracts_and_refreshes_fonts(self) -> None:
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr("FiraCodeNerdFont-Regular.ttf", b"font data")

        with tempfile.TemporaryDirectory() as temp_dir:
            fonts_dir = Path(temp_dir) / "fonts"
            stdout = io.StringIO()
            with (
                patch.object(nerd_fonts, "USER_FONTS_DIR", fonts_dir),
                patch.object(nerd_fonts.urllib.request, "urlopen", return_value=io.BytesIO(archive_data.getvalue())) as urlopen,
                patch.object(nerd_fonts.shutil, "which", return_value="/usr/bin/fc-cache"),
                patch.object(nerd_fonts.subprocess, "run") as run,
                contextlib.redirect_stdout(stdout),
            ):
                run.return_value.returncode = 0
                result = nerd_fonts.install_nerd_font("FiraCode")

            self.assertEqual(result, 0)
            self.assertEqual(
                urlopen.call_args.args[0],
                nerd_fonts.NERD_FONTS_RELEASE_URL.format(asset="FiraCode"),
            )
            self.assertEqual(
                (fonts_dir / "NerdFonts" / "FiraCode" / "FiraCodeNerdFont-Regular.ttf").read_bytes(),
                b"font data",
            )
            run.assert_called_once_with(
                ["/usr/bin/fc-cache", "-f", str(fonts_dir / "NerdFonts" / "FiraCode")],
                check=False,
            )
            self.assertIn(nerd_fonts.NERD_FONTS_VERSION, stdout.getvalue())

    def test_dry_run_uses_shared_version_without_downloading(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(nerd_fonts.urllib.request, "urlopen") as urlopen,
            contextlib.redirect_stdout(stdout),
        ):
            result = nerd_fonts.install_nerd_font("Ubuntu", dry_run=True)

        self.assertEqual(result, 0)
        self.assertIn(
            f"/v{nerd_fonts.NERD_FONTS_VERSION}/Ubuntu.zip",
            stdout.getvalue(),
        )
        urlopen.assert_not_called()

    def test_get_font_does_not_require_sudo(self) -> None:
        with (
            patch("mla.cli.authenticate_sudo") as authenticate_sudo,
            patch("mla.scripts.nerd_fonts.install_nerd_font", return_value=0) as install_font,
        ):
            result = main(["get", "FiraCode"])

        self.assertEqual(result, 0)
        authenticate_sudo.assert_not_called()
        install_font.assert_called_once_with("FiraCode", dry_run=False)


if __name__ == "__main__":
    unittest.main()
