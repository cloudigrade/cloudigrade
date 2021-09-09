"""Collection of tests for AzureOfferTemplateViewSet."""

from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory

from api.views import AzureOfferTemplateViewSet
from util.azure import ARM_TEMPLATE


class AzureOfferTemplateViewSetTest(TransactionTestCase):
    """AzureOfferTemplateViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.factory = APIRequestFactory()

    def get_azure_offer_template_list(self):
        """
        Generate a response for a get on the AzureOfferTemplateViewSet.

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get("/azure-offer-template/")
        view = AzureOfferTemplateViewSet.as_view(actions={"get": "list"})
        response = view(request)
        return response

    def test_list_azure_offer_template(self):
        """Assert that azure offer template is returned correctly."""
        response = self.get_azure_offer_template_list()
        self.assertEqual(200, response.status_code)
        self.assertEqual("*", response.headers.get("Access-Control-Allow-Origin"))
        self.assertEqual(ARM_TEMPLATE, response.data)
