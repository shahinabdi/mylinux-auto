import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent




def get_data_file() -> Path:
    override = os.environ.get("REPOSITORY_FILE")
    return Path(override) if override else BASE_DIR / "data" / "repositories.json"

def get_packages_file() -> Path:
    override = os.environ.get("PACKAGES_FILE")
    return Path(override) if override else BASE_DIR / "data" / "packages.json"


_sudo_password: str | None = None


def get_sudo_password() -> str | None:
    return _sudo_password or load_user_config().get("password")


def authenticate_sudo() -> bool:
    """Ask for the sudo password once and keep it in memory only (never written to disk)."""
    import getpass
    import subprocess

    global _sudo_password
    if os.geteuid() == 0:
        return True
    for _ in range(3):
        password = getpass.getpass("[sudo] password: ")
        result = subprocess.run(
            ["sudo", "-S", "-p", "", "-v"],
            input=password + "\n",
            text=True,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            _sudo_password = password
            return True
        print("Sorry, try again.")
    return False


DEFAULT_SOURCE_ORDER = ["native", "aur", "flatpak"]


def get_user_config_file() -> Path:
    override = os.environ.get("MLA_CONFIG")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "mla" / "config.json"


def load_user_config() -> dict:
    try:
        with get_user_config_file().open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_user_config(config: dict) -> Path:
    path = get_user_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Created with 0600 because it may contain the sudo password.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
        file.write("\n")
    os.chmod(path, 0o600)
    return path


def get_source_order(package: str | None = None) -> list[str]:
    """Install source order, with an optional per-package override."""
    config = load_user_config()
    override = config.get("package_sources", {}).get(package or "")
    if override:
        return [override] if isinstance(override, str) else list(override)
    return list(config.get("source_order") or DEFAULT_SOURCE_ORDER)
