"""Model registry status and explicit retraining endpoint."""

import asyncio

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.engine.model_manager import model_manager
from app.engine.model_training import train_all


router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/status")
async def model_status() -> dict:
    return {
        "enabled": settings.ENABLE_MODEL_ENGINE,
        "ready": all(item["ready"] for item in model_manager.status().values()),
        "models": model_manager.status(),
    }


@router.post("/train")
async def train_models(sample_size: int = 3000) -> dict:
    if not 500 <= sample_size <= 100000:
        raise HTTPException(status_code=422, detail="sample_size must be between 500 and 100000")
    registry = await asyncio.to_thread(train_all, settings.MODEL_DIR, sample_size)
    model_manager.ensure_ready()
    return {
        "trained": list(registry["models"]),
        "metrics": {name: item["metrics"] for name, item in registry["models"].items()},
    }
