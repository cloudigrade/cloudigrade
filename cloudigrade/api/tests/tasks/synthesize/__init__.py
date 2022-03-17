"""Helpers for testing api.tasks.synthesize.* functions."""

from contextlib import contextmanager

from django.db.models.signals import post_save

from api import models
from api.tasks import synthesize
from util.tests import helper as util_helper


def create_synthetic_data_request_without_post_save(
    cloud_type,
    synthesize_user=True,
    synthesize_cloud_accounts=True,
    synthesize_images=True,
):
    """
    Create a SyntheticDataRequest with only some relations populated.

    This function mocks the post_save signal handler so we can locally create only
    the related objects we want for the test case. This is also convenient for tests
    that use TestCase; only TransactionTestCase triggers the on_commit call inside the
    post-save signal handler that calls the async tasks.
    """
    with util_helper.mock_signal_handler(
        post_save,
        models.synthetic_data_request_post_save_callback,
        models.SyntheticDataRequest,
    ):
        request = models.SyntheticDataRequest.objects.create(cloud_type=cloud_type)
        if not synthesize_user:
            return request
        synthesize.synthesize_user(request.id)
        if not synthesize_cloud_accounts:
            request.refresh_from_db()
            return request
        synthesize.synthesize_cloud_accounts(request.id)
        if not synthesize_images:
            request.refresh_from_db()
            return request
        synthesize.synthesize_images(request.id)
        request.refresh_from_db()
        return request


@contextmanager
def mock_post_save_signal_handler():
    """Mock the post_save signal handler for SyntheticDataRequest."""
    with util_helper.mock_signal_handler(
        post_save,
        models.synthetic_data_request_post_save_callback,
        models.SyntheticDataRequest,
    ):
        yield
