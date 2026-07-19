from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# A directory is the project root when it holds both of these. Checking two markers rather
# than one avoids matching some unrelated parent that happens to contain a `config/`.
_ROOT_MARKERS = ("pyproject.toml", "config")


def find_repo_root(start: Path | None = None) -> Path:
    """The directory holding `pyproject.toml` and `config/`.

    Locally everything is launched from the repository root, so a relative `data/...` or
    `config/...` happens to resolve. A deployed process has no such guarantee: Render sets
    the working directory from the service definition, and the data bundle is unpacked
    wherever `BW_DATA_DIR` points. Anchoring the defaults to the installed package means the
    API reads the same files whatever directory it was started from.

    Searched outwards from this file first, which is correct for the editable install used in
    development and in the Render build, then from the working directory. Falls back to the
    working directory so a failure surfaces as a "file not found" naming a real path rather
    than an import-time crash.
    """
    origin = (start or Path(__file__)).resolve()
    for candidate in (origin, *origin.parents):
        if all((candidate / marker).exists() for marker in _ROOT_MARKERS):
            return candidate

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if all((candidate / marker).exists() for marker in _ROOT_MARKERS):
            return candidate

    return cwd


REPO_ROOT = find_repo_root()


class Settings(BaseSettings):
    chicago_data_app_token: str | None = None
    chicago_data_domain: str = "data.cityofchicago.org"
    chicago_crime_dataset_id: str = "ijzp-q8t2"

    # BW_DATA_DIR is what the deployment sets: the API and the data bundle must agree on one
    # location. DATA_DIR stays accepted so existing local .env files keep working.
    data_dir: Path = Field(
        default=REPO_ROOT / "data",
        validation_alias=AliasChoices("BW_DATA_DIR", "DATA_DIR"),
    )
    config_dir: Path = Field(
        default=REPO_ROOT / "config",
        validation_alias=AliasChoices("BW_CONFIG_DIR", "CONFIG_DIR"),
    )

    log_dir: Path = Field(
        default=REPO_ROOT / "logs",
        validation_alias=AliasChoices("BW_LOG_DIR", "LOG_DIR"),
    )
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Required because the directory fields carry a validation_alias. Without it, an
        # alias replaces the field name outright, so `Settings(data_dir=...)` would be
        # silently dropped by extra="ignore" and fall back to the real data directory —
        # which would point tests and callers at production data instead of their tmp path.
        populate_by_name=True,
    )

    @property
    def crime_data_url(self) -> str:
        return f"https://{self.chicago_data_domain}/resource/{self.chicago_crime_dataset_id}.json"

    @property
    def crime_metadata_url(self) -> str:
        return f"https://{self.chicago_data_domain}/api/views/{self.chicago_crime_dataset_id}"

    @property
    def crime_categories_config(self) -> Path:
        return self.config_dir / "crime_categories.yml"

    @property
    def neighborhood_config(self) -> Path:
        return self.config_dir / "neighborhoods" / "neighborhoods.yml"

    @property
    def bronzeville_geojson(self) -> Path:
        return self.config_dir / "neighborhoods" / "bronzeville.geojson"
