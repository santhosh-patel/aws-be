"""
Response Cache — In-memory TTL cache to avoid repeated AWS API calls.

Uses cachetools.TTLCache for thread-safe, time-limited caching.
Key = hash of (tool_name, sorted_arguments). Default TTL = 300s.
"""
import hashlib
import json
import threading
import time
import logging
from typing import Any, Dict, Optional, Tuple
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Default TTL by data category (seconds)
CACHE_TTL = {
    "cost": 300,        # 5 min — cost data changes slowly
    "resource": 120,    # 2 min — resources can change faster
    "default": 180,     # 3 min — everything else
}


class ResponseCache:
    """
    Thread-safe in-memory TTL cache for AWS API responses.
    
    Eliminates redundant boto3 calls when a user asks the same question
    within the TTL window (e.g., refreshes, follow-ups, currency conversion).
    """

    def __init__(self, maxsize: int = 256, default_ttl: int = 300):
        self._cache = TTLCache(maxsize=maxsize, ttl=default_ttl)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(tool_name: str, arguments: Dict[str, Any]) -> str:
        """Deterministic cache key from tool name + arguments."""
        args_str = json.dumps(arguments, sort_keys=True, default=str)
        raw = f"{tool_name}:{args_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return cached result or None."""
        key = self._make_key(tool_name, arguments)
        with self._lock:
            result = self._cache.get(key)
            if result is not None:
                self._hits += 1
                logger.debug(f"[Cache HIT] {tool_name} (key={key})")
                return result
            self._misses += 1
            return None

    def set(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Store a result in the cache."""
        key = self._make_key(tool_name, arguments)
        with self._lock:
            self._cache[key] = result
        logger.debug(f"[Cache SET] {tool_name} (key={key})")

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._cache.clear()
        logger.info("[Cache] Invalidated all entries")

    def stats(self) -> Dict[str, Any]:
        """Return cache performance statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0,
                "size": len(self._cache),
                "maxsize": self._cache.maxsize,
            }

    def classify_tool(self, tool_name: str) -> str:
        """Classify a tool into a cache category."""
        name = tool_name.lower()
        if "cost" in name or "spend" in name or "billing" in name:
            return "cost"
        if "resource" in name or "ec2" in name or "instance" in name:
            return "resource"
        return "default"
