from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bw_observatory.config import Settings


class ChicagoDataError(RuntimeError):
    """Raised when the Chicago Data Portal cannot be queried safely."""


class ChicagoDataClient:
    def __init__(self, settings: Settings, timeout_seconds: float = 30.0) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.settings.chicago_data_app_token:
            headers["X-App-Token"] = self.settings.chicago_data_app_token
        return headers

    # The retry sits on the raw request, not on the public methods. Timeouts and transport
    # errors are subclasses of httpx.HTTPError, so wrapping them in ChicagoDataError inside
    # the retried call would hide them from tenacity and no retry would ever fire.
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        reraise=True,
    )
    def _request_json(self, url: str, params: dict[str, str | int] | None = None) -> Any:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            return response.json()

    def get_metadata(self) -> dict[str, Any]:
        try:
            payload = self._request_json(self.settings.crime_metadata_url)
        except (httpx.HTTPError, ValueError) as exc:
            raise ChicagoDataError(f"Metadata request failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise ChicagoDataError("Metadata response was not an object.")
        return payload

    def get_crimes(
        self,
        *,
        limit: int = 10,
        where: str | None = None,
        order: str = "date DESC, id DESC",
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 50_000:
            raise ValueError("limit must be between 1 and 50,000")
        if offset < 0:
            raise ValueError("offset must not be negative")

        params: dict[str, str | int] = {
            "$limit": limit,
            "$order": order,
        }
        if offset:
            params["$offset"] = offset
        if where:
            params["$where"] = where

        try:
            payload = self._request_json(self.settings.crime_data_url, params)
        except (httpx.HTTPError, ValueError) as exc:
            raise ChicagoDataError(f"Crime data request failed: {exc}") from exc

        if not isinstance(payload, list):
            raise ChicagoDataError("Crime response was not a list.")
        if not all(isinstance(item, dict) for item in payload):
            raise ChicagoDataError("Crime response contained an invalid record.")
        return payload

    def list_crime_ids(self, *, where: str, limit: int = 50_000, offset: int = 0) -> list[str]:
        """One page of record ids for a filter, ordered by id. Reconciliation compares the
        full id set of a year against the local partition; ids alone are ~1% of the row
        payload, so a year is a handful of requests rather than a re-download."""
        if limit < 1 or limit > 50_000:
            raise ValueError("limit must be between 1 and 50,000")
        params: dict[str, str | int] = {
            "$select": "id",
            "$where": where,
            "$order": "id ASC",
            "$limit": limit,
        }
        if offset:
            params["$offset"] = offset
        try:
            payload = self._request_json(self.settings.crime_data_url, params)
        except (httpx.HTTPError, ValueError) as exc:
            raise ChicagoDataError(f"Crime id request failed: {exc}") from exc
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) and "id" in item for item in payload
        ):
            raise ChicagoDataError("Crime id response was not a list of id rows.")
        return [str(item["id"]) for item in payload]

    def count_crimes(self, where: str | None = None) -> int:
        """How many records the source holds for a filter. One aggregate request.

        Used by the incremental refresh to reconcile a partition against the source: a
        watermark on `updated_on` can only see rows that were inserted or modified, never
        rows the city has since removed, so the row count is the one cheap signal of drift.
        """
        params: dict[str, str | int] = {"$select": "count(*) AS n"}
        if where:
            params["$where"] = where

        try:
            payload = self._request_json(self.settings.crime_data_url, params)
        except (httpx.HTTPError, ValueError) as exc:
            raise ChicagoDataError(f"Crime count request failed: {exc}") from exc

        if (
            not isinstance(payload, list)
            or len(payload) != 1
            or not isinstance(payload[0], dict)
            or "n" not in payload[0]
        ):
            raise ChicagoDataError("Crime count response was not a single aggregate row.")
        try:
            return int(payload[0]["n"])
        except (TypeError, ValueError) as exc:
            raise ChicagoDataError(f"Crime count was not an integer: {payload[0]['n']!r}") from exc
