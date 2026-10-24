import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

from .config import BASE_DIR, get_mla_config_dir, get_user_configs_file
from .models import UserConfig


def _safe_relative_path(value: str, label: str) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {label} path: {value!r}.")
    path = PurePosixPath(value)
    if not value or path == PurePosixPath(".") or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Invalid {label} path: {value!r}.")
    return Path(*path.parts)


def load_user_configs() -> list[UserConfig]:
    path = get_user_configs_file()
    try:
        with path.open(encoding="utf-8") as file:
            raw = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a JSON list.")

    configs: list[UserConfig] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"User config entry {index} in {path} must be a JSON object.")
        try:
            config = UserConfig(**item)
        except TypeError as error:
            raise ValueError(f"Invalid user config entry {index} in {path}: {error}") from error
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (config.name, config.description, config.category)
        ):
            raise ValueError(f"User config entry {index} in {path} has an empty required field.")
        _safe_relative_path(config.source, "source")
        _safe_relative_path(config.target, "target")
        if config.upstream_installer_url is not None:
            if not isinstance(config.upstream_installer_url, str) or not config.upstream_installer_url.startswith(
                "https://"
            ):
                raise ValueError(f"Invalid upstream installer URL for {config.name!r}.")
        normalized_name = config.name.casefold()
        if normalized_name in seen_names:
            raise ValueError(f"Duplicate user config name: {config.name}.")
        seen_names.add(normalized_name)
        configs.append(config)
    return configs


def get_config_source(config: UserConfig) -> Path:
    relative_source = _safe_relative_path(config.source, "source")
    return get_mla_config_dir() / "configs" / relative_source


def get_config_target(config: UserConfig) -> Path:
    relative_target = _safe_relative_path(config.target, "target")
    return Path.home() / relative_target


def get_config_status(config: UserConfig) -> str:
    source = get_config_source(config)
    target = get_config_target(config)
    if target.is_symlink():
        return "Installed" if target.resolve() == source.resolve() else "Conflict"
    if config.upstream_installer_url:
        marker = get_mla_config_dir() / "state" / "configs" / config.name
        try:
            if marker.read_text(encoding="utf-8").strip() == config.upstream_installer_url:
                return "Installed"
        except FileNotFoundError:
            pass
        return "Unknown" if target.exists() else "Not installed"
    return "Conflict" if target.exists() else "Not installed"


def install_user_config(config: UserConfig) -> int:
    if config.upstream_installer_url:
        try:
            choice = input(
                f"Use preferred upstream Git config installer? "
                "[Y/n] (choose n for MLA starter config): "
            ).strip().casefold()
        except EOFError:
            print("No selection received; GitConfig installation cancelled.", file=sys.stderr)
            return 1
        if choice not in {"", "y", "yes", "n", "no"}:
            print("Choose y for upstream or n for the MLA starter config.", file=sys.stderr)
            return 1
        if choice in {"", "y", "yes"}:
            return _install_upstream_config(config)

    source = get_config_source(config)
    if source.exists() and not source.is_file():
        print(f"Managed config source is not a regular file: {source}", file=sys.stderr)
        return 1
    if not source.exists():
        template = BASE_DIR / "data" / "user-configs" / _safe_relative_path(config.source, "source")
        if not template.is_file():
            print(f"Config template does not exist: {template}", file=sys.stderr)
            return 1
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, source)

    target = get_config_target(config)
    if target.is_symlink() and target.resolve() == source.resolve():
        print(f"{config.name} is already linked at {target}.")
        return 0
    if target.exists() or target.is_symlink():
        print(
            f"Cannot activate {config.name}: {target} already exists. "
            "Move it aside or remove it before retrying; it was not changed.",
            file=sys.stderr,
        )
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source)
    print(f"Activated {config.name}: {target} -> {source}")
    return 0


def _install_upstream_config(config: UserConfig) -> int:
    backup_paths = (
        Path.home() / ".gitconfig",
        Path.home() / ".gitignore_global",
        Path.home() / ".gitmessage",
    )
    for path in backup_paths:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            print(
                f"Cannot safely run the upstream installer because {path} "
                "is a symlink or not a regular file.",
                file=sys.stderr,
            )
            return 1

    backups: list[tuple[Path, Path]] = []
    for path in backup_paths:
        if not path.exists():
            continue
        backup = path.with_name(f"{path.name}.mla.bak")
        suffix = 1
        while backup.exists():
            backup = path.with_name(f"{path.name}.mla.bak.{suffix}")
            suffix += 1
        try:
            shutil.copy2(path, backup)
        except OSError as error:
            print(f"Could not back up {path}: {error}", file=sys.stderr)
            return 1
        backups.append((path, backup))

    url = config.upstream_installer_url
    print(
        f"Running the upstream installer from {url}. "
        "It will ask for your Git name/email and Full or Lite config, "
        "then install ~/.gitconfig, ~/.gitignore_global, and ~/.gitmessage."
    )
    if backups:
        print("Backed up existing Git config files:")
        for original, backup in backups:
            print(f"  {original} -> {backup}")

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            script = response.read().decode("utf-8")
        result = subprocess.run(["bash"], input=script, text=True, check=False)
    except (OSError, UnicodeError, urllib.error.URLError) as error:
        print(f"Failed to download or run the upstream Git config installer: {error}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(
            f"Upstream Git config installer failed with exit code {result.returncode}. "
            "Any backups were preserved.",
            file=sys.stderr,
        )
        return result.returncode

    marker = get_mla_config_dir() / "state" / "configs" / config.name
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{url}\n", encoding="utf-8")
    except OSError as error:
        print(f"Git config was installed, but status could not be saved: {error}", file=sys.stderr)
        return 1
    return 0
