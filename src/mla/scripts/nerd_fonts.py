import io
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

NERD_FONTS_VERSION = "3.5.1"
NERD_FONTS_RELEASE_URL = (
    "https://github.com/ryanoasis/nerd-fonts/releases/download/"
    f"v{NERD_FONTS_VERSION}/{{asset}}.zip"
)
USER_FONTS_DIR = Path.home() / ".local" / "share" / "fonts"


def install_nerd_font(asset: str, dry_run: bool = False) -> int:
    if not asset or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
        for character in asset
    ):
        print(f"Invalid Nerd Font asset name: {asset!r}", file=sys.stderr)
        return 1

    url = NERD_FONTS_RELEASE_URL.format(asset=asset)
    install_dir = USER_FONTS_DIR / "NerdFonts" / asset
    if dry_run:
        print(f"Download {url}")
        print(f"Install fonts to {install_dir}")
        return 0

    try:
        with urllib.request.urlopen(url) as response:
            archive_data = response.read()

        install_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=install_dir.parent) as temp_dir:
            staged_dir = Path(temp_dir)
            with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
                font_files = [
                    member for member in archive.infolist()
                    if not member.is_dir()
                    and PurePosixPath(member.filename).suffix.lower() in {".ttf", ".otf"}
                ]
                if not font_files:
                    print(f"No TTF or OTF fonts found in {url}.", file=sys.stderr)
                    return 1

                for member in font_files:
                    member_path = PurePosixPath(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        print(f"Unsafe path in font archive: {member.filename}", file=sys.stderr)
                        return 1
                    destination = staged_dir.joinpath(*member_path.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)

            shutil.copytree(staged_dir, install_dir, dirs_exist_ok=True)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, RuntimeError) as error:
        print(f"Failed to install {asset} Nerd Font: {error}", file=sys.stderr)
        return 1

    print(f"Installed {asset} Nerd Font {NERD_FONTS_VERSION} to {install_dir}.")
    fc_cache = shutil.which("fc-cache")
    if fc_cache is None:
        print("fc-cache was not found; restart applications to detect the new fonts.")
        return 0
    try:
        result = subprocess.run([fc_cache, "-f", str(install_dir)], check=False)
    except OSError as error:
        print(f"Failed to refresh the font cache: {error}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(f"fc-cache failed with exit code {result.returncode}.", file=sys.stderr)
    return result.returncode
