"""Collection of tests for the 'configurequeues' management command."""
from io import StringIO
from unittest.mock import PropertyMock, call, patch

import faker
from django.core.management import call_command
from django.test import TestCase

_faker = faker.Faker()


class ConfigureQueuesTest(TestCase):
    """Management command 'configurequeues' test case."""

    def test_command_output(self):
        """
        Test that 'configurequeues' ensures its list of queues have DLQs.

        Note:
            This patches over the built-in queue names with dummy test names.
        """
        queue_names = [
            _faker.slug(),
            _faker.slug(),
            _faker.slug(),
        ]
        queue_urls = {
            queue_name: _faker.url() + queue_name for queue_name in queue_names
        }
        expected_get_url_calls = [call(queue_name) for queue_name in queue_names]
        expected_ensure_queue_has_dlq_calls = [
            call(name, url) for name, url in queue_urls.items()
        ]

        def fake_get_sqs_queue_url(name):
            """Fake calls for aws.get_sqs_queue_url."""
            return queue_urls[name]

        _path = "util.management.commands.configurequeues"
        with patch("{}.aws".format(_path)) as mock_aws, patch(
            "{}.Command.queue_names".format(_path), new_callable=PropertyMock
        ) as mock_queue_names:
            mock_queue_names.return_value = queue_names
            mock_aws.get_sqs_queue_url.side_effect = fake_get_sqs_queue_url

            stdout = StringIO()
            stderr = StringIO()
            call_command("configurequeues", stdout=stdout, stderr=stderr)

            mock_aws.get_sqs_queue_url.assert_has_calls(expected_get_url_calls)
            mock_aws.ensure_queue_has_dlq.assert_has_calls(
                expected_ensure_queue_has_dlq_calls
            )
