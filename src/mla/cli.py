import argparse
import subprocess
import sys
from collections.abc import Sequence

from .models import Package, Repository, UserConfig
from .config import DEFAULT_SOURCE_ORDER, authenticate_sudo, get_user_config_file, load_user_config, save_user_config
from .packages import ensure_flatpak, ensure_yay, find_package, install_package, load_catalog
from .utils.distro import detect_distro
from .storage import load_packages, save_packages
from .user_configs import install_user_config, load_user_configs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mla",
        description="Manage and run your Linux software setup command catalog.",
    )
    commands = parser.add_subparsers(dest="action", required=True)

    list_parser = commands.add_parser("list", help="List catalog entries.")
    list_parser.add_argument("--category", help="Show only entries in this category.")

    search_parser = commands.add_parser("search", help="Search repository names, descriptions, and categories.")
    search_parser.add_argument("query", help="Text to search for.")

    show_parser = commands.add_parser("show", help="Show an entry and its setup command.")
    show_parser.add_argument("entry", help="Repository name.")

    add_parser = commands.add_parser("add", help="Add a setup command to the catalog.")
    add_parser.add_argument("name")
    add_parser.add_argument("description")
    add_parser.add_argument("command", help="Shell command to run when installing this entry.")
    add_parser.add_argument("category")

    remove_parser = commands.add_parser("remove", help="Remove an entry from the catalog.")
    remove_parser.add_argument("entry", help="Repository name.")

    install_parser = commands.add_parser(
        "install",
        help="Run an entry's shell command after confirmation.",
    )
    install_parser.add_argument("entry", help="Repository name.")
    install_parser.add_argument(
        "--yes",
        action="store_true",
        help="Run without an interactive confirmation prompt.",
    )

    init_parser = commands.add_parser("init", help="First-time setup: save distro, sudo password and install preferences.")
    init_parser.add_argument("--sources", help="Comma-separated order, e.g. aur,native,flatpak.")
    commands.add_parser("pkgs", help="List packages installable by name.")
    get_parser = commands.add_parser("get", help="Install a package by name for this distro.")
    get_parser.add_argument("package")
    get_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts.")
    get_parser.add_argument("--ask", action="store_true", help="Keep package manager prompts even if auto_yes is on.")
    get_parser.add_argument("--dry-run", action="store_true", help="Print the command without running it.")
    get_parser.add_argument("--flatpak", action="store_true", help="Prefer the Flatpak version.")
    setup_parser = commands.add_parser("setup", help="Install helper tools (yay, flatpak).")
    setup_parser.add_argument("tool", choices=["yay", "flatpak", "starship"])
    setup_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts.")
    setup_parser.add_argument("--ask", action="store_true", help="Keep prompts even if auto_yes is on.")
    commands.add_parser("distro", help="Show the detected Linux distribution.")
    commands.add_parser("configs", help="List available user configuration templates.")
    config_parser = commands.add_parser("config", help="Activate a user configuration template.")
    config_parser.add_argument("name", help="User config name.")
    commands.add_parser(
        "tui",
        help="Browse and install packages, fonts, configs, and repositories interactively.",
    )

    return parser


def _find_repository(repositories: list[Repository], entry: str) -> Repository | None:
    normalized_entry = entry.casefold()
    return next((repo for repo in repositories if repo.name.casefold() == normalized_entry), None)


def _print_repository(repository: Repository) -> None:
    print(repository.name)
    print(f"Category: {repository.category}")
    print(f"Description: {repository.description}")
    print(f"Command: {repository.url}")


def _list_repositories(repositories: list[Repository], category: str | None = None) -> None:
    if category is not None:
        repositories = [
            repo for repo in repositories if repo.category.casefold() == category.casefold()
        ]
    if not repositories:
        print("No catalog entries found.")
        return

    name_width = max(len("NAME"), *(len(repo.name) for repo in repositories))
    category_width = max(len("CATEGORY"), *(len(repo.category) for repo in repositories))
    print(f"{'NAME':<{name_width}}  {'CATEGORY':<{category_width}}  DESCRIPTION")
    for repository in sorted(repositories, key=lambda repo: repo.name.casefold()):
        print(
            f"{repository.name:<{name_width}}  {repository.category:<{category_width}}  "
            f"{repository.description}"
        )


def _init(args: argparse.Namespace) -> int:
    import getpass

    distro = detect_distro()
    print(f"Detected: {distro.pretty_name} (family: {distro.family})")
    config = load_user_config()
    config["distro"] = {"id": distro.id, "family": distro.family, "pretty_name": distro.pretty_name}

    default = ",".join(config.get("source_order") or DEFAULT_SOURCE_ORDER)
    raw = args.sources or input(f"Install source order (native, aur, flatpak) [{default}]: ").strip() or default
    sources = [item.strip() for item in raw.split(",") if item.strip()]
    if not sources or any(item not in ("native", "aur", "flatpak") for item in sources):
        print("Sources must be from: native, aur, flatpak.", file=sys.stderr)
        return 1
    config["source_order"] = sources
    config["auto_yes"] = input("Skip package manager confirmation prompts (auto yes)? [Y/n]: ").strip().lower() != "n"
    config.setdefault("package_sources", {})

    if input("Store sudo password in the config file in PLAIN TEXT (chmod 600)? [y/N]: ").strip().lower() == "y":
        config["password"] = getpass.getpass("sudo password: ")
    else:
        config.pop("password", None)

    path = save_user_config(config)
    print(f"Saved {path}. Per-package overrides go in \"package_sources\", e.g. {{\"firefox\": \"flatpak\"}}.")
    return 0


def _run_tui() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("The TUI requires an interactive terminal.", file=sys.stderr)
        return 1

    from .tui import CatalogEntry, get_install_status, run_tui

    packages = load_catalog()
    repositories = load_packages()
    user_configs = load_user_configs()
    entries = [
        CatalogEntry("package", package.name, package.category, package.description, package)
        for package in packages
    ] + [
        CatalogEntry(
            "repository",
            repository.name,
            repository.category,
            repository.description,
            repository,
        )
        for repository in repositories
    ] + [
        CatalogEntry(
            "config",
            config.name,
            config.category,
            config.description,
            config,
        )
        for config in user_configs
    ]
    selected = run_tui(entries)
    if not selected:
        return 0

    already_installed = [entry for entry in selected if get_install_status(entry) == "Installed"]
    pending = [entry for entry in selected if entry not in already_installed]
    if already_installed:
        print("Already installed; will skip:")
        for entry in already_installed:
            print(f"  {entry.kind}: {entry.name}")
    if not pending:
        return 0

    print("Selected entries:")
    for entry in pending:
        print(f"  {entry.kind}: {entry.name}")
    try:
        confirmation = input(
            f"Install {len(pending)} selected "
            f"entr{'y' if len(pending) == 1 else 'ies'}? [y/N] "
        )
    except EOFError:
        confirmation = ""
    if confirmation.strip().casefold() not in {"y", "yes"}:
        print("Installation cancelled.")
        return 1

    needs_sudo = any(
        isinstance(entry.value, Package) and not entry.value.font_asset
        for entry in pending
    )
    if needs_sudo and not load_user_config().get("password") and not authenticate_sudo():
        print("Authentication failed.", file=sys.stderr)
        return 1

    auto_yes = load_user_config().get("auto_yes", True)
    failed = False
    for entry in pending:
        print(f"\nInstalling {entry.name} ({entry.kind})...")
        if isinstance(entry.value, Package):
            code = install_package(entry.value, assume_yes=auto_yes)
            if code == 0 and entry.name == "docker":
                from .scripts.docker import post_install

                code = post_install()
        elif isinstance(entry.value, Repository):
            code = subprocess.run(entry.value.url, shell=True, check=False).returncode
            if code == 0 and entry.name == "starship":
                from .scripts.starship import configure

                code = configure()
        else:
            code = install_user_config(entry.value)
        if code != 0:
            print(f"Installation failed for {entry.name} (exit code {code}).", file=sys.stderr)
            failed = True
    return 1 if failed else 0


def _run(args: argparse.Namespace) -> int:
    if args.action == "init":
        return _init(args)

    if args.action == "tui":
        return _run_tui()

    if args.action == "pkgs":
        for package in load_catalog():
            print(f"{package.name:20} {package.category:10} {package.description}")
        return 0

    package_to_install = find_package(args.package) if args.action == "get" else None
    if args.action == "get" and package_to_install is None:
        print(f"Package not found: {args.package}", file=sys.stderr)
        return 1

    needs_sudo = (
        (args.action == "get" and package_to_install is not None and not package_to_install.font_asset)
        or (args.action == "setup" and args.tool != "starship")
    )
    if needs_sudo and not getattr(args, "dry_run", False):
        if not load_user_config().get("password") and not authenticate_sudo():
            print("Authentication failed.", file=sys.stderr)
            return 1

    auto_yes = getattr(args, "yes", False) or (load_user_config().get("auto_yes", True) and not getattr(args, "ask", False))

    if args.action == "get":
        assert package_to_install is not None
        code = install_package(
            package_to_install,
            assume_yes=auto_yes,
            prefer_flatpak=args.flatpak,
            dry_run=args.dry_run,
        )
        if code == 0 and package_to_install.name == "docker" and not args.dry_run:
            from .scripts.docker import post_install

            return post_install()
        return code

    if args.action == "setup":
        if args.tool == "starship":
            from .scripts.starship import configure

            return configure()
        ok = ensure_yay(assume_yes=auto_yes) if args.tool == "yay" else ensure_flatpak(assume_yes=auto_yes)
        return 0 if ok else 1

    if args.action == "distro":
        distro = detect_distro()
        print(f"{distro.pretty_name} (id={distro.id}, family={distro.family})")
        return 0

    if args.action == "configs":
        configs = load_user_configs()
        for config in configs:
            print(f"{config.name:16} {config.category:10} {config.description}")
        return 0

    if args.action == "config":
        config = next(
            (item for item in load_user_configs() if item.name.casefold() == args.name.casefold()),
            None,
        )
        if config is None:
            print(f"User config not found: {args.name}", file=sys.stderr)
            return 1
        return install_user_config(config)

    repositories = load_packages()

    if args.action == "list":
        _list_repositories(repositories, args.category)
        return 0

    if args.action == "search":
        query = args.query.casefold()
        matches = [
            repository
            for repository in repositories
            if query
            in " ".join(
                (repository.name, repository.description, repository.category)
            ).casefold()
        ]
        _list_repositories(matches)
        return 0

    if args.action == "add":
        if _find_repository(repositories, args.name) is not None:
            print(f"An entry named {args.name!r} already exists.", file=sys.stderr)
            return 2
        repository = Repository(
            name=args.name,
            description=args.description,
            url=args.command,
            category=args.category,
        )
        repositories.append(repository)
        save_packages(repositories)
        print(f"Added {repository.name}.")
        return 0

    repository = _find_repository(repositories, args.entry)
    if repository is None:
        print(f"No catalog entry found for {args.entry!r}.", file=sys.stderr)
        return 2

    if args.action == "show":
        _print_repository(repository)
        return 0

    if args.action == "remove":
        repositories.remove(repository)
        save_packages(repositories)
        print(f"Removed {repository.name}.")
        return 0

    if args.action == "install":
        print(f"About to run the catalog shell command for {repository.name}:")
        print(f"  {repository.url}")
        if not args.yes:
            try:
                confirmation = input("Continue? [y/N] ").strip().casefold()
            except EOFError:
                confirmation = ""
            if confirmation not in {"y", "yes"}:
                print("Installation cancelled.")
                return 1
        code = subprocess.run(repository.url, shell=True, check=False).returncode
        if code == 0 and repository.name == "starship":
            from .scripts.starship import configure

            return configure()
        return code

    raise AssertionError(f"Unhandled action: {args.action}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError) as error:
        print(f"mla: {error}", file=sys.stderr)
        return 1
