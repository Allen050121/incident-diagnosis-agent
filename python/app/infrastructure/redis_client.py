"""Redis connection manager"""

import redis
from app.config import settings


_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Get or create Redis client (singleton)"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
    return _redis_client


def reset_redis():
    """Reset Redis client (for testing)"""
    global _redis_client
    _redis_client = None
