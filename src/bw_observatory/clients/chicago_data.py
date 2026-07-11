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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        reraise=True,
    )
    def get_metadata(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    self.settings.crime_metadata_url,
                    headers=self._headers(),
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ChicagoDataError(f"Metadata request failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise ChicagoDataError("Metadata response was not an object.")
        return payload

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        reraise=True,
    )
    def get_crimes(
        self,
        *,
        limit: int = 10,
        where: str | None = None,
        order: str = "date DESC, id DESC",
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 50_000:
            raise ValueError("limit must be between 1 and 50,000")

        params: dict[str, str | int] = {
            "$limit": limit,
            "$order": order,
        }
        if where:
            params["$where"] = where

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    self.settings.crime_data_url,
                    headers=self._headers(),
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ChicagoDataError(f"Crime data request failed: {exc}") from exc

        if not isinstance(payload, list):
            raise ChicagoDataError("Crime response was not a list.")
        if not all(isinstance(item, dict) for item in payload):
            raise ChicagoDataError("Crime response contained an invalid record.")
        return payload
