from bw_observatory.config import Settings


def test_default_dataset_id() -> None:
    settings = Settings(_env_file=None)
    assert settings.chicago_crime_dataset_id == "ijzp-q8t2"


def test_dataset_id_override(monkeypatch) -> None:
    monkeypatch.setenv("CHICAGO_CRIME_DATASET_ID", "example-id")
    settings = Settings(_env_file=None)
    assert settings.chicago_crime_dataset_id == "example-id"
