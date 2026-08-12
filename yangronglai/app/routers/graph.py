"""Relationship graph inspection and explicit Neo4j synchronization."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.engine.graph import graph_engine


router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/status")
async def graph_status() -> dict:
    return {
        "enabled": settings.ENABLE_GRAPH_ENGINE,
        "backend": settings.GRAPH_BACKEND,
        "version": graph_engine.version,
        "capabilities": graph_engine.capabilities(),
        "neo4j_configured": bool(settings.NEO4J_PASSWORD),
    }


@router.get("/users/{user_id}")
async def user_neighborhood(
    user_id: str,
    depth: int = Query(default=2, ge=1, le=3),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await graph_engine.neighborhood(user_id, session, depth=depth)


@router.post("/sync")
async def sync_graph(session: AsyncSession = Depends(get_db)) -> dict:
    if settings.GRAPH_BACKEND != "neo4j":
        raise HTTPException(status_code=409, detail="GRAPH_BACKEND 不是 neo4j")
    try:
        return await graph_engine.sync_to_neo4j(session)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
