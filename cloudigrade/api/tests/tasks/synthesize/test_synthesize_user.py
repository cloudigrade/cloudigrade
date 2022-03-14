"""Collection of tests for api.tasks.synthesize.synthesize_user."""
from contextlib import contextmanager

from django.db.models.signals import post_save
from django.test import TestCase

from api import AWS_PROVIDER_STRING, models
from api.tasks import synthesize
from util.tests import helper as util_helper


@contextmanager
def mock_post_save_signal_handler():
    """Mock the post_save signal handler for SyntheticDataRequest."""
    with util_helper.mock_signal_handler(
        post_save,
        models.synthetic_data_request_post_save_callback,
        models.SyntheticDataRequest,
    ):
        yield


def create_synthetic_data_request_without_post_save(cloud_type):
    """
    Create a SyntheticDataRequest with only some relations populated.

    This function mocks the post_save signal handler so we can locally create the
    related objects we want for the test case. This is also convenient for tests
    that use TestCase; only TransactionTestCase triggers the on_commit call inside the
    post-save signal handler that calls the async tasks.
    """
    with mock_post_save_signal_handler():
        request = models.SyntheticDataRequest.objects.create(cloud_type=cloud_type)
        return request


class SynthesizeUserTest(TestCase):
    """api.tasks.synthesize_user test case."""

    def setUp(self):
        """Set up test data."""
        self.request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING
        )

    def test_synthesize_user(self):
        """Test happy path to create a new User for the SyntheticDataRequest."""
        response = synthesize.synthesize_user(self.request.id)
        self.assertEqual(response, self.request.id)
        self.request.refresh_from_db()
        self.assertIsNotNone(self.request.user)

    def test_synthesize_user_but_user_already_exists(self):
        """Test early return if the SyntheticDataRequest already has a User."""
        user = util_helper.generate_test_user()
        self.request.user = user
        with mock_post_save_signal_handler():
            self.request.save()

        response = synthesize.synthesize_user(self.request.id)
        self.assertIsNone(response)

    def test_synthesize_user_but_request_id_not_found(self):
        """Test early return if the SyntheticDataRequest does not exist."""
        self.request.delete()
        response = synthesize.synthesize_user(self.request.id)
        self.assertIsNone(response)
