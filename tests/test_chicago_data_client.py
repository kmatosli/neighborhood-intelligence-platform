from bw_observatory.config import Settings


def test_crime_endpoint_is_constructed() -> None:
    settings = Settings(_env_file=None)
    assert settings.crime_data_url == (
        "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
    )
