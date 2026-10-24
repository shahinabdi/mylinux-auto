import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mla.models import UserConfig
from mla.user_configs import get_config_status, install_user_config, load_user_configs


class UserConfigTests(unittest.TestCase):
    def test_loads_builtin_config_catalog(self) -> None:
        config_list = load_user_configs()
        configs = {config.name for config in config_list}
        self.assertTrue({"GitConfig", "EzaAliases", "Tmux", "Alacritty", "Kitty", "Neovim"} <= configs)
        git_config = next(config for config in config_list if config.name == "GitConfig")
        self.assertEqual(
            git_config.upstream_installer_url,
            "https://raw.githubusercontent.com/shahinabdi/git-config/main/setup-git-config.sh",
        )

    def test_installs_template_to_mla_config_dir_and_symlinks_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_data = root / "package-data"
            template = package_data / "data" / "user-configs" / "tmux" / "tmux.conf"
            template.parent.mkdir(parents=True)
            template.write_text("set -g mouse on\n", encoding="utf-8")
            mla_config_dir = root / "home" / ".config" / "mla"
            home_dir = root / "home"
            config = UserConfig(
                "Tmux",
                "Starter tmux configuration",
                "Terminal",
                "tmux/tmux.conf",
                ".config/tmux/tmux.conf",
            )

            with (
                patch("mla.user_configs.BASE_DIR", package_data),
                patch("mla.user_configs.get_mla_config_dir", return_value=mla_config_dir),
                patch.object(Path, "home", return_value=home_dir),
            ):
                self.assertEqual(get_config_status(config), "Not installed")
                self.assertEqual(install_user_config(config), 0)
                source = mla_config_dir / "configs" / "tmux" / "tmux.conf"
                target = home_dir / ".config" / "tmux" / "tmux.conf"
                self.assertEqual(source.read_text(encoding="utf-8"), "set -g mouse on\n")
                self.assertTrue(target.is_symlink())
                self.assertEqual(target.resolve(), source.resolve())
                self.assertEqual(get_config_status(config), "Installed")
                self.assertEqual(install_user_config(config), 0)

    def test_does_not_replace_existing_config_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_data = root / "package-data"
            template = package_data / "data" / "user-configs" / "tmux" / "tmux.conf"
            template.parent.mkdir(parents=True)
            template.write_text("starter\n", encoding="utf-8")
            home_dir = root / "home"
            target = home_dir / ".config" / "tmux" / "tmux.conf"
            target.parent.mkdir(parents=True)
            target.write_text("user data\n", encoding="utf-8")
            config = UserConfig(
                "Tmux",
                "Starter tmux configuration",
                "Terminal",
                "tmux/tmux.conf",
                ".config/tmux/tmux.conf",
            )

            with (
                patch("mla.user_configs.BASE_DIR", package_data),
                patch("mla.user_configs.get_mla_config_dir", return_value=root / "mla"),
                patch.object(Path, "home", return_value=home_dir),
            ):
                self.assertEqual(install_user_config(config), 1)
                self.assertEqual(target.read_text(encoding="utf-8"), "user data\n")
                self.assertEqual(get_config_status(config), "Conflict")

    def test_rejects_catalog_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "userconfigs.json"
            catalog_path.write_text(
                json.dumps(
                    [{
                        "name": "Bad",
                        "description": "Bad config",
                        "category": "Test",
                        "source": "../outside",
                        "target": ".config/test",
                    }]
                ),
                encoding="utf-8",
            )
            with patch("mla.user_configs.get_user_configs_file", return_value=catalog_path):
                with self.assertRaisesRegex(ValueError, "Invalid source path"):
                    load_user_configs()

    def test_upstream_git_installer_backs_up_existing_configs_and_records_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_dir = Path(temp_dir) / "home"
            home_dir.mkdir()
            mla_dir = home_dir / ".config" / "mla"
            existing = {
                ".gitconfig": "old git config",
                ".gitignore_global": "old ignore rules",
                ".gitmessage": "old commit template",
            }
            for filename, content in existing.items():
                (home_dir / filename).write_text(content, encoding="utf-8")
            config = UserConfig(
                "GitConfig",
                "Git config",
                "Git",
                "git/.gitconfig",
                ".gitconfig",
                "https://example.com/setup-git-config.sh",
            )
            with (
                patch.object(Path, "home", return_value=home_dir),
                patch("mla.user_configs.get_mla_config_dir", return_value=mla_dir),
                patch("mla.user_configs.urllib.request.urlopen", return_value=io.BytesIO(b"echo setup")) as urlopen,
                patch("mla.user_configs.subprocess.run", return_value=type("Result", (), {"returncode": 0})()) as run,
                patch("builtins.input", return_value="y"),
            ):
                self.assertEqual(install_user_config(config), 0)
                self.assertEqual(get_config_status(config), "Installed")

            urlopen.assert_called_once_with(config.upstream_installer_url, timeout=30)
            run.assert_called_once_with(["bash"], input="echo setup", text=True, check=False)
            for filename, content in existing.items():
                self.assertEqual(
                    (home_dir / f"{filename}.mla.bak").read_text(encoding="utf-8"),
                    content,
                )
    def test_git_config_can_choose_mla_starter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_data = root / "package-data"
            template = package_data / "data" / "user-configs" / "git" / ".gitconfig"
            template.parent.mkdir(parents=True)
            template.write_text("[init]\n    defaultBranch = main\n", encoding="utf-8")
            home_dir = root / "home"
            config = UserConfig(
                "GitConfig",
                "Git config",
                "Git",
                "git/.gitconfig",
                ".gitconfig",
                "https://example.com/setup-git-config.sh",
            )
            with (
                patch.object(Path, "home", return_value=home_dir),
                patch("mla.user_configs.BASE_DIR", package_data),
                patch("mla.user_configs.get_mla_config_dir", return_value=home_dir / ".config" / "mla"),
                patch("mla.user_configs._install_upstream_config") as upstream,
                patch("builtins.input", return_value="n"),
            ):
                self.assertEqual(install_user_config(config), 0)

            upstream.assert_not_called()
            self.assertTrue((home_dir / ".gitconfig").is_symlink())


if __name__ == "__main__":
    unittest.main()
