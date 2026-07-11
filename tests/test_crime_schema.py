from typing import Any

from bw_observatory.validation.crime_schema import (
    CORE_RECORD_FIELDS,
    REQUIRED_CRIME_FIELDS,
    missing_coordinates,
    missing_core_fields,
    missing_required_fields,
)


def _metadata(field_names: set[str]) -> dict[str, Any]:
    return {"columns": [{"fieldName": name} for name in field_names]}


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {name: "value" for name in REQUIRED_CRIME_FIELDS}
    record.update(overrides)
    return record


def test_required_fields_are_detected() -> None:
    assert missing_required_fields(_metadata(REQUIRED_CRIME_FIELDS)) == set()


def test_missing_field_is_reported() -> None:
    metadata = _metadata(REQUIRED_CRIME_FIELDS - {"updated_on"})
    assert missing_required_fields(metadata) == {"updated_on"}


def test_missing_coordinate_columns_in_metadata_are_blocking() -> None:
    # A record may lack coordinates, but the dataset must still publish the columns.
    metadata = _metadata(REQUIRED_CRIME_FIELDS - {"latitude", "longitude"})
    assert missing_required_fields(metadata) == {"latitude", "longitude"}


def test_record_without_coordinates_is_allowed() -> None:
    record = _record()
    del record["latitude"]
    del record["longitude"]

    assert missing_core_fields(record) == set()
    assert missing_coordinates(record) == {"latitude", "longitude"}


def test_record_with_null_coordinates_is_allowed() -> None:
    record = _record(latitude=None, longitude=None)

    assert missing_core_fields(record) == set()
    assert missing_coordinates(record) == {"latitude", "longitude"}


def test_record_with_coordinates_reports_none_missing() -> None:
    assert missing_coordinates(_record()) == set()


def test_missing_core_fields_are_blocking() -> None:
    record = _record()
    for name in ("id", "date", "primary_type"):
        del record[name]

    assert missing_core_fields(record) == {"id", "date", "primary_type"}


def test_null_core_field_is_blocking() -> None:
    assert missing_core_fields(_record(case_number=None)) == {"case_number"}


def test_coordinates_are_not_core_fields() -> None:
    assert CORE_RECORD_FIELDS.isdisjoint({"latitude", "longitude"})
