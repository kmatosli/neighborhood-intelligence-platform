from bw_observatory.validation.crime_schema import (
    REQUIRED_CRIME_FIELDS,
    missing_required_fields,
)


def test_required_fields_are_detected() -> None:
    metadata = {
        "columns": [{"fieldName": name} for name in REQUIRED_CRIME_FIELDS]
    }
    assert missing_required_fields(metadata) == set()


def test_missing_field_is_reported() -> None:
    metadata = {
        "columns": [
            {"fieldName": name}
            for name in REQUIRED_CRIME_FIELDS
            if name != "updated_on"
        ]
    }
    assert missing_required_fields(metadata) == {"updated_on"}
