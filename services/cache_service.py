import json
import redis
from config import config


class CacheService:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=2,
            )
        return self._client

    def get(self, key: str):
        try:
            value = self.client.get(key)
            return json.loads(value) if value else None
        except (redis.RedisError, Exception):
            return None

    def set(self, key: str, value, ttl: int = None):
        try:
            self.client.setex(key, ttl or config.REDIS_TTL, json.dumps(value))
        except (redis.RedisError, Exception):
            pass  # 캐시 실패해도 서비스는 계속

    def delete(self, key: str):
        try:
            self.client.delete(key)
        except (redis.RedisError, Exception):
            pass

    def is_available(self) -> bool:
        try:
            self.client.ping()
            return True
        except Exception:
            return False


cache = CacheService()
