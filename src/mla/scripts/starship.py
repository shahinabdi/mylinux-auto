from ..utils.dotfiles import add_export, detect_shell, dotfiles_dir, append_line

INIT_LINES = {
    "bash": 'eval "$(starship init bash)"',
    "zsh": 'eval "$(starship init zsh)"',
    "fish": "starship init fish | source",
}


def configure() -> int:
    shell = detect_shell()
    line = INIT_LINES.get(shell)
    if line is None:
        print(f"Unsupported shell for starship: {shell}")
        return 1
    # exports.bash is not valid fish syntax, so fish gets its own file next to it.
    if shell == "fish":
        added = append_line("exports.fish", line)
        target = dotfiles_dir() / "exports.fish"
    else:
        added = add_export(line)
        target = dotfiles_dir() / "exports.bash"
    print(f"{'Added to' if added else 'Already present in'} {target} ({shell}): {line}")
    return 0
