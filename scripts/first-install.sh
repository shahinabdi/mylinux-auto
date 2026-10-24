#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
    if ! command -v curl >/dev/null 2>&1; then
        printf 'Error: curl is required to install uv.\n' >&2
        exit 1
    fi

    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    printf 'Error: uv installation completed, but uv is not available in PATH.\n' >&2
    exit 1
fi

uv tool install --force "$repo_root"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v mla >/dev/null 2>&1; then
    printf 'Error: mla was installed, but the command is not available in PATH.\n' >&2
    exit 1
fi

exec mla init "$@"
