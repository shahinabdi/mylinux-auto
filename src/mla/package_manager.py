import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

from .config import get_sudo_password
from .utils.distro import Distro, detect_distro


@dataclass(frozen=True)
class PackageManager:
    name: str
    install_cmd: tuple[str, ...]
    update_cmd: tuple[str, ...]
    query_cmd: tuple[str, ...]
    yes_flag: str

    def _privileged(self, cmd: Sequence[str]) -> list[str]:
        if os.geteuid() == 0 or not shutil.which("sudo"):
            return list(cmd)
        if get_sudo_password() is not None:
            return ["sudo", "-S", "-p", "", *cmd]
        return ["sudo", *cmd]

    def install_command(self, packages: Sequence[str], assume_yes: bool = False) -> list[str]:
        cmd = list(self.install_cmd)
        if assume_yes and self.yes_flag:
            cmd.append(self.yes_flag)
        return self._privileged([*cmd, *packages])

    def update_command(self) -> list[str]:
        return self._privileged(self.update_cmd)

    def is_installed(self, package: str) -> bool:
        result = subprocess.run(
            [*self.query_cmd, package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    @staticmethod
    def _run(cmd: Sequence[str]) -> int:
        password = get_sudo_password()
        if password is not None and "-S" in cmd[:3]:
            return subprocess.run(cmd, input=password + "\n", text=True).returncode
        return subprocess.run(cmd).returncode

    def install(self, packages: Sequence[str], assume_yes: bool = False) -> int:
        return self._run(self.install_command(packages, assume_yes))

    def update(self) -> int:
        return self._run(self.update_command())


PACKAGE_MANAGERS: dict[str, PackageManager] = {
    "arch": PackageManager(
        "pacman", ("pacman", "-S", "--needed"), ("pacman", "-Sy"), ("pacman", "-Qi"), "--noconfirm"
    ),
    "debian": PackageManager(
        "apt", ("apt-get", "install"), ("apt-get", "update"), ("dpkg", "-s"), "-y"
    ),
    "fedora": PackageManager(
        "dnf", ("dnf", "install"), ("dnf", "check-update"), ("rpm", "-q"), "-y"
    ),
    "suse": PackageManager(
        "zypper", ("zypper", "install"), ("zypper", "refresh"), ("rpm", "-q"), "-y"
    ),
    "alpine": PackageManager(
        "apk", ("apk", "add"), ("apk", "update"), ("apk", "info", "-e"), ""
    ),
    "void": PackageManager(
        "xbps", ("xbps-install",), ("xbps-install", "-S"), ("xbps-query",), "-y"
    ),
}


def get_package_manager(distro: Distro | None = None) -> PackageManager | None:
    distro = distro or detect_distro()
    return PACKAGE_MANAGERS.get(distro.family)


def run_privileged(cmd: Sequence[str]) -> int:
    """Run a command as root, using sudo and the configured password if needed."""
    return PackageManager._run(PackageManager._privileged(None, cmd))  # type: ignore[arg-type]
