"""
Redis client utilities.
"""

from typing import Optional

from redis.asyncio import Redis

from app.core.config import settings


redis_client: Optional[Redis] = None


async def init_redis() -> None:
    global redis_client
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis_client.ping()


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return redis_client


async def is_redis_healthy() -> bool:
    try:
        client = get_redis()
        pong = await client.ping()
        return bool(pong)
    except Exception:
        return False
