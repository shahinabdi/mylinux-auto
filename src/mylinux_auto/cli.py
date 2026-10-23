import argparse
import subprocess
import sys
from collections.abc import Sequence

from .models import Repository
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


def _run(args: argparse.Namespace) -> int:
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
        return subprocess.run(repository.url, shell=True, check=False).returncode

    raise AssertionError(f"Unhandled action: {args.action}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError) as error:
        print(f"mylinux-auto: {error}", file=sys.stderr)
        return 1
