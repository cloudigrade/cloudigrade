"""Utility module to aid Celery functionality."""

from celery import shared_task
from celery.utils.time import get_exponential_backoff_interval

from util.exceptions import AwsThrottlingException, NotReadyException


def retriable_shared_task(
    original_function=None,
    retry_max_elapsed_backoff=None,
    autoretry_for=(NotReadyException, AwsThrottlingException),
    max_retries=35,
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=120,
    **kwargs
):
    """
    Decorate function to be a shared task with our standard retry settings.

    The default settings of max_retries=35 and retry_backoff_max=120 allow for
    a total maximum elapsed backoff time of **one hour** of retries, with a
    maximum backoff per individual retry of two minutes. If we want to change
    these defaults to target a different maximum backoff for individual retries
    or total elapsed, please use calculate_max_retries to find the new values.

    This decorator can be used with or without arguments. For example:

        @retriable_shared_task
        def my_great_task(input1, input2):
            ...

        @retriable_shared_task(max_retries=5, retry_backoff_max=100)
        def my_great_task(input1, input2):
            ...

    Args:
        original_function: The function to decorate.
        retry_max_elapsed_backoff (int): Max elapsed time in seconds to allow
            across all retries. If specified, max_retries input is ignored and
            recalculated to accommodate this value.

    Returns:
        function: The decorated function as a shared task.

    """
    if retry_max_elapsed_backoff is not None:
        max_retries = calculate_max_retries(
            retry_max_elapsed_backoff, retry_backoff_max
        )

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


def calculate_max_retries(retry_max_elapsed_backoff, retry_backoff_max):
    """
    Calculate retry count to allow before reaching the max elapsed time.

    Args:
        retry_max_elapsed_backoff (int): maximum time in seconds to allow for
            waiting cumulatively across all retries
        retry_backoff_max (int): maximum time in seconds to allow for a retry

    Returns:
        int: number of allowed retries

    """
    max_retries = 0
    elapsed_time = 0
    while elapsed_time < retry_max_elapsed_backoff:
        retry_factor = get_exponential_backoff_interval(
            factor=1, retries=max_retries, maximum=retry_backoff_max
        )
        elapsed_time += retry_factor
        if elapsed_time < retry_max_elapsed_backoff:
            max_retries += 1
    return max_retries
