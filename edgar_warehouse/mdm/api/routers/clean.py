"""Version-2 shared identities, role provenance and pinned generation reads."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from edgar_warehouse.mdm.clean.cli import engine_from_env
from edgar_warehouse.mdm.clean.consumer import ContractReader

router = APIRouter(tags=["clean-mdm"])


def get_reader():
    engine = engine_from_env("MDM_DATABASE_URL")
    try:
        yield ContractReader(engine)
    finally:
        engine.dispose()


@router.get("/entities/{entity_id}")
def entity(
    entity_id: UUID,
    reader: Annotated[ContractReader, Depends(get_reader)],
    generation: int | None = Query(default=None, ge=1),
):
    try:
        return reader.entity(str(entity_id), generation=generation)
    except KeyError as exc:
        raise HTTPException(404, "Identity or generation not found") from exc


@router.get("/objects/{object_type}")
def objects(
    object_type: Literal["entity", "relationship", "review"],
    reader: Annotated[ContractReader, Depends(get_reader)],
    generation: int | None = Query(default=None, ge=1),
    after: str = "",
    limit: int = Query(default=100, ge=1, le=1000),
):
    try:
        return reader.snapshot_page(
            object_type, generation=generation, after=after, limit=limit
        )
    except KeyError as exc:
        raise HTTPException(404, "Generation not found") from exc
