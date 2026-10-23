import os
from pathlib import Path

BASE_DIR = Path(__file__).parent




def get_data_file() -> Path:
    override = os.environ.get("REPOSITORY_FILE")
    return Path(override) if override else BASE_DIR / "data" / "repositories.json"