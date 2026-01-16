import time
from collections import deque
from .config import settings

class RateLimiter:
    def __init__(self, requests: int = None, window: int = None):
        self.requests = requests or settings.RATE_LIMIT_REQUESTS
        self.window = window or settings.RATE_LIMIT_WINDOW
        self.history = deque()

    def is_allowed(self) -> bool:
        """Check if request is allowed under rate limit."""
        now = time.time()
        
        # Remove timestamps outside current window
        while self.history and self.history[0] <= now - self.window:
            self.history.popleft()
            
        if len(self.history) < self.requests:
            self.history.append(now)
            return True
            
        return False
