"""Read-only public API over the Silver layer.

There is no refresh endpoint and no write path — ingestion is not triggerable over HTTP
(docs/architecture/SECURITY.md).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bw_observatory.api.routes import incidents, overview, pulse, years

app = FastAPI(
    title="Bronzeville–Woodlawn Observatory API",
    version="0.1.0",
    description="Read-only civic data for Bronzeville and Woodlawn.",
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
app.include_router(incidents.router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
