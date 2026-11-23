"""Suite-wide test isolation."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _not_production(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tests run as a non-production process unless a test says otherwise, even from a shell
    # that has `RENDER` or `BW_PRODUCTION` set (Settings.production refuses development
    # releases). monkeypatch restores the environment after each test.
    monkeypatch.delenv("BW_PRODUCTION", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
