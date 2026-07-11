from bw_observatory.clients.chicago_data import ChicagoDataClient, ChicagoDataError
from bw_observatory.config import Settings
from bw_observatory.validation.crime_schema import (
    missing_required_fields,
    validate_record_shape,
)


def main() -> int:
    settings = Settings()
    client = ChicagoDataClient(settings)

    try:
        metadata = client.get_metadata()
        missing_metadata = missing_required_fields(metadata)
        if missing_metadata:
            print(f"BLOCKING: missing metadata fields: {sorted(missing_metadata)}")
            return 1

        records = client.get_crimes(limit=10)
        if not records:
            print("BLOCKING: API returned no records.")
            return 1

        invalid = [
            {"index": index, "missing": sorted(validate_record_shape(record))}
            for index, record in enumerate(records)
            if validate_record_shape(record)
        ]
        if invalid:
            print(f"BLOCKING: invalid record shapes: {invalid}")
            return 1

        print("Chicago crime API check passed.")
        print(f"Dataset ID: {settings.chicago_crime_dataset_id}")
        print(f"Records validated: {len(records)}")
        print(f"Latest returned incident date: {records[0].get('date')}")
        return 0
    except ChicagoDataError as exc:
        print(f"BLOCKING: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
