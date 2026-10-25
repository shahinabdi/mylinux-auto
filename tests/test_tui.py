import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mla.cli import _run_tui, main
from mla.models import Package, Repository, UserConfig
from mla.tui import (
    CatalogEntry,
    get_install_status,
    not_installed_entries,
    run_tui,
    update_selection,
    visible_entries,
)
from mla.utils.distro import Distro


class TuiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = CatalogEntry(
            "package",
            "editor",
            "Editor",
            "Text editor",
            Package("editor", "Text editor", "Editor", {"debian": "editor"}),
        )
        self.font = CatalogEntry(
            "package",
            "FiraCode",
            "Font",
            "FiraCode Nerd Font",
            Package("FiraCode", "FiraCode Nerd Font", "Font", font_asset="FiraCode"),
        )
        self.repository = CatalogEntry(
            "repository",
            "starship",
            "Shell",
            "Shell prompt",
            Repository("starship", "Shell prompt", "install command", "Shell", "starship"),
        )
        self.config = CatalogEntry(
            "config",
            "Tmux",
            "Terminal",
            "Starter tmux config",
            UserConfig("Tmux", "Starter tmux config", "Terminal", "tmux/tmux.conf", ".config/tmux/tmux.conf"),
        )
        self.entries = [self.package, self.font, self.repository, self.config]

    def test_views_separate_packages_fonts_and_repositories(self) -> None:
        self.assertEqual(visible_entries(self.entries, "Packages"), [self.package])
        self.assertEqual(visible_entries(self.entries, "Fonts"), [self.font])
        self.assertEqual(visible_entries(self.entries, "Configs"), [self.config])
        self.assertEqual(visible_entries(self.entries, "Repositories"), [self.repository])
        self.assertEqual(visible_entries(self.entries, "All"), self.entries)

    def test_select_all_and_clear_only_affect_current_view(self) -> None:
        selected: set[str] = set()
        update_selection(selected, [self.package, self.font], True)
        self.assertEqual(selected, {self.package.key, self.font.key})

        update_selection(selected, [self.font], False)
        self.assertEqual(selected, {self.package.key})

    def test_not_installed_filter_excludes_installed_and_unknown(self) -> None:
        statuses = {
            self.package.key: "Not installed",
            self.font.key: "Installed",
            self.repository.key: "Unknown",
            self.config.key: "Not installed",
        }

        self.assertEqual(
            not_installed_entries(self.entries, statuses),
            [self.package, self.config],
        )

    def test_tui_select_all_returns_selected_entries(self) -> None:
        class FakeScreen:
            def __init__(self) -> None:
                self.keys = [ord("a"), ord("i")]
                self.lines: list[str] = []

            def erase(self) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 20, 80

            def addnstr(self, *args: object) -> None:
                self.lines.append(str(args[2]))

            def refresh(self) -> None:
                pass

            def timeout(self, delay: int) -> None:
                pass

            def getch(self) -> int:
                return self.keys.pop(0)

        screen = FakeScreen()
        with (
            patch("mla.tui.get_install_status", return_value="Not installed"),
            patch("mla.tui.curses.wrapper", side_effect=lambda draw, entries: draw(screen, entries)),
        ):
            selected = run_tui(self.entries)

        self.assertEqual(selected, self.entries)
        self.assertTrue(any("MyLinuxAutomation(MLA)" in line for line in screen.lines))
        self.assertTrue(any("NOT INSTALLED" in line for line in screen.lines))
        self.assertNotIn("Text editor", screen.lines)
        self.assertNotIn("Shell prompt", screen.lines)

    def test_enter_does_not_quit_and_q_requires_confirmation(self) -> None:
        class FakeScreen:
            def __init__(self) -> None:
                self.keys = [10, ord("q"), ord("n"), ord("q"), ord("y")]
                self.lines: list[str] = []

            def erase(self) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 20, 80

            def addnstr(self, *args: object) -> None:
                self.lines.append(str(args[2]))

            def refresh(self) -> None:
                pass

            def getch(self) -> int:
                return self.keys.pop(0)

        screen = FakeScreen()
        with (
            patch("mla.tui.get_install_status", return_value="Not installed"),
            patch("mla.tui.curses.wrapper", side_effect=lambda draw, entries: draw(screen, entries)),
        ):
            selected = run_tui(self.entries)

        self.assertEqual(selected, [])
        self.assertTrue(any("Quit MyLinuxAutomation(MLA)? [y/N]" in line for line in screen.lines))

    def test_selecting_and_clearing_stays_in_current_view(self) -> None:
        class FakeScreen:
            def __init__(self) -> None:
                self.keys = [ord("2"), ord("a"), ord("n"), ord("q"), ord("n"), ord("q"), ord("y")]
                self.lines: list[str] = []

            def erase(self) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 20, 80

            def addnstr(self, *args: object) -> None:
                self.lines.append(str(args[2]))

            def refresh(self) -> None:
                pass

            def timeout(self, delay: int) -> None:
                pass

            def getch(self) -> int:
                return self.keys.pop(0)

        screen = FakeScreen()
        with (
            patch("mla.tui.get_install_status", return_value="Not installed"),
            patch("mla.tui.curses.wrapper", side_effect=lambda draw, entries: draw(screen, entries)),
        ):
            selected = run_tui(self.entries)

        self.assertEqual(selected, [])
        self.assertIn("Selected all 1 entries in Packages.", screen.lines)
        self.assertIn("Cleared selection in Packages.", screen.lines)

    def test_selection_notice_clears_and_restores_footer_controls(self) -> None:
        class FakeScreen:
            def __init__(self) -> None:
                self.keys = [ord("n"), ord("i")]
                self.lines: list[str] = []
                self.timed_out = False

            def erase(self) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 20, 80

            def addnstr(self, *args: object) -> None:
                self.lines.append(str(args[2]))

            def refresh(self) -> None:
                pass

            def timeout(self, delay: int) -> None:
                self.timed_out = delay > 0

            def getch(self) -> int:
                if self.timed_out:
                    self.timed_out = False
                    return -1
                return self.keys.pop(0)

        screen = FakeScreen()
        with (
            patch("mla.tui.get_install_status", return_value="Not installed"),
            patch("mla.tui.curses.wrapper", side_effect=lambda draw, entries: draw(screen, entries)),
        ):
            self.assertEqual(run_tui(self.entries), [])

        self.assertIn("Cleared selection in All.", screen.lines)
        self.assertIn("view", screen.lines)
        self.assertIn("quit", screen.lines)

    def test_filter_toggle_limits_selection_and_can_be_turned_off(self) -> None:
        class FakeScreen:
            def __init__(self) -> None:
                self.keys = [ord("f"), ord("a"), ord("f"), ord("a"), ord("i")]
                self.lines: list[str] = []

            def erase(self) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 20, 100

            def addnstr(self, *args: object) -> None:
                self.lines.append(str(args[2]))

            def refresh(self) -> None:
                pass

            def timeout(self, delay: int) -> None:
                pass

            def getch(self) -> int:
                return self.keys.pop(0)

        screen = FakeScreen()
        status_by_key = {
            self.package.key: "Not installed",
            self.font.key: "Installed",
            self.repository.key: "Unknown",
            self.config.key: "Not installed",
        }
        with (
            patch(
                "mla.tui.get_install_status",
                side_effect=lambda entry: status_by_key[entry.key],
            ),
            patch("mla.tui.curses.wrapper", side_effect=lambda draw, entries: draw(screen, entries)),
        ):
            selected = run_tui(self.entries)

        self.assertEqual(selected, self.entries)
        self.assertIn("NOT INSTALLED ONLY", "\n".join(screen.lines))
        self.assertIn("2 entries", "\n".join(screen.lines))

    def test_help_view_explains_catalog_types_with_examples(self) -> None:
        class FakeScreen:
            def __init__(self) -> None:
                self.keys = [ord("?"), *([ord("j")] * 30), ord("q"), ord("y")]
                self.lines: list[str] = []

            def erase(self) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 20, 100

            def addnstr(self, *args: object) -> None:
                self.lines.append(str(args[2]))

            def refresh(self) -> None:
                pass

            def getch(self) -> int:
                return self.keys.pop(0)

        screen = FakeScreen()
        with (
            patch("mla.tui.get_install_status", return_value="Not installed"),
            patch("mla.tui.curses.wrapper", side_effect=lambda draw, entries: draw(screen, entries)),
        ):
            self.assertEqual(run_tui(self.entries), [])

        help_text = "\n".join(screen.lines)
        for example in (
            "ADDING PACKAGES",
            "ADDING FONTS",
            "ADDING CONFIGS",
            "ADDING REPOSITORY COMMANDS",
            "CATEGORIES",
            "mla add starship",
            "userconfigs.json",
        ):
            with self.subTest(example=example):
                self.assertIn(example, help_text)

    def test_font_install_status_checks_font_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fonts_dir = Path(temp_dir)
            font_dir = fonts_dir / "NerdFonts" / "FiraCode"
            font_dir.mkdir(parents=True)
            with patch("mla.scripts.nerd_fonts.USER_FONTS_DIR", fonts_dir):
                self.assertEqual(get_install_status(self.font), "Not installed")
                (font_dir / "FiraCode.ttf").write_bytes(b"font")
                self.assertEqual(get_install_status(self.font), "Installed")

    def test_package_status_uses_native_package_query(self) -> None:
        manager = SimpleNamespace(query_cmd=("dpkg", "-s"), is_installed=lambda name: name == "editor")
        distro = Distro("debian", (), "Debian", "Debian", "debian")
        with (
            patch("mla.tui.get_package_manager", return_value=manager),
            patch("mla.tui.shutil.which", return_value="/usr/bin/dpkg"),
        ):
            self.assertEqual(get_install_status(self.package, distro), "Installed")

    def test_repository_without_detection_metadata_is_unknown(self) -> None:
        unknown = CatalogEntry(
            "repository",
            "custom",
            "Other",
            "Custom command",
            Repository("custom", "Custom command", "some command", "Other"),
        )
        self.assertEqual(get_install_status(unknown), "Unknown")

    def test_tui_requires_interactive_terminal(self) -> None:
        with (
            patch("mla.cli.sys.stdin.isatty", return_value=False),
            patch("mla.cli.sys.stdout.isatty", return_value=False),
        ):
            self.assertEqual(main(["tui"]), 1)

    def test_tui_installs_selected_package_after_confirmation(self) -> None:
        with (
            patch("mla.cli.sys.stdin.isatty", return_value=True),
            patch("mla.cli.sys.stdout.isatty", return_value=True),
            patch("mla.cli.load_catalog", return_value=[self.package.value]),
            patch("mla.cli.load_packages", return_value=[]),
            patch("mla.cli.load_user_configs", return_value=[]),
            patch("mla.tui.run_tui", return_value=[self.package]),
            patch("mla.tui.get_install_status", return_value="Not installed"),
            patch("mla.cli.load_user_config", return_value={"auto_yes": False}),
            patch("mla.cli.authenticate_sudo", return_value=True),
            patch("mla.cli.install_package", return_value=0) as install_package,
            patch("builtins.input", return_value="y"),
        ):
            result = _run_tui()

        self.assertEqual(result, 0)
        install_package.assert_called_once_with(self.package.value, assume_yes=False)


if __name__ == "__main__":
    unittest.main()
