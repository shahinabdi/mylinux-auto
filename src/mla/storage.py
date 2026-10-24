import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from .config import get_data_file
from .models import Repository


def _validate_repositories(repositories: list[Repository]) -> None:
    seen_ids: set[int] = set()
    seen_names: set[str] = set()

    for repository in repositories:
        if isinstance(repository.id, bool) or not isinstance(repository.id, int) or repository.id < 1:
            raise ValueError("Repository IDs must be positive integers.")
        for field_name in ("name", "description", "url", "category"):
            value = getattr(repository, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Repository {repository.id} has an empty or invalid {field_name}.")
        if repository.id in seen_ids:
            raise ValueError(f"Duplicate repository ID: {repository.id}.")
        normalized_name = repository.name.casefold()
        if normalized_name in seen_names:
            raise ValueError(f"Duplicate repository name: {repository.name}.")
        seen_ids.add(repository.id)
        seen_names.add(normalized_name)


def load_packages() -> list[Repository]:
    data_file = get_data_file()
    try:
        with data_file.open(encoding="utf-8") as file:
            raw_repositories = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in repository catalog {data_file}: {error}") from error

    if not isinstance(raw_repositories, list):
        raise ValueError(f"Repository catalog {data_file} must contain a JSON list.")

    repositories: list[Repository] = []
    for index, item in enumerate(raw_repositories):
        if not isinstance(item, dict):
            raise ValueError(f"Repository entry {index + 1} in {data_file} must be a JSON object.")
        try:
            repositories.append(Repository(**item))
        except TypeError as error:
            raise ValueError(f"Invalid repository entry {index + 1} in {data_file}: {error}") from error

    _validate_repositories(repositories)
    return repositories

def save_packages(repositories: list[Repository]) -> None:
    _validate_repositories(repositories)
    data_file = get_data_file()
    data_file.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=data_file.parent,
            prefix=f".{data_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump([asdict(repo) for repo in repositories], file, indent=2, ensure_ascii=False)
            file.write("\n")
        temporary_path.replace(data_file)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

def next_repository_id(repositories: list[Repository]) -> int:
    return max((repo.id for repo in repositories), default=0) + 1