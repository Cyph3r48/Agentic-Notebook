"""
System endpoints for basic API status.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/system")


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}
