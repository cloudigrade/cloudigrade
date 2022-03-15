"""Collection of tests for api.tasks.synthesize.synthesize_user."""

from django.test import TestCase

from api import AWS_PROVIDER_STRING
from api.tasks import synthesize
from api.tests.tasks.synthesize import (
    create_synthetic_data_request_without_post_save,
    mock_post_save_signal_handler,
)
from util.tests import helper as util_helper


class SynthesizeUserTest(TestCase):
    """api.tasks.synthesize_user test case."""

    def setUp(self):
        """Set up test data."""
        self.request = create_synthetic_data_request_without_post_save(
            cloud_type=AWS_PROVIDER_STRING, synthesize_user=False
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
