import os
import time
from functools import wraps

_client = None

def redis_client():
    global _client
    url=os.environ.get("REDIS_URL","").strip()
    if not url: return None
    if _client is not None: return _client
    try:
        import redis
        _client=redis.Redis.from_url(url,decode_responses=True,socket_connect_timeout=2,socket_timeout=2,retry_on_timeout=True)
        _client.ping()
        return _client
    except Exception:
        _client=None
        return None

def cache_get(key):
    client=redis_client()
    if not client: return None
    try: return client.get(key)
    except Exception: return None

def cache_set(key,value,ttl=300):
    client=redis_client()
    if not client: return False
    try: client.setex(key,int(ttl),value); return True
    except Exception: return False

def cache_delete(key):
    client=redis_client()
    if not client: return False
    try: client.delete(key); return True
    except Exception: return False
