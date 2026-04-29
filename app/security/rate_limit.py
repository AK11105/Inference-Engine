"""
Sliding-window rate limiter with two backends:

- RedisRateLimiter  — production; uses an atomic Lua script.
- RateLimiter       — in-process fallback (same API, same tests pass).

The middleware selects the backend at startup based on REDIS_URL.
"""
import time
from collections import defaultdict, deque


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


# Atomic Lua script: remove stale entries, check count, conditionally add — all in one round-trip.
_LUA = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local rate   = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('zremrangebyscore', key, '-inf', now - window)
local count = redis.call('zcard', key)
if count >= rate then return 0 end
redis.call('zadd', key, now, member)
redis.call('expire', key, window + 1)
return 1
"""


class RedisRateLimiter:
    """
    Redis-backed sliding-window rate limiter.

    Uses an atomic Lua script so the check-then-add is race-free across
    concurrent processes.
    """

    def __init__(self, rate: int, per_seconds: int, redis_client, name: str = "rl"):
        self.rate = rate
        self.per_seconds = per_seconds
        self._redis = redis_client
        self._name = name

    def allow(self, key: str) -> bool:
        import uuid as _uuid
        now = time.time()
        zkey = f"ratelimit:{self._name}:{key}"
        member = f"{now}:{_uuid.uuid4().hex}"
        result = self._redis.eval(_LUA, 1, zkey, now, self.per_seconds, self.rate, member)
        return bool(result)


def make_rate_limiter(
    rate: int,
    per_seconds: int,
    name: str = "default",
    redis_client=None,
) -> "RateLimiter | RedisRateLimiter":
    if redis_client is not None:
        return RedisRateLimiter(rate=rate, per_seconds=per_seconds, redis_client=redis_client, name=name)
    return RateLimiter(rate=rate, per_seconds=per_seconds)
