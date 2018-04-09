"""Collection of tests for ``util.celery`` module."""
from unittest.mock import patch

from django.test import TestCase

from util import celery
from util.exceptions import NotReadyException


class UtilCeleryTest(TestCase):
    """Celery utility functions test case."""

    def test_retriable_shared_task(self):
        """Test retriable_shared_task with no args decorates correctly."""
        with patch.object(celery, 'shared_task') as mock_shared_task:

            def my_func(a, b):
                return a + b

            # Turn the mocked shared_task into a dumb pass-through.
            mock_shared_task.return_value = my_func

            # This acts like:
            # @retriable_shared_task
            # def my_func():
            #    ...
            decorated_func = celery.retriable_shared_task()(my_func)
            result = decorated_func(1, 2)
            self.assertEqual(result, 3)

            args, kwargs = mock_shared_task.call_args_list[0]
            self.assertEqual(my_func, args[0])
            expected_kwargs = {
                'autoretry_for': (NotReadyException,),
                'max_retries': 3,
                'retry_backoff': True,
                'retry_jitter': True,
                'retry_backoff_max': 60,
            }
            self.assertDictEqual(kwargs, expected_kwargs)

    def test_retriable_shared_task_with_args(self):
        """Test retriable_shared_task with args decorates correctly."""
        with patch.object(celery, 'shared_task') as mock_shared_task:

            def my_func(a, b):
                return a + b

            # Turn the mocked shared_task into a dumb pass-through.
            mock_shared_task.return_value = my_func

            # This acts like:
            # @retriable_shared_task(max_retries=10)
            # def my_func():
            #    ...
            decorated_func = celery.retriable_shared_task(
                my_func, max_retries=10
            )
            result = decorated_func(1, 2)
            self.assertEqual(result, 3)

            args, kwargs = mock_shared_task.call_args_list[0]
            self.assertEqual(my_func, args[0])
            expected_kwargs = {
                'autoretry_for': (NotReadyException,),
                'max_retries': 10,
                'retry_backoff': True,
                'retry_jitter': True,
                'retry_backoff_max': 60,
            }
            self.assertDictEqual(kwargs, expected_kwargs)
