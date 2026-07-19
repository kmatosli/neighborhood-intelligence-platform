from __future__ import annotations

from typing import Any

COORDINATE_FIELDS = {
    "latitude",
    "longitude",
}

# Every column the dataset must publish, coordinates included. The dataset losing a
# coordinate column is a schema break; an individual incident lacking coordinates is not.
REQUIRED_CRIME_FIELDS = {
    "id",
    "case_number",
    "date",
    "block",
    "iucr",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "domestic",
    "beat",
    "district",
    "ward",
    "community_area",
    "year",
    "updated_on",
    *COORDINATE_FIELDS,
}

# Fields an incident cannot be identified or analyzed without. The remaining columns
# (block, description, ward, ...) are nullable in the source data, and Socrata omits
# null values from its JSON entirely, so their absence is not treated as a defect.
CORE_RECORD_FIELDS = {
    "id",
    "case_number",
    "date",
    "iucr",
    "primary_type",
    "arrest",
    "domestic",
    "year",
    "updated_on",
}


def metadata_field_names(metadata: dict[str, Any]) -> set[str]:
    columns = metadata.get("columns", [])
    if not isinstance(columns, list):
        return set()

    names: set[str] = set()
    for column in columns:
        if isinstance(column, dict):
            field_name = column.get("fieldName")
            if isinstance(field_name, str):
                names.add(field_name)
    return names


def missing_required_fields(metadata: dict[str, Any]) -> set[str]:
    return REQUIRED_CRIME_FIELDS - metadata_field_names(metadata)


def _present_fields(record: dict[str, Any]) -> set[str]:
    return {name for name, value in record.items() if value is not None}


def missing_core_fields(record: dict[str, Any]) -> set[str]:
    """Core fields absent from a record. Any result here is a blocking defect."""
    return CORE_RECORD_FIELDS - _present_fields(record)


def missing_coordinates(record: dict[str, Any]) -> set[str]:
    """Coordinate fields absent from a record. Expected in practice; warn, do not block."""
    return COORDINATE_FIELDS - _present_fields(record)
