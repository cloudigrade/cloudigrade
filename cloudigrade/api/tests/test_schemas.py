"""Collection of tests targeting custom schema generation."""
from django.test import TestCase

from api.schemas import SysconfigSchema
from api.views import SysconfigViewSet


class SchemaTestCase(TestCase):
    """Test custom openapi.json Schema generation."""

    def test_sysconfigschema(self):
        """Test that the sysconfig schema generation returns expected results."""
        schema = SysconfigSchema()
        path = "/api/cloudigrade/v2/sysconfig/"
        method = "GET"
        schema.view = SysconfigViewSet.as_view({"get": "list"})
        spec = schema.get_operation(path, method)

        expected_response = {
            "200": {
                "content": {
                    "application/json": {"schema": {"items": {}, "type": "object"}}
                },
                "description": "Retrieve current system configuration.",
            }
        }

        self.assertIsNotNone(spec["operationId"])
        self.assertEqual(spec["responses"], expected_response)
