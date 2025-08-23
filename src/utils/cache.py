import time
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod


class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        pass


class InMemoryCache(CacheBackend):
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if entry['expires'] > time.time():
                return entry['value']
            else:
                del self._cache[key]
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        self._cache[key] = {
            'value': value,
            'expires': time.time() + ttl
        }
    
    async def delete(self, key: str) -> None:
        self._cache.pop(key, None)
    
    async def clear(self) -> None:
        self._cache.clear()


class Cache:
    def __init__(self, backend: CacheBackend):
        self.backend = backend
    
    async def get(self, key: str) -> Optional[Any]:
        return await self.backend.get(key)
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        await self.backend.set(key, value, ttl)
    
    async def delete(self, key: str) -> None:
        await self.backend.delete(key)
    
    async def clear(self) -> None:
        await self.backend.clear()


# Initialize cache with in-memory backend for Vercel serverless
cache = Cache(InMemoryCache())