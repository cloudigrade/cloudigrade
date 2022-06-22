"""Collection of helper methods for the Internal caching."""
import datetime

from django.core.cache import cache, caches
from django_redis.cache import RedisCache


def get_cache_key_timeout(key):
    """Return the timeout for the key specified."""
    # Development/Production environments use Redis
    if isinstance(caches["default"], RedisCache):
        return cache.ttl(key=key)

    # Test environments use LocMemCache
    expiration_unix_timestamp = cache._expire_info.get(cache.make_key(key))
    if expiration_unix_timestamp is None:
        return 0
    expiration_date_time = datetime.datetime.fromtimestamp(expiration_unix_timestamp)

    now = datetime.datetime.now()
    if expiration_date_time < now:
        return 0
    delta = expiration_date_time - now
    return delta.seconds
