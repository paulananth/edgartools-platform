"""FastAPI app for the MDM REST API.

Mounted at /api/v1/mdm. Every router requires X-API-Key.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI

from edgar_warehouse.mdm.api.auth import require_api_key
from edgar_warehouse.mdm.api.routers import (
    advisers,
    companies,
    entities,
    export,
    funds,
    graph,
    persons,
    rules,
    securities,
    stewardship,
)


def create_app() -> FastAPI:
    app = FastAPI(title="EdgarTools MDM", version="1.0.0")

    api = APIRouter(prefix="/api/v1/mdm", dependencies=[Depends(require_api_key)])
    api.include_router(entities.router)
    api.include_router(companies.router)
    api.include_router(advisers.router)
    api.include_router(persons.router)
    api.include_router(securities.router)
    api.include_router(funds.router)
    api.include_router(graph.router)
    api.include_router(stewardship.router)
    api.include_router(rules.router)
    api.include_router(export.router)
    app.include_router(api)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
