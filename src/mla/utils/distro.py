from dataclasses import dataclass
from pathlib import Path

OS_RELEASE_PATHS = (Path("/etc/os-release"), Path("/usr/lib/os-release"))

FAMILIES = ("arch", "debian", "fedora", "suse", "alpine", "gentoo", "void")
# Families that are derived from, or identified by, another family's ID.
FAMILY_ALIASES = {
    "rhel": "fedora",
    "centos": "fedora",
    "ubuntu": "debian",
    "opensuse": "suse",
    "manjaro": "arch",
    "cachyos": "arch",
    "endeavouros": "arch",
}


@dataclass(frozen=True)
class Distro:
    id: str
    id_like: tuple[str, ...]
    name: str
    pretty_name: str
    family: str

    @property
    def is_arch(self) -> bool:
        return self.family == "arch"

    @property
    def is_debian(self) -> bool:
        return self.family == "debian"

    @property
    def is_fedora(self) -> bool:
        return self.family == "fedora"


def parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _family(distro_id: str, id_like: tuple[str, ...]) -> str:
    for candidate in (distro_id, *id_like):
        candidate = candidate.lower()
        if candidate in FAMILIES:
            return candidate
        if candidate in FAMILY_ALIASES:
            return FAMILY_ALIASES[candidate]
    return distro_id.lower() or "unknown"


def detect_distro(paths: tuple[Path, ...] = OS_RELEASE_PATHS) -> Distro:
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        values = parse_os_release(text)
        distro_id = values.get("ID", "").lower()
        id_like = tuple(values.get("ID_LIKE", "").lower().split())
        name = values.get("NAME", distro_id or "Linux")
        return Distro(
            id=distro_id or "unknown",
            id_like=id_like,
            name=name,
            pretty_name=values.get("PRETTY_NAME", name),
            family=_family(distro_id, id_like),
        )
    return Distro("unknown", (), "Linux", "Linux", "unknown")


if __name__ == "__main__":
    detected = detect_distro()
    print(f"{detected.pretty_name} (id={detected.id}, family={detected.family})")
