"""Utility module to aid Celery functionality."""
from celery import shared_task

from util.exceptions import NotReadyException


def retriable_shared_task(original_function=None,
                          autoretry_for=(NotReadyException,),
                          max_retries=3,
                          retry_backoff=True,
                          retry_jitter=True,
                          retry_backoff_max=60,
                          **kwargs):
    """
    Decorate function to be a shared task with our standard retry settings.

    This decorator can be used with or without arguments. For example:

        @retriable_shared_task
        def my_great_task(input1, input2):
            ...

        @retriable_shared_task(max_retries=5, retry_backoff_max=100)
        def my_great_task(input1, input2):
            ...

    Args:
        original_function: The function to decorate.

    Returns:
        function: The decorated function as a shared task.

    """
    def _retriable_shared_task(function):
        return shared_task(
            function,
            autoretry_for=autoretry_for,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            retry_jitter=retry_jitter,
            retry_backoff_max=retry_backoff_max,
            **kwargs
        )

    if original_function:
        return _retriable_shared_task(original_function)
    return _retriable_shared_task
