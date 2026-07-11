from __future__ import annotations

from typing import Any

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
    "latitude",
    "longitude",
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


def validate_record_shape(record: dict[str, Any]) -> set[str]:
    return REQUIRED_CRIME_FIELDS - set(record)
