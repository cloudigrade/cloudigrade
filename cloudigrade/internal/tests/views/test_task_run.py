"""Collection of tests for running tasks from the internal API."""

from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from internal.views import task_run

_faker = faker.Faker()


class TaskRunTest(TestCase):
    """Task run view test case."""

    def setUp(self):
        """Set up shared test data."""
        self.factory = APIRequestFactory()
        celery_app_patch = patch("internal.views.celery_app")
        self.mock_celery_app = celery_app_patch.start()
        self.addCleanup(celery_app_patch.stop)

    def test_task_run(self):
        """Test happy path success for running an arbitrary task."""
        task_name = _faker.slug()
        task_kwargs = {_faker.slug(): _faker.slug(), _faker.slug(): _faker.slug()}

        mock_signature = self.mock_celery_app.signature.return_value
        mock_async_result = mock_signature.delay.return_value

        request = self.factory.post(
            "/task_run/",
            data={"task_name": task_name, "kwargs": task_kwargs},
            format="json",
        )
        response = task_run(request)

        self.mock_celery_app.signature.assert_called_with(task_name)
        mock_signature.delay.assert_called_with(**task_kwargs)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["async_result_id"], mock_async_result.id)

    def test_task_run_bad_post_params(self):
        """Test error is returned and task is not called when bad input is given."""
        task_name = _faker.slug()
        request = self.factory.post(
            "/task_run/",
            data={task_name: task_name, "unrelated_potato_argument": task_name},
            format="json",
        )
        response = task_run(request)
        self.assertEqual(response.status_code, 400)
        self.mock_celery_app.signature.assert_not_called()

    def test_task_run_bad_task_kwargs(self):
        """
        Test error is returned when task is called when bad kwargs.

        Celery's delay raises TypeError if the arguments it is given do not match the
        actual function signature of the task being called. Example:

        $ http localhost:8000/internal/tasks/ \
            task_name="api.tasks.enable_account" kwargs:='{"potato":1}'

        HTTP/1.1 400 Bad Request
        {"error":"enable_account() got an unexpected keyword argument 'potato'"}
        """
        task_name = _faker.slug()
        task_kwargs = {_faker.slug(): _faker.slug(), _faker.slug(): _faker.slug()}

        type_error_message = _faker.sentence()
        mock_signature = self.mock_celery_app.signature.return_value
        mock_signature.delay.side_effect = TypeError(type_error_message)

        request = self.factory.post(
            "/task_run/",
            data={"task_name": task_name, "kwargs": task_kwargs},
            format="json",
        )
        response = task_run(request)

        self.mock_celery_app.signature.assert_called_with(task_name)
        mock_signature.delay.assert_called_with(**task_kwargs)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], type_error_message)
