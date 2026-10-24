from dataclasses import dataclass, field


@dataclass
class Repository:
    """A named software setup command in the user's repository catalog."""

    name: str
    description: str
    url: str
    category: str
    installed_check: str | None = None


@dataclass
class UserConfig:
    """A user config template, optionally paired with a preferred upstream installer."""

    name: str
    description: str
    category: str
    source: str
    target: str
    upstream_installer_url: str | None = None


@dataclass
class Package:
    """A package installable by name, with per-distro-family name overrides.

    `names` maps a distro family (arch, debian, fedora, ...) or "default" to the
    native package name. `aur` and `flatpak` hold an AUR package name and a
    Flatpak application ID; `font_asset` identifies a Nerd Fonts release asset.
    """

    name: str
    description: str
    category: str
    names: dict[str, str] = field(default_factory=dict)
    aur: str | None = None
    flatpak: str | None = None
    font_asset: str | None = None

    def native_name(self, family: str) -> str | None:
        return self.names.get(family) or self.names.get("default")
