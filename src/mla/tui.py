import curses
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from typing import Literal

from .models import Package, Repository, UserConfig
from .package_manager import get_package_manager
from .user_configs import get_config_status
from .utils.distro import Distro, detect_distro

EntryKind = Literal["package", "repository", "config"]
VIEWS = ("All", "Packages", "Fonts", "Configs", "Repositories", "Help")
HELP_CONTENT = (
    ("HOW TO USE MLA", True),
    ("Choose a tab with Left/Right or keys 1-6. Space checks an item; a selects all in that tab; n clears it.", False),
    ("Press i to install checked items. Already installed items are skipped.", False),
    ("", False),
    ("ADDING PACKAGES", True),
    ("A package is software installed by your distro package manager. Edit src/mla/data/packages.json in a source checkout.", False),
    ("For a writable installed catalog, copy that file to ~/.config/mla/packages.json and set PACKAGES_FILE to that path.", False),
    ('Example: {"name":"htop","description":"Process viewer","category":"Tools","names":{"default":"htop"}}', False),
    ("Use categories such as Terminal, Editor, or Tools. Add distro-specific names inside names, e.g. \"debian\":\"python3-pip\".", False),
    ("Packages appear in All and Packages.", False),
    ("", False),
    ("ADDING FONTS", True),
    ("A font is a package entry installed for your user. Add it to packages.json with category Font.", False),
    ('Example: {"name":"Hack","description":"Hack Nerd Font","category":"Font","font_asset":"Hack"}', False),
    ("font_asset must match a Nerd Fonts release asset. The shared version is set in nerd_fonts.py.", False),
    ("", False),
    ("ADDING CONFIGS", True),
    ("A config links a managed file to an app's usual config path. Add a record to userconfigs.json and a starter file under user-configs/.", False),
    ('Example: {"name":"Tmux","description":"Tmux settings","category":"Terminal","source":"tmux/tmux.conf","target":".config/tmux/tmux.conf"}', False),
    ("source is relative to user-configs/; target is relative to your home. MLA manages the copy in ~/.config/mla/configs/ and symlinks it.", False),
    ("Categories are the app area, e.g. Terminal, Editor, Git, or Shell. Use mla config Tmux to activate one config directly.", False),
    ("", False),
    ("ADDING REPOSITORY COMMANDS", True),
    ("Use a repository command for a setup script or custom install command, not a distro package.", False),
    ("In a checkout run: mla add NAME DESCRIPTION COMMAND CATEGORY", False),
    ('Example: mla add starship "Shell prompt" "curl -sS https://starship.rs/install.sh | sh" Shell', False),
    ("For a writable installed catalog, copy repositories.json to ~/.config/mla/ and set REPOSITORY_FILE to it first.", False),
    ("Repository commands run as shell commands. Review them before adding or installing.", False),
    ("", False),
    ("CATEGORIES", True),
    ("Pick a short label that groups similar entries; it does not change installation behavior.", False),
    ("Examples: Terminal → tmux; Editor → Neovim; Shell → EzaAliases; Git → GitConfig; Font → FiraCode.", False),
)


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
    if view == "Help":
        return []
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


def _init_styles() -> dict[str, int]:
    styles = {
        "title": curses.A_BOLD,
        "tab": curses.A_REVERSE | curses.A_BOLD,
        "heading": curses.A_BOLD,
        "example": curses.A_NORMAL,
        "ok": curses.A_BOLD,
        "bad": curses.A_NORMAL,
        "warn": curses.A_NORMAL,
        "dim": curses.A_DIM,
        "check": curses.A_BOLD,
        "cursor": curses.A_REVERSE | curses.A_BOLD,
    }
    try:
        if not curses.has_colors():
            return styles
        curses.start_color()
        try:
            curses.use_default_colors()
            background = -1
        except curses.error:
            background = curses.COLOR_BLACK
        palette = {
            "title": (curses.COLOR_CYAN, True),
            "tab": (curses.COLOR_BLACK, True),
            "heading": (curses.COLOR_MAGENTA, True),
            "example": (curses.COLOR_GREEN, False),
            "ok": (curses.COLOR_GREEN, True),
            "bad": (curses.COLOR_RED, False),
            "warn": (curses.COLOR_YELLOW, False),
            "check": (curses.COLOR_CYAN, True),
        }
        for pair, (name, (color, bold)) in enumerate(palette.items(), start=1):
            if name == "tab":
                curses.init_pair(pair, color, curses.COLOR_CYAN)
            else:
                curses.init_pair(pair, color, background)
            styles[name] = curses.color_pair(pair) | (curses.A_BOLD if bold else 0)
        styles["cursor"] = curses.A_REVERSE | curses.A_BOLD
    except (curses.error, AttributeError):
        pass
    return styles


def _status_style(status: str, styles: dict[str, int]) -> int:
    return {
        "Installed": styles["ok"],
        "Not installed": styles["bad"],
        "Conflict": styles["warn"],
    }.get(status, styles["dim"])


def _draw(screen: curses.window, entries: list[CatalogEntry]) -> set[str]:
    styles = _init_styles()
    selected: set[str] = set()
    statuses = {entry.key: get_install_status(entry) for entry in entries}
    view_index = 0
    cursor = 0
    offset = 0
    help_offset = 0
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
        if view != "Help":
            if cursor < offset:
                offset = cursor
            elif cursor >= offset + max_rows:
                offset = cursor - max_rows + 1

        screen.addnstr(0, 0, "mla  /  SOFTWARE SETUP", width - 1, styles["title"])
        column = 0
        for index, name in enumerate(VIEWS):
            label = f" {index + 1} {name} "
            if column + len(label) >= width:
                break
            screen.addnstr(
                1,
                column,
                label,
                width - 1 - column,
                styles["tab"] if index == view_index else styles["dim"],
            )
            column += len(label) + 1
        screen.addnstr(2, 0, "─" * (width - 1), width - 1, styles["dim"])
        if view == "Help":
            screen.addnstr(3, 0, "Examples and instructions  |  ↑/↓ scroll", width - 1, styles["dim"])
            help_rows: list[tuple[str, str]] = []
            for line, is_heading in HELP_CONTENT:
                if is_heading:
                    help_rows.append((f"▌ {line}", "heading"))
                    continue
                is_example = line.startswith("Example:")
                kind = "example" if is_example else "text"
                prefix = "  " if kind == "text" else "    "
                wrapped = textwrap.wrap(line, width=max(1, width - 6)) or [""]
                help_rows.extend((prefix + part, kind) for part in wrapped)
            max_rows = max(1, height - 7)
            help_offset = min(help_offset, max(0, len(help_rows) - max_rows))
            for item_index, (line, kind) in enumerate(
                help_rows[help_offset:help_offset + max_rows]
            ):
                screen.addnstr(
                    4 + item_index,
                    1,
                    line,
                    width - 2,
                    styles.get(kind, curses.A_NORMAL),
                )
        else:
            screen.addnstr(
                3,
                0,
                f"{len(visible)} entries   |   {len(selected)} selected",
                width - 1,
                styles["dim"],
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
                raw_status = statuses[entry.key]
                status = raw_status.upper()
                is_cursor = offset + item_index == cursor
                head = f"{'>' if is_cursor else ' '} [{marker}] {name:<{name_width}} "
                mid = f"{category:<{category_width}} "
                tail = f"{status:>{status_width}}"
                row_style = styles["cursor"] if is_cursor else curses.A_NORMAL
                screen.addnstr(row, 0, head, width - 1, row_style)
                x = len(head)
                screen.addnstr(
                    row, x, mid, max(1, width - 1 - x),
                    row_style if is_cursor else styles["dim"],
                )
                x += len(mid)
                if x < width - 1:
                    screen.addnstr(
                        row, x, tail, width - 1 - x,
                        row_style if is_cursor else _status_style(raw_status, styles),
                    )

        footer = height - 2
        screen.addnstr(footer, 0, "─" * (width - 1), width - 1, styles["dim"])
        if message:
            screen.addnstr(footer + 1, 0, message, width - 1, styles["warn"])
        else:
            hints = (
                ("←→", "view"), ("Space", "toggle"), ("a", "all"), ("n", "clear"),
                ("i", "install"), ("?", "help"), ("q", "quit"),
            )
            x = 0
            for hint_key, action in hints:
                if x + len(hint_key) + len(action) + 2 >= width:
                    break
                screen.addnstr(footer + 1, x, hint_key, width - 1 - x, styles["check"])
                x += len(hint_key) + 1
                screen.addnstr(footer + 1, x, action, width - 1 - x, styles["dim"])
                x += len(action) + 2
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
        elif key == ord("6") or key in (ord("?"), ord("H")):
            view_index = VIEWS.index("Help")
            help_offset = 0
        elif key in (curses.KEY_UP, ord("k")) and (visible or view == "Help"):
            if view == "Help":
                help_offset = max(0, help_offset - 1)
            else:
                cursor = (cursor - 1) % len(visible)
        elif key in (curses.KEY_DOWN, ord("j")) and (visible or view == "Help"):
            if view == "Help":
                help_offset += 1
            else:
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
