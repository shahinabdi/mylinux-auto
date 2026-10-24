# mla

`mla` is a small command-line catalog for Linux software setup
commands. It can list, search, inspect, add, and remove catalog entries. The
`install` command runs the selected entry's shell command.

## Install

From a checkout with [uv](https://docs.astral.sh/uv/) installed:

```sh
uv tool install .
```

Or run the app from the project:

```sh
uv run mla --help
```

For first-time setup from a checkout, run the bootstrap script. It installs
`uv` if needed, installs this project as a tool, and launches `mla init`:

```sh
./scripts/first-install.sh
```

## Usage

```sh
mla list
mla list --category Shell
mla search rust
mla show uv
mla add ripgrep "Fast recursive search" "cargo install ripgrep" Rust
mla remove ripgrep
mla install uv
mla get FiraCode
mla config Tmux
mla configs
mla tui
```

The package catalog includes tmux, Alacritty, Kitty, and eza, as well as the
available Nerd Fonts. The `tui` command shows packages, fonts, configs, and
repository commands in one place. Use the arrow keys to navigate, Space to
toggle an entry, `a` to select all in the current view, `n` to clear that
view, and `i` to install selected entries. Installed packages and fonts are
detected automatically. Repository entries can set an `installed_check`
executable in `repositories.json`; entries without one show an unknown status.
Press `?` or choose the Help tab for in-TUI instructions and examples showing
how to add packages, fonts, configs, and repository commands.

User config templates are cataloged in `src/mla/data/userconfigs.json`.
`mla configs` lists them and `mla config <name>` activates one. MLA copies a
starter template into `~/.config/mla/configs/` the first time it is selected,
then symlinks it to the application's conventional config path. Edit the
managed file under `~/.config/mla/configs/` to customize it. Existing target
files are never overwritten; move a conflicting file aside before activating
its template. GitConfig offers the preferred upstream installer from
`shahinabdi/git-config` or the MLA starter config. The upstream option prompts
for your Git identity and profile, backs up existing Git config files, and
installs `.gitconfig`, `.gitignore_global`, and `.gitmessage` in your home
directory.

Repository entries can be selected by name. `install` prints the command and
asks for confirmation before running it. Use `--yes` to skip the prompt when
running deliberately in a script:

```sh
mla install uv --yes
```

Catalog commands are shell commands and may make system changes. Only install
entries from a catalog you trust. The default catalog is stored at
`src/mla/data/repositories.json`; set `REPOSITORY_FILE` to use a
different JSON catalog.

The package catalog also includes FiraCode, Go-Mono, Hack, Meslo,
JetBrainsMono, and Ubuntu Nerd Fonts. Install each with
`mla get <font-name>`. Nerd Fonts are installed for the current user;
their shared release version is configured by `NERD_FONTS_VERSION` in
`src/mla/scripts/nerd_fonts.py`.

## Catalog format

The repository catalog is a JSON array. Each entry has a unique `name`,
`description`, shell command in `url`, and `category`. The application
validates entries and writes updates atomically. Legacy repository IDs are
ignored when loading older catalogs.
