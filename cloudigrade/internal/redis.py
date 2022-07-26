"""Internal Redis helper functions."""
from django_redis import get_redis_connection


def execute_command(command, args):
    """Execute a Redis command."""
    with get_redis_connection("default") as connection:
        func = getattr(connection, command)
        results = func(*args)
    return results
