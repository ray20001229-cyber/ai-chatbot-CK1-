import json
import logging
import time
import uuid
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)
_client: Redis | None = None
_disabled_until = 0.0


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


def redis_ping() -> bool:
    if not _can_attempt():
        return False
    try:
        return bool(get_redis().ping())
    except RedisError:
        _mark_unavailable()
        return False


def cache_get(key: str) -> dict[str, Any] | None:
    if not _can_attempt():
        return None
    try:
        value = get_redis().get(key)
        return json.loads(value) if value else None
    except (RedisError, json.JSONDecodeError):
        _mark_unavailable()
        return None


def cache_set(key: str, value: dict[str, Any], ttl: int = 30) -> None:
    if not _can_attempt():
        return
    try:
        get_redis().setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except RedisError:
        _mark_unavailable()
        logger.warning("Redis cache write failed")


def cache_delete(key: str) -> None:
    if not _can_attempt():
        return
    try:
        get_redis().delete(key)
    except RedisError:
        _mark_unavailable()
        pass


def acquire_lock(key: str, ttl: int) -> str | None:
    if not _can_attempt():
        return "redis-unavailable"
    token = str(uuid.uuid4())
    try:
        acquired = get_redis().set(key, token, nx=True, ex=ttl)
        return token if acquired else None
    except RedisError:
        _mark_unavailable()
        # Safe degradation for local single-process mode.
        return "redis-unavailable"


def release_lock(key: str, token: str) -> None:
    if token == "redis-unavailable":
        return
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
      return redis.call('del', KEYS[1])
    end
    return 0
    """
    try:
        get_redis().eval(script, 1, key, token)
    except RedisError:
        _mark_unavailable()
        pass


def _can_attempt() -> bool:
    return time.monotonic() >= _disabled_until


def _mark_unavailable() -> None:
    global _disabled_until
    _disabled_until = time.monotonic() + 5
