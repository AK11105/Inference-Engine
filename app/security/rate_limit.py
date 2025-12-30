import time 
from collections import defaultdict, deque

class RateLimiter:
    def __init__(self, rate: int, per_seconds: int):
        self.rate = rate
        self.per_seconds = per_seconds
        self._events = defaultdict(deque)
    
    def allow(self, key: str) -> bool:
        now = time.time()
        window = self._events[key]
        while window and now - window[0] > self.per_seconds:
            window.popleft()
        if len(window) >= self.rate:
            return False
        window.append(now)
        return True
    
    