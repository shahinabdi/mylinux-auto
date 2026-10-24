import os
import pwd
import shutil
from pathlib import Path

DOTFILES_DIR = Path.home() / ".config" / "dotfiles"


def dotfiles_dir() -> Path:
    override = os.environ.get("MLA_DOTFILES_DIR")
    return Path(override) if override else DOTFILES_DIR


def detect_shell() -> str:
    """Return the user's login shell name (bash, zsh, fish, ...)."""
    shell = os.environ.get("SHELL") or pwd.getpwuid(os.getuid()).pw_shell
    return Path(shell).name


def append_line(filename: str, line: str) -> bool:
    """Append a line to a dotfiles file, backing it up to <file>.bak first.

    An existing .bak is overwritten. Returns False if the line is already present.
    """
    path = dotfiles_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if line in existing.splitlines():
        return False
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    with path.open("a", encoding="utf-8") as file:
        if existing and not existing.endswith("\n"):
            file.write("\n")
        file.write(line + "\n")
    return True


def add_export(line: str) -> bool:
    return append_line("exports.bash", line)


def add_alias(line: str) -> bool:
    return append_line("aliases.bash", line)
