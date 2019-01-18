"""Collection of tests for InstanceEventViewSet."""
from urllib.parse import urlparse

from django.test import TestCase
from django.urls import resolve
from rest_framework.test import (APIRequestFactory,
                                 force_authenticate)

from account.models import (AwsInstanceEvent,
                            AwsMachineImage)
from account.tests import helper as account_helper
from account.views import (InstanceEventViewSet)
from util.tests import helper as util_helper

HOURS_5 = 60. * 60 * 5


class InstanceEventViewSetTest(TestCase):
    """InstanceEventViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)
        self.account1 = account_helper.generate_aws_account(user=self.user1)
        self.account2 = account_helper.generate_aws_account(user=self.user1)
        self.account3 = account_helper.generate_aws_account(user=self.user2)
        self.account4 = account_helper.generate_aws_account(user=self.user2)
        self.instance1 = account_helper.generate_aws_instance(self.account1)
        self.instance2 = account_helper.generate_aws_instance(self.account2)
        self.instance3 = account_helper.generate_aws_instance(self.account3)
        self.instance4 = account_helper.generate_aws_instance(self.account4)
        powered_time = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
        self.event1 = account_helper.generate_single_aws_instance_event(
            instance=self.instance1, occurred_at=powered_time
        )
        self.event2 = account_helper.generate_single_aws_instance_event(
            instance=self.instance2, occurred_at=powered_time
        )
        self.event3 = account_helper.generate_single_aws_instance_event(
            instance=self.instance3, occurred_at=powered_time
        )
        self.event4 = account_helper.generate_single_aws_instance_event(
            instance=self.instance4, occurred_at=powered_time
        )
        self.factory = APIRequestFactory()

    def assertResponseHasEventData(self, response, event):
        """Assert the response has data matching the instance event object."""
        self.assertEqual(
            response.data['id'], event.id
        )
        self.assertEqual(
            response.data['instance'],
            f'http://testserver/api/v1/instance/{event.instance.id}/'
        )
        self.assertEqual(
            response.data['instance_id'], event.instance.id
        )
        self.assertEqual(
            response.data['resourcetype'], event.__class__.__name__
        )
        self.assertEqual(
            response.data['url'],
            f'http://testserver/api/v1/event/{event.id}/'
        )

        if isinstance(event, AwsInstanceEvent):
            self.assertEqual(
                response.data['subnet'], event.subnet
            )
            self.assertEqual(
                response.data['machineimage_id'], event.machineimage_id
            )
            __, machineimage_args, machineimage_kwargs = resolve(
                urlparse(response.data['machineimage'])[2]
            )
            machineimage = AwsMachineImage.objects.get(
                *machineimage_args, **machineimage_kwargs
            )
            self.assertEqual(machineimage, event.machineimage)
            self.assertEqual(
                response.data['event_type'], event.event_type
            )
            self.assertEqual(
                response.data['instance_type'], event.instance_type
            )

    def get_event_get_response(self, user, event_id):
        """
        Generate a response for a get-retrieve on the InstanceViewSet.

        Args:
            user (User): Django auth user performing the request
            event_id (int): the id of the instance event to retrieve
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/event/')
        force_authenticate(request, user=user)
        view = InstanceEventViewSet.as_view(actions={'get': 'retrieve'})
        response = view(request, pk=event_id)
        return response

    def get_event_list_response(self, user, data=None):
        """
        Generate a response for a get-list on the InstanceEventViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/event/', data)
        force_authenticate(request, user=user)
        view = InstanceEventViewSet.as_view(actions={'get': 'list'})
        response = view(request)
        return response

    def get_event_ids_from_list_response(self, response):
        """
        Get the instance event id values from the paginated response.

        Args:
            response (Response): Django response object to inspect

        Returns:
            set[int]: the event id values found in the response

        """
        event_ids = set([
            event['id'] for event in response.data['results']
        ])
        return event_ids

    def test_list_events_as_user1(self):
        """Assert that user1 sees only its own instance events."""
        expected_events = {
            self.event1.id,
            self.event2.id,
        }
        response = self.get_event_list_response(self.user1)
        actual_events = \
            self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_user2(self):
        """Assert that user2 sees only its own instance events."""
        expected_events = {
            self.event3.id,
            self.event4.id,
        }
        response = self.get_event_list_response(self.user2)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_superuser(self):
        """Assert that the superuser sees all events regardless of owner."""
        expected_events = {
            self.event1.id,
            self.event2.id,
            self.event3.id,
            self.event4.id
        }
        response = self.get_event_list_response(self.superuser)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_superuser_with_user_filter(self):
        """Assert that the superuser sees events filtered by user_id."""
        expected_events = {
            self.event3.id,
            self.event4.id
        }
        params = {'user_id': self.user2.id}
        response = self.get_event_list_response(self.superuser, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_superuser_with_instance_filter(self):
        """Assert that the superuser sees events filtered by instance_id."""
        expected_events = {
            self.event3.id,
        }
        params = {'instance_id': self.instance3.id}
        response = self.get_event_list_response(self.superuser, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_user1_with_instance_filter(self):
        """Assert that the user1 sees user1 events filtered by instance_id."""
        expected_events = {
            self.event1.id,
        }
        params = {'instance_id': self.instance1.id}
        response = self.get_event_list_response(self.user1, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_user2_with_instance_filter(self):
        """Assert that the user2 sees user2 events filtered by instance_id."""
        expected_events = {
            self.event3.id,
        }
        params = {'instance_id': self.instance3.id}
        response = self.get_event_list_response(self.user2, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_get_user1s_event_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own events."""
        user = self.user1
        event = self.event2  # Event belongs to user1.

        response = self.get_event_get_response(user, event.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasEventData(response, event)

    def test_get_user1s_event_as_user2_returns_404(self):
        """Assert that user2 cannot get an event belonging to user1."""
        user = self.user2
        event = self.event2  # Event belongs to user1, NOT user2.

        response = self.get_event_get_response(user, event.id)
        self.assertEqual(response.status_code, 404)

    def test_get_user1s_event_as_superuser_returns_ok(self):
        """Assert that superuser can get another user's events."""
        user = self.superuser
        event = self.event2  # Instance belongs to user1, NOT superuser.

        response = self.get_event_get_response(user, event.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasEventData(response, event)

    def test_list_events_as_superuser_with_bad_filter(self):
        """Assert that the list events returns 400 with bad user_id."""
        params = {'user_id': 'not_an_int'}
        response = self.get_event_list_response(self.superuser, params)
        self.assertEqual(response.status_code, 400)

    def test_list_events_as_superuser_with_user_and_instance_filters(self):
        """Assert that super user can stack instance & user filters."""
        expected_events = {
            self.event3.id,
        }
        params = {'instance_id': self.instance3.id,
                  'user_id': self.user2.id}
        response = self.get_event_list_response(self.superuser, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)
