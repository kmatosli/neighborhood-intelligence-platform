from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    chicago_data_app_token: str | None = None
    chicago_data_domain: str = "data.cityofchicago.org"
    chicago_crime_dataset_id: str = "ijzp-q8t2"
    data_dir: Path = Path("data")
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def crime_data_url(self) -> str:
        return f"https://{self.chicago_data_domain}/resource/{self.chicago_crime_dataset_id}.json"

    @property
    def crime_metadata_url(self) -> str:
        return f"https://{self.chicago_data_domain}/api/views/{self.chicago_crime_dataset_id}"
