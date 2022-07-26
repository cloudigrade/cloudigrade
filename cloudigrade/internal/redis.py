"""Internal Redis helper functions."""
from django.core.cache import caches
from django_redis import get_redis_connection
from django_redis.cache import RedisCache


def execute_command(command, args):
    """Execute a Redis command."""
    with get_redis_connection("default") as connection:
        func = getattr(connection, command)
        results = func(*args)
    return results


def redis_is_the_default_cache():
    """Check if Redis is the default cache."""
    return isinstance(caches["default"], RedisCache)
