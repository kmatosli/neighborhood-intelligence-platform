"""Read-only public API over the Silver layer.

There is no refresh endpoint and no write path — ingestion is not triggerable over HTTP
(docs/architecture/SECURITY.md). The one writer that runs inside this process is the
scheduled refresh (`bw_observatory.ops.scheduler`), which is a clock, not an endpoint: it
starts only when `BW_REFRESH_SCHEDULE` is set, and it runs the same CLI a person would.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bw_observatory.api.routes import freshness, geographies, incidents, overview, pulse, years
from bw_observatory.config import Settings
from bw_observatory.ops.scheduler import RefreshScheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = RefreshScheduler(Settings())
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(
    title="Ward 20 Neighborhood Intelligence API",
    version="0.2.0",
    description="Read-only civic data for Chicago's Ward 20 and the areas within it.",
    lifespan=lifespan,
)

# The Vite dev server proxies /api, so this is only needed when the frontend is served
# directly from its own origin during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(overview.router)
app.include_router(pulse.router)
app.include_router(years.router)
app.include_router(geographies.router)
app.include_router(incidents.router)
app.include_router(freshness.router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
