"""
Sliding-window rate limiter with two backends:

- RedisRateLimiter  — production; uses Redis ZADD/ZREMRANGEBYSCORE.
- RateLimiter       — in-process fallback (same API, same tests pass).

The middleware selects the backend at startup based on REDIS_URL.
"""
import os
import time
from collections import defaultdict, deque
from typing import Optional


class RateLimiter:
    """In-process sliding-window rate limiter (single-process only)."""

    def __init__(self, rate: int, per_seconds: int):
        self.rate = rate
        self.per_seconds = per_seconds
        self._events: defaultdict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        window = self._events[key]
        while window and now - window[0] > self.per_seconds:
            window.popleft()
        if len(window) >= self.rate:
            return False
        window.append(now)
        return True


class RedisRateLimiter:
    """
    Redis-backed sliding-window rate limiter.

    Uses a sorted set per (limiter_name, key) where the score is the
    Unix timestamp of each request.  Thread-safe and process-safe.
    """

    def __init__(
        self,
        rate: int,
        per_seconds: int,
        redis_client,
        name: str = "rl",
    ):
        self.rate = rate
        self.per_seconds = per_seconds
        self._redis = redis_client
        self._name = name

    def allow(self, key: str) -> bool:
        import uuid as _uuid
        now = time.time()
        zkey = f"ratelimit:{self._name}:{key}"
        window_start = now - self.per_seconds
        member = f"{now}:{_uuid.uuid4().hex}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(zkey, "-inf", window_start)
        pipe.zcard(zkey)
        pipe.zadd(zkey, {member: now})
        pipe.expire(zkey, self.per_seconds + 1)
        results = pipe.execute()

        count_before_add = results[1]
        if count_before_add >= self.rate:
            self._redis.zrem(zkey, member)
            return False
        return True


def make_rate_limiter(
    rate: int,
    per_seconds: int,
    name: str = "default",
    redis_client=None,
) -> RateLimiter | RedisRateLimiter:
    """
    Factory: returns RedisRateLimiter when a client is provided,
    otherwise falls back to the in-process RateLimiter.
    """
    if redis_client is not None:
        return RedisRateLimiter(
            rate=rate,
            per_seconds=per_seconds,
            redis_client=redis_client,
            name=name,
        )
    return RateLimiter(rate=rate, per_seconds=per_seconds)
