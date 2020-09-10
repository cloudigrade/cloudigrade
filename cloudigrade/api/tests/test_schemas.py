"""Collection of tests targeting custom schema generation."""
from django.test import TestCase

from api.schemas import ConcurrentSchema, SysconfigSchema
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
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "aws_account_id": {"type": "string"},
                                "aws_policies": {
                                    "type": "object",
                                    "properties": {
                                        "traditional_inspection": {
                                            "type": "object",
                                            "properties": {
                                                "Statement": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "Action": {
                                                                "type": "array",
                                                                "items": {
                                                                    "type": "string"
                                                                },
                                                            },
                                                        },
                                                        "additionalProperties": {
                                                            "type": "string"
                                                        },
                                                    },
                                                },
                                                "Version": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                                "version": {"type": "string"},
                            },
                        }
                    }
                },
                "description": "Retrieve current system configuration.",
            }
        }

        self.assertIsNotNone(spec["operationId"])
        self.assertEqual(spec["responses"], expected_response)

    def test_concurrentschema(self):
        """Test that the concurrent schema generation returns expected results."""
        schema = ConcurrentSchema()
        path = "/api/cloudigrade/v2/concurrent/"
        method = "GET"
        schema.view = SysconfigViewSet.as_view({"get": "list"})
        spec = schema.get_operation(path, method)

        expected_response = {
            "operationId": "listDailyConcurrentUsages",
            "parameters": [
                {
                    "name": "limit",
                    "required": False,
                    "in": "query",
                    "description": "Number of results to return per page.",
                    "schema": {"type": "integer"},
                },
                {
                    "name": "offset",
                    "required": False,
                    "in": "query",
                    "description": "The initial index from "
                    "which to return the results.",
                    "schema": {"type": "integer"},
                },
            ],
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "count": {"type": "integer", "example": 123},
                                    "next": {"type": "string", "nullable": True},
                                    "previous": {"type": "string", "nullable": True},
                                    "results": {
                                        "type": "array",
                                        "items": {
                                            "properties": {
                                                "date": {
                                                    "type": "string",
                                                    "format": "date",
                                                },
                                                "maximum_counts": {
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "arch": {"type": "string"},
                                                            "sla": {"type": "string"},
                                                            "role": {"type": "string"},
                                                            "usage": {"type": "string"},
                                                            "service_type": {
                                                                "type": "string"
                                                            },
                                                            "instance_count": {
                                                                "type": "integer"
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                        "required": ["date"],
                                    },
                                },
                            },
                        }
                    },
                    "description": "Generate report of concurrent "
                    "usage within a time frame.",
                }
            },
        }

        self.assertIsNotNone(spec["operationId"])
        self.assertIsNotNone(spec["parameters"])
        self.assertEqual(spec, expected_response)
