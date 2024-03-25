"""Collection of tests for ``util.azure.identity`` module."""

from unittest.mock import Mock, patch
from uuid import UUID

from django.test import TestCase

from util.azure.identity import get_cloudigrade_available_subscriptions


class UtilAzureIdentityTest(TestCase):
    """Azure Identity utility functions test case."""

    def setUp(self):
        """Set up shared values for azure identity tests."""
        mock_customer_sub = Mock()
        mock_cloudigrade_sub = Mock()
        customer_sub_dict = {
            "id": "/subscriptions/d9812b28-6286-4501-9cd5-f43b2a455364",
            "subscription_id": "d9812b28-6286-4501-9cd5-f43b2a455364",
            "display_name": "FizzBuzz Enterprise Inc.",
            "tenant_id": "c5e703e3-653b-4515-89ac-4d8bdc388f05",
            "state": "Enabled",
            "subscription_policies": {
                "location_placement_id": "Public_2014-09-01",
                "quota_id": "EnterpriseAgreement_2014-09-01",
                "spending_limit": "Off",
            },
            "authorization_source": "RoleBased",
            "managed_by_tenants": [
                {"tenant_id": "1e1cc753-fcc2-4b68-847d-f3ed485a8d89"}
            ],
        }
        cloudigrade_sub_dict = {
            "id": "/subscriptions/03cd596c-179c-4191-985a-4bc6256f9126",
            "subscription_id": "03cd596c-179c-4191-985a-4bc6256f9126",
            "display_name": "Cloudigrade Account",
            "tenant_id": "1e1cc753-fcc2-4b68-847d-f3ed485a8d89",
            "state": "Enabled",
            "subscription_policies": {
                "location_placement_id": "Public_2014-09-01",
                "quota_id": "EnterpriseAgreement_2014-09-01",
                "spending_limit": "Off",
            },
            "authorization_source": "RoleBased",
            "managed_by_tenants": [],
        }
        mock_customer_sub.as_dict.return_value = customer_sub_dict
        mock_cloudigrade_sub.as_dict.return_value = cloudigrade_sub_dict

        self.customer_subscription_id = UUID("d9812b28-6286-4501-9cd5-f43b2a455364")
        self.cloudigrade_subscription_id = UUID("03cd596c-179c-4191-985a-4bc6256f9126")
        self.subscriptions_response = [
            mock_customer_sub,
            mock_cloudigrade_sub,
        ]

    @patch("util.azure.identity.SubscriptionClient")
    def test_get_cloudigrade_available_subscriptions(self, mock_client):
        """Assert get_cloudigrade_available_subscriptions returns subs array."""
        mock_subs = mock_client.return_value.subscriptions.list
        mock_subs.return_value = self.subscriptions_response

        subs = get_cloudigrade_available_subscriptions()
        self.assertIn(self.customer_subscription_id, subs)
        self.assertIn(self.cloudigrade_subscription_id, subs)
