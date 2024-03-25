"""Collection of tests for ``util.celery`` module."""

from unittest.mock import patch

from django.test import TestCase

from util import celery
from util.celery import calculate_max_retries
from util.exceptions import AwsThrottlingException, NotReadyException


class UtilCeleryTest(TestCase):
    """Celery utility functions test case."""

    @patch("util.celery.shared_task")
    def test_retriable_shared_task(self, mock_shared_task):
        """Test retriable_shared_task with no args decorates correctly."""

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
            "autoretry_for": (NotReadyException, AwsThrottlingException),
            "max_retries": 35,
            "retry_backoff": True,
            "retry_jitter": True,
            "retry_backoff_max": 120,
        }
        self.assertDictEqual(kwargs, expected_kwargs)

    @patch("util.celery.shared_task")
    def test_retriable_shared_task_with_args(self, mock_shared_task):
        """Test retriable_shared_task with args decorates correctly."""

        def my_func(a, b):
            return a + b

        # Turn the mocked shared_task into a dumb pass-through.
        mock_shared_task.return_value = my_func

        # This acts like:
        # @retriable_shared_task(max_retries=10)
        # def my_func():
        #    ...
        decorated_func = celery.retriable_shared_task(my_func, max_retries=10)
        result = decorated_func(1, 2)
        self.assertEqual(result, 3)

        args, kwargs = mock_shared_task.call_args_list[0]
        self.assertEqual(my_func, args[0])
        expected_kwargs = {
            "autoretry_for": (NotReadyException, AwsThrottlingException),
            "max_retries": 10,
            "retry_backoff": True,
            "retry_jitter": True,
            "retry_backoff_max": 120,
        }
        self.assertDictEqual(kwargs, expected_kwargs)

    @patch("util.celery.shared_task")
    def test_retriable_shared_task_recalc_max_retries(self, mock_shared_task):
        """
        Test retriable_shared_task recalculates max_retries.

        This differs from the default settings by forcing max_retries to
        change. Given retry_backoff_max=10 and retry_max_elapsed_backoff=60,
        the new max_retries passed into the shared_task should be 8. See also
        test_calculate_max_retries_low_retry_time for more info.
        """

        def my_func(a, b):
            return a + b

        # Turn the mocked shared_task into a dumb pass-through.
        mock_shared_task.return_value = my_func

        decorated_func = celery.retriable_shared_task(
            my_func,
            retry_backoff_max=10,
            retry_max_elapsed_backoff=60,
        )
        result = decorated_func(1, 2)
        self.assertEqual(result, 3)

        args, kwargs = mock_shared_task.call_args_list[0]
        self.assertEqual(my_func, args[0])
        expected_kwargs = {
            "autoretry_for": (NotReadyException, AwsThrottlingException),
            "max_retries": 8,
            "retry_backoff": True,
            "retry_jitter": True,
            "retry_backoff_max": 10,
        }
        self.assertDictEqual(kwargs, expected_kwargs)

    def test_calculate_max_retries(self):
        """
        Test retry count calculation.

        calculate_max_retries(60, 60) should effectively have retries like:
        - retry 1 is 1 sec, after which elapsed time is 1 sec
        - retry 2 is 2 sec, after which elapsed time is 3 sec
        - retry 3 is 4 sec, after which elapsed time is 7 sec
        - retry 4 is 8 sec, after which elapsed time is 15 sec
        - retry 5 is 16 sec, after which elapsed time is 31 sec
        - retry 6 is 32 sec, after which elapsed time is 63 sec
        but because the 6th retry exceeds the elapsed limit, the expected max
        number of retries should be 5.
        """
        max_retries = calculate_max_retries(60, 60)
        self.assertEqual(5, max_retries)

    def test_calculate_max_retries_low_retry_time(self):
        """
        Test retry count calculation with a low retry time.

        calculate_max_retries(60, 10) should effectively have retries like:
        - retry 1 is 1 sec, after which elapsed time is 1 sec
        - retry 2 is 2 sec, after which elapsed time is 3 sec
        - retry 3 is 4 sec, after which elapsed time is 7 sec
        - retry 4 is 8 sec, after which elapsed time is 15 sec
        - retry 5 is capped at 10 sec, after which elapsed time is 25 sec
        - retry 6 is capped at 10 sec, after which elapsed time is 35 sec
        - retry 7 is capped at 10 sec, after which elapsed time is 45 sec
        - retry 8 is capped at 10 sec, after which elapsed time is 55 sec
        - retry 9 is capped at 10 sec, after which elapsed time is 65 sec
        but because the 9th retry exceeds the elapsed limit, the expected max
        number of retries should be 8.
        """
        max_retries = calculate_max_retries(60, 10)
        self.assertEqual(8, max_retries)
