"""Collection of tests for the 'checkceleryconfigs' management command."""

from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch

import faker
from django.core.management import call_command
from django.test import TestCase
from django.test import override_settings

_faker = faker.Faker()
command_path = "util.management.commands.checkceleryconfigs"


@contextmanager
def patch_yaml(clowdapp_yaml_queue_names):
    """Patch the getting of CELERY_QUEUE_NAMES from clowdapp.yaml."""
    with patch(
        "{}.Command.get_clowdapp_yaml_celery_queue_names".format(command_path)
    ) as mock_get_clowdapp:
        mock_get_clowdapp.return_value = clowdapp_yaml_queue_names
        yield


@contextmanager
def patch_exit():
    """Patch the sys.exit call."""
    with patch("{}.sys.exit".format(command_path)) as mock_exit:
        yield mock_exit


@contextmanager
def patch_routes(celery_task_routes):
    """Override the CELERY_TASK_ROUTES setting."""
    with override_settings(CELERY_TASK_ROUTES=celery_task_routes):
        yield


@contextmanager
def patch_autodiscovered(task_names):
    """Patch the autodiscovered tasks in the Celery app."""
    with patch("{}.celery_app".format(command_path)) as mock_celery_app:
        mock_celery_app.tasks = {name: None for name in task_names}
        yield


@contextmanager
def patch_everything(
    clowdapp_yaml_queue_names, celery_task_routes, autodiscovered_tasks
):
    """Patch **all the things** for one convenient call to test."""
    with patch_exit() as mock_exit, patch_yaml(clowdapp_yaml_queue_names), patch_routes(
        celery_task_routes
    ), patch_autodiscovered(autodiscovered_tasks):
        yield mock_exit


class CheckCeleryConfigsTest(TestCase):
    """Management command 'checkceleryconfigs' test case."""

    def setUp(self):
        """Set up test data."""
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.task_name = f"{_faker.slug()}.{_faker.slug()}"
        self.task_queue = _faker.slug()
        self.clowdapp_yaml_queue_names = {self.task_queue}
        self.celery_task_routes = {self.task_name: {"queue": self.task_queue}}
        self.autodiscovered_tasks = [self.task_name]

    def assertCommandSuccess(self, mock_exit):
        """Assert that the commmand exited cleanly with no stderr."""
        self.stderr.seek(0)
        self.assertEqual("", self.stderr.read())
        mock_exit.assert_not_called()

    def assertCommandFailure(self, expected_stderr, mock_exit):
        """Assert that the commmand exited with the given stderr."""
        self.stderr.seek(0)
        self.assertIn(expected_stderr, self.stderr.read())
        mock_exit.assert_called_once_with(1)

    def test_configs_all_good(self):
        """Test happy path when configs are all aligned."""
        with patch_everything(
            self.clowdapp_yaml_queue_names,
            self.celery_task_routes,
            self.autodiscovered_tasks,
        ) as mock_exit:
            call_command("checkceleryconfigs", stdout=self.stdout, stderr=self.stderr)
            self.assertCommandSuccess(mock_exit)

    def test_queue_not_in_clowdapp_yaml_bad(self):
        """Test failure when queue is not in clowdapp.yaml."""
        self.clowdapp_yaml_queue_names = set()  # missing!
        expected_stderr = (
            f"{self.task_queue} is defined in CELERY_TASK_ROUTES "
            "but not in clowdapp.yml's CELERY_QUEUE_NAMES parameter."
        )

        with patch_everything(
            self.clowdapp_yaml_queue_names,
            self.celery_task_routes,
            self.autodiscovered_tasks,
        ) as mock_exit:
            call_command("checkceleryconfigs", stdout=self.stdout, stderr=self.stderr)
            self.assertCommandFailure(expected_stderr, mock_exit)

    def test_route_missing_bad(self):
        """Test failure when task is not in routes."""
        self.celery_task_routes = {}  # missing!
        expected_stderr = (
            f"{self.task_name} is discovered but is not defined in CELERY_TASK_ROUTES."
        )

        with patch_everything(
            self.clowdapp_yaml_queue_names,
            self.celery_task_routes,
            self.autodiscovered_tasks,
        ) as mock_exit:
            call_command("checkceleryconfigs", stdout=self.stdout, stderr=self.stderr)
            self.assertCommandFailure(expected_stderr, mock_exit)

    def test_route_has_no_queue_bad(self):
        """Test failure when task route has no queue."""
        self.celery_task_routes[self.task_name] = {}  # missing queue!
        expected_stderr = (
            f"{self.task_name} is defined in CELERY_TASK_ROUTES "
            "but does not configure a queue."
        )

        with patch_everything(
            self.clowdapp_yaml_queue_names,
            self.celery_task_routes,
            self.autodiscovered_tasks,
        ) as mock_exit:
            call_command("checkceleryconfigs", stdout=self.stdout, stderr=self.stderr)
            self.assertCommandFailure(expected_stderr, mock_exit)

    def test_task_not_autodiscovered_bad(self):
        """Test failure when task is not autodiscovered."""
        self.autodiscovered_tasks = []  # missing!
        expected_stderr = (
            f"{self.task_name} is defined in CELERY_TASK_ROUTES "
            "but has not been autodiscovered."
        )

        with patch_everything(
            self.clowdapp_yaml_queue_names,
            self.celery_task_routes,
            self.autodiscovered_tasks,
        ) as mock_exit:
            call_command("checkceleryconfigs", stdout=self.stdout, stderr=self.stderr)
            self.assertCommandFailure(expected_stderr, mock_exit)
