import curses
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

from .models import Package, Repository, UserConfig
from .package_manager import get_package_manager
from .user_configs import get_config_status
from .utils.distro import Distro, detect_distro

EntryKind = Literal["package", "repository", "config"]
VIEWS = ("All", "Packages", "Fonts", "Configs", "Repositories")


@dataclass(frozen=True)
class CatalogEntry:
    kind: EntryKind
    name: str
    category: str
    description: str
    value: Package | Repository | UserConfig

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name.casefold()}"


def visible_entries(entries: list[CatalogEntry], view: str) -> list[CatalogEntry]:
    if view == "Packages":
        return [
            entry for entry in entries
            if isinstance(entry.value, Package) and not entry.value.font_asset
        ]
    if view == "Fonts":
        return [
            entry for entry in entries
            if isinstance(entry.value, Package) and bool(entry.value.font_asset)
        ]
    if view == "Configs":
        return [entry for entry in entries if isinstance(entry.value, UserConfig)]
    if view == "Repositories":
        return [entry for entry in entries if entry.kind == "repository"]
    return entries


def update_selection(
    selected: set[str],
    entries: list[CatalogEntry],
    checked: bool,
) -> None:
    for entry in entries:
        if checked:
            selected.add(entry.key)
        else:
            selected.discard(entry.key)


def get_install_status(entry: CatalogEntry, distro: Distro | None = None) -> str:
    if isinstance(entry.value, UserConfig):
        return get_config_status(entry.value)
    if isinstance(entry.value, Repository):
        check = entry.value.installed_check
        if not check:
            return "Unknown"
        return "Installed" if shutil.which(check) else "Not installed"

    package = entry.value
    if package.font_asset:
        from .scripts.nerd_fonts import USER_FONTS_DIR

        font_dir = USER_FONTS_DIR / "NerdFonts" / package.font_asset
        try:
            return "Installed" if any(
                path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
                for path in font_dir.rglob("*")
            ) else "Not installed"
        except OSError:
            return "Unknown"

    distro = distro or detect_distro()
    manager = get_package_manager(distro)
    checked = False

    native = package.native_name(distro.family)
    if manager and native and shutil.which(manager.query_cmd[0]):
        checked = True
        if manager.is_installed(native):
            return "Installed"

    if package.aur and distro.family == "arch" and manager and shutil.which(manager.query_cmd[0]):
        checked = True
        if manager.is_installed(package.aur):
            return "Installed"
    elif package.aur and distro.family == "arch" and shutil.which("yay"):
        checked = True
        result = subprocess.run(
            ["yay", "-Q", package.aur],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return "Installed"

    if package.flatpak and shutil.which("flatpak"):
        checked = True
        result = subprocess.run(
            ["flatpak", "info", package.flatpak],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return "Installed"

    return "Not installed" if checked else "Unknown"


def _draw(screen: curses.window, entries: list[CatalogEntry]) -> set[str]:
    selected: set[str] = set()
    statuses = {entry.key: get_install_status(entry) for entry in entries}
    view_index = 0
    cursor = 0
    offset = 0
    message = ""

    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 7 or width < 32:
            screen.addnstr(
                0,
                0,
                "Terminal too small. Resize it or press q to quit.",
                max(1, width - 1),
            )
            screen.refresh()
            if screen.getch() in (ord("q"), ord("Q"), 27):
                return set()
            continue

        view = VIEWS[view_index]
        visible = visible_entries(entries, view)
        if visible:
            cursor = min(cursor, len(visible) - 1)
        else:
            cursor = 0
        max_rows = max(1, height - 7)
        if cursor < offset:
            offset = cursor
        elif cursor >= offset + max_rows:
            offset = cursor - max_rows + 1

        screen.addnstr(0, 0, "mla  /  SOFTWARE SETUP", width - 1, curses.A_BOLD)
        tabs = "   ".join(
            f"{index + 1} {name}" if index != view_index else f"> {index + 1} {name} <"
            for index, name in enumerate(VIEWS)
        )
        screen.addnstr(1, 0, tabs, width - 1, curses.A_BOLD)
        screen.addnstr(2, 0, "-" * (width - 1), width - 1, curses.A_DIM)
        screen.addnstr(
            3,
            0,
            f"{len(visible)} entries   |   {len(selected)} selected",
            width - 1,
        )

        status_width = min(14, max(9, width // 5))
        category_width = min(14, max(8, width // 5))
        name_width = max(1, width - status_width - category_width - 12)
        for item_index, entry in enumerate(visible[offset:offset + max_rows]):
            row = 4 + item_index
            marker = "x" if entry.key in selected else " "
            name = entry.name
            category = entry.category
            if len(name) > name_width:
                name = name[:max(1, name_width - 1)] + "~"
            if len(category) > category_width:
                category = category[:max(1, category_width - 1)] + "~"
            status = statuses[entry.key].upper()
            label = (
                f"{'>' if offset + item_index == cursor else ' '} "
                f"[{marker}] {name:<{name_width}} "
                f"{category:<{category_width}} {status:>{status_width}}"
            )
            style = curses.A_REVERSE | curses.A_BOLD if offset + item_index == cursor else curses.A_NORMAL
            screen.addnstr(row, 0, label, width - 1, style)

        footer = height - 2
        screen.addnstr(footer, 0, "-" * (width - 1), width - 1, curses.A_DIM)
        if message:
            screen.addnstr(footer + 1, 0, message, width - 1, curses.A_BOLD)
        else:
            screen.addnstr(
                footer + 1,
                0,
                "Arrows move/view  Space toggle  a all  n clear  i install  q quit",
                width - 1,
                curses.A_DIM,
            )
        screen.refresh()

        key = screen.getch()
        if key in (ord("q"), ord("Q"), 27):
            return set()
        if key in (curses.KEY_LEFT, ord("h")):
            view_index = (view_index - 1) % len(VIEWS)
            cursor = offset = 0
        elif key in (curses.KEY_RIGHT, ord("l")):
            view_index = (view_index + 1) % len(VIEWS)
            cursor = offset = 0
        elif key in (ord("1"), ord("2"), ord("3"), ord("4"), ord("5")):
            view_index = int(chr(key)) - 1
            cursor = offset = 0
        elif key in (curses.KEY_UP, ord("k")) and visible:
            cursor = (cursor - 1) % len(visible)
        elif key in (curses.KEY_DOWN, ord("j")) and visible:
            cursor = (cursor + 1) % len(visible)
        elif key == ord(" ") and visible:
            current = visible[cursor]
            if current.key in selected:
                selected.remove(current.key)
            else:
                selected.add(current.key)
        elif key in (ord("a"), ord("A")):
            update_selection(selected, visible, True)
            message = f"Selected all {len(visible)} entries in {view}."
        elif key in (ord("n"), ord("N")):
            update_selection(selected, visible, False)
            message = f"Cleared selection in {view}."
        elif key in (ord("i"), ord("I"), curses.KEY_ENTER, 10, 13):
            return selected


def run_tui(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    selected = curses.wrapper(_draw, entries)
    return [entry for entry in entries if entry.key in selected]
