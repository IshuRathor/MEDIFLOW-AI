from collections import defaultdict
from time import monotonic

from fastapi import HTTPException

from app.core.config import REDIS_URL


try:
    import redis
except ImportError:
    redis = None


if REDIS_URL and redis:
    _redis_client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
else:
    _redis_client = None

_memory_windows: dict[str, list[float]] = defaultdict(list)


def enforce_rate_limit(
    scope: str,
    identifier: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    key = f"mediflow:{scope}:{identifier}"

    if _redis_client:
        try:
            count = _redis_client.incr(key)
            if count == 1:
                _redis_client.expire(key, window_seconds)
            if count > limit:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please wait and try again.",
                )
            return
        except HTTPException:
            raise
        except Exception:
            pass

    now = monotonic()
    timestamps = [
        timestamp
        for timestamp in _memory_windows[key]
        if now - timestamp < window_seconds
    ]
    if len(timestamps) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait and try again.",
        )
    timestamps.append(now)
    _memory_windows[key] = timestamps
