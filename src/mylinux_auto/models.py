from dataclasses import dataclass


@dataclass
class Repository:
    """A software setup command in the user's repository catalog."""

    id: int
    name: str
    description: str
    url: str
    category: str