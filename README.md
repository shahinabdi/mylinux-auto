# mylinux-auto

`mylinux-auto` is a small command-line catalog for Linux software setup
commands. It can list, search, inspect, add, and remove catalog entries. The
`install` command runs the selected entry's shell command.

## Install

From a checkout with [uv](https://docs.astral.sh/uv/) installed:

```sh
uv tool install .
```

Or run the app from the project:

```sh
uv run mylinux-auto --help
```

## Usage

```sh
mylinux-auto list
mylinux-auto list --category Shell
mylinux-auto search rust
mylinux-auto show uv
mylinux-auto add ripgrep "Fast recursive search" "cargo install ripgrep" Rust
mylinux-auto remove ripgrep
mylinux-auto install uv
```

Entries can be selected by name or numeric ID. `install` prints the command
and asks for confirmation before running it. Use `--yes` to skip the prompt
when running deliberately in a script:

```sh
mylinux-auto install uv --yes
```

Catalog commands are shell commands and may make system changes. Only install
entries from a catalog you trust. The default catalog is stored at
`src/mla/data/repositories.json`; set `REPOSITORY_FILE` to use a
different JSON catalog.

## Catalog format

The catalog is a JSON array. Each entry has a unique positive integer `id`,
unique `name`, `description`, shell command in `url`, and `category`. The
application validates entries and writes updates atomically.
