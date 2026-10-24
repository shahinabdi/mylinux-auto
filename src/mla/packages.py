import json
import os
import shutil
import subprocess
import tempfile

from .config import get_packages_file, get_source_order
from .models import Package
from .package_manager import PackageManager, get_package_manager
from .utils.distro import Distro, detect_distro

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"


def load_catalog() -> list[Package]:
    path = get_packages_file()
    try:
        with path.open(encoding="utf-8") as file:
            raw = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a JSON list.")

    packages: list[Package] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        try:
            package = Package(**item)
        except TypeError as error:
            raise ValueError(f"Invalid package entry {index} in {path}: {error}") from error
        if not package.name.strip() or package.name.casefold() in seen:
            raise ValueError(f"Empty or duplicate package name in entry {index}: {package.name!r}.")
        seen.add(package.name.casefold())
        packages.append(package)
    return packages


def find_package(name: str, catalog: list[Package] | None = None) -> Package | None:
    for package in catalog if catalog is not None else load_catalog():
        if package.name.casefold() == name.casefold():
            return package
    return None


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode


def ensure_flatpak(manager: PackageManager | None = None, assume_yes: bool = False) -> bool:
    if not shutil.which("flatpak"):
        manager = manager or get_package_manager()
        if manager is None or manager.install(["flatpak"], assume_yes) != 0:
            return False
    return _run(["flatpak", "remote-add", "--if-not-exists", "flathub", FLATHUB_URL]) == 0


def ensure_yay(distro: Distro | None = None, assume_yes: bool = False) -> bool:
    """Install yay from the AUR (Arch family only)."""
    distro = distro or detect_distro()
    if distro.family != "arch":
        return False
    if shutil.which("yay"):
        return True
    manager = get_package_manager(distro)
    if manager is None or manager.install(["git", "base-devel"], assume_yes) != 0:
        return False
    if os.geteuid() == 0:
        print("yay must be built as a regular user (makepkg refuses to run as root).")
        return False
    with tempfile.TemporaryDirectory() as tmp:
        build_dir = os.path.join(tmp, "yay")
        if _run(["git", "clone", "https://aur.archlinux.org/yay.git", build_dir]) != 0:
            return False
        cmd = ["makepkg", "-si"] + (["--noconfirm"] if assume_yes else [])
        return subprocess.run(cmd, cwd=build_dir).returncode == 0


def install_package(
    package: Package,
    distro: Distro | None = None,
    assume_yes: bool = False,
    prefer_flatpak: bool = False,
    dry_run: bool = False,
) -> int:
    """Try each source in the configured order (native, aur, flatpak) until one applies."""
    if package.font_asset:
        from .scripts.nerd_fonts import install_nerd_font

        return install_nerd_font(package.font_asset, dry_run=dry_run)

    distro = distro or detect_distro()
    manager = get_package_manager(distro)
    native = package.native_name(distro.family)
    order = ["flatpak"] if prefer_flatpak and package.flatpak else get_source_order(package.name)
    yes = ["--noconfirm"] if assume_yes else []

    for source in order:
        if source == "native" and manager and native:
            if dry_run:
                print(" ".join(manager.install_command([native], assume_yes)))
                return 0
            return manager.install([native], assume_yes)
        if source in ("aur", "yay") and distro.family == "arch" and package.aur:
            if dry_run:
                print(" ".join(["yay", "-S", "--needed", *yes, package.aur]))
                return 0
            if not ensure_yay(distro, assume_yes):
                return 1
            return _run(["yay", "-S", "--needed", *yes, package.aur])
        if source == "flatpak" and package.flatpak:
            if dry_run:
                print(f"flatpak install flathub {'-y ' if assume_yes else ''}{package.flatpak}")
                return 0
            return _install_flatpak(package, manager, assume_yes)
    print(f"No install method for {package.name} on {distro.pretty_name} (sources: {order}).")
    return 1


def _install_flatpak(package: Package, manager: PackageManager | None, assume_yes: bool) -> int:
    if not ensure_flatpak(manager, assume_yes):
        return 1
    return _run(["flatpak", "install", "flathub", *(["-y"] if assume_yes else []), package.flatpak])
