import argparse
import subprocess
import sys
from collections.abc import Sequence

from .models import Repository
from .config import DEFAULT_SOURCE_ORDER, authenticate_sudo, get_user_config_file, load_user_config, save_user_config
from .packages import ensure_flatpak, ensure_yay, find_package, install_package, load_catalog
from .utils.distro import detect_distro
from .storage import load_packages, next_repository_id, save_packages


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mylinux-auto",
        description="Manage and run your Linux software setup command catalog.",
    )
    commands = parser.add_subparsers(dest="action", required=True)

    list_parser = commands.add_parser("list", help="List catalog entries.")
    list_parser.add_argument("--category", help="Show only entries in this category.")

    search_parser = commands.add_parser("search", help="Search names, descriptions, and categories.")
    search_parser.add_argument("query", help="Text to search for.")

    show_parser = commands.add_parser("show", help="Show an entry and its setup command.")
    show_parser.add_argument("entry", help="Entry name or numeric ID.")

    add_parser = commands.add_parser("add", help="Add a setup command to the catalog.")
    add_parser.add_argument("name")
    add_parser.add_argument("description")
    add_parser.add_argument("command", help="Shell command to run when installing this entry.")
    add_parser.add_argument("category")

    remove_parser = commands.add_parser("remove", help="Remove an entry from the catalog.")
    remove_parser.add_argument("entry", help="Entry name or numeric ID.")

    install_parser = commands.add_parser(
        "install",
        help="Run an entry's shell command after confirmation.",
    )
    install_parser.add_argument("entry", help="Entry name or numeric ID.")
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

    return parser


def _find_repository(repositories: list[Repository], entry: str) -> Repository | None:
    if entry.isdecimal():
        repository_id = int(entry)
        return next((repo for repo in repositories if repo.id == repository_id), None)
    normalized_entry = entry.casefold()
    return next((repo for repo in repositories if repo.name.casefold() == normalized_entry), None)


def _print_repository(repository: Repository) -> None:
    print(f"{repository.name} (ID: {repository.id})")
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
    print(f"{'ID':>3}  {'NAME':<{name_width}}  {'CATEGORY':<{category_width}}  DESCRIPTION")
    for repository in sorted(repositories, key=lambda repo: repo.name.casefold()):
        print(
            f"{repository.id:>3}  {repository.name:<{name_width}}  "
            f"{repository.category:<{category_width}}  {repository.description}"
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


def _run(args: argparse.Namespace) -> int:
    if args.action == "init":
        return _init(args)

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
            id=next_repository_id(repositories),
            name=args.name,
            description=args.description,
            url=args.command,
            category=args.category,
        )
        repositories.append(repository)
        save_packages(repositories)
        print(f"Added {repository.name} (ID: {repository.id}).")
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
        print(f"mylinux-auto: {error}", file=sys.stderr)
        return 1
