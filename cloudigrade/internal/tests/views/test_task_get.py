"""Collection of tests for getting task results from the internal API."""
from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from internal.views import task_get

_faker = faker.Faker()


class TaskGetTest(TestCase):
    """Task get view test case."""

    def setUp(self):
        """Set up shared test data."""
        self.factory = APIRequestFactory()
        AsyncResult_patch = patch("internal.views.AsyncResult")
        self.mock_AsyncResult = AsyncResult_patch.start()
        self.addCleanup(AsyncResult_patch.stop)

    def test_task_get(self):
        """Test happy path success getting a completed (ready) task."""
        async_result_id = str(_faker.uuid4())
        self.mock_AsyncResult.return_value.ready.return_value = True
        expected_returned_value = self.mock_AsyncResult.return_value.get.return_value

        request = self.factory.get(f"/task_get/{async_result_id}/")
        response = task_get(request, async_result_id)

        self.mock_AsyncResult.assert_called_once_with(async_result_id)
        self.mock_AsyncResult.return_value.get.assert_called_once_with()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["async_result_id"], async_result_id)
        self.assertTrue(response.data["ready"])
        self.assertEqual(response.data["result"], expected_returned_value)

    def test_task_get_not_ready(self):
        """Test when task has not completed (is not ready)."""
        async_result_id = str(_faker.uuid4())
        self.mock_AsyncResult.return_value.ready.return_value = False

        request = self.factory.get(f"/task_get/{async_result_id}/")
        response = task_get(request, async_result_id)

        self.mock_AsyncResult.assert_called_once_with(async_result_id)
        self.mock_AsyncResult.return_value.get.assert_not_called()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["async_result_id"], async_result_id)
        self.assertFalse(response.data["ready"])
        self.assertIsNone(response.data["result"])

    def test_task_get_execution_raised_exception(self):
        """
        Test when the worker raised an execution when executing the task.

        Typically, what happens is the async task reports "ready" and the "get" call
        raises the exception that occurred when the worker executed the task. Example:

        $ http localhost:8000/internal/tasks/ \
            task_name="api.tasks.enable_account" kwargs:='{"cloud_account_id":"potato"}'

        HTTP/1.1 201 Created
        {
            "async_result_id": "9fb41f3d-e4ed-4b55-844a-6d7b62732d80"
        }

        $ http localhost:8000/internal/tasks/9fb41f3d-e4ed-4b55-844a-6d7b62732d80/

        HTTP/1.1 200 OK
        {
            "async_result_id": "9fb41f3d-e4ed-4b55-844a-6d7b62732d80",
            "error_args": [
                "Field 'id' expected a number but got 'potato'."
            ],
            "error_class": "builtins.ValueError"
        }
        """
        async_result_id = str(_faker.uuid4())
        self.mock_AsyncResult.return_value.ready.return_value = True
        error_message = "Field 'id' expected a number but got 'potato'."
        self.mock_AsyncResult.return_value.get.side_effect = ValueError(error_message)

        request = self.factory.get(f"/task_get/{async_result_id}/")
        response = task_get(request, async_result_id)

        self.mock_AsyncResult.assert_called_once_with(async_result_id)
        self.mock_AsyncResult.return_value.get.assert_called_once_with()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["async_result_id"], async_result_id)
        self.assertEqual(response.data["error_args"], [error_message])
        self.assertEqual(response.data["error_class"], "builtins.ValueError")
