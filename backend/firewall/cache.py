from abc import ABC, abstractmethod
from typing import Optional
from .models import FirewallDecision

class BaseCache(ABC):
    """Abstract interface for caching firewall decisions."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[FirewallDecision]:
        pass
        
    @abstractmethod
    async def set(self, key: str, decision: FirewallDecision, ttl_seconds: int = 3600):
        pass

class InMemoryCache(BaseCache):
    """Simple in-memory dictionary cache implementation."""
    
    def __init__(self):
        self._store = {}
        
    async def get(self, key: str) -> Optional[FirewallDecision]:
        return self._store.get(key)
        
    async def set(self, key: str, decision: FirewallDecision, ttl_seconds: int = 3600):
        # In a real implementation with TTL, we'd store timestamps and expire keys
        self._store[key] = decision
