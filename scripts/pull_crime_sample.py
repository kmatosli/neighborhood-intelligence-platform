from __future__ import annotations

import json
from pathlib import Path

from bw_observatory.clients.chicago_data import ChicagoDataClient
from bw_observatory.config import Settings


def main() -> None:
    settings = Settings()
    client = ChicagoDataClient(settings)

    where = "date >= '2025-01-01T00:00:00.000'"
    records = client.get_crimes(limit=100, where=where)

    output_dir = settings.data_dir / "bronze"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "crime_sample.json"
    output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    print(f"Saved {len(records)} records to {output_path}")


if __name__ == "__main__":
    main()
