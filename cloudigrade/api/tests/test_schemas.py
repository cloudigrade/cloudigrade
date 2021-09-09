"""Collection of tests targeting custom schema generation."""
from django.test import TestCase

from api.schemas import AzureOfferTemplateSchema, ConcurrentSchema, SysconfigSchema
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
                                "azure_offer_template_path": {
                                    "type": "string",
                                    "format": "uri",
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

    def test_azureoffertemplateschema(self):
        """Test that azure offer template schema generation returns expected results."""
        schema = AzureOfferTemplateSchema()
        path = "/api/cloudigrade/v2/azure-offer-template/"
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
                                "$schema": {"type": "string"},
                                "contentVersion": {"type": "string"},
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "mspOfferName": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "defaultValue": {"type": "string"},
                                                "allowedValues": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                        },
                                        "mspOfferDescription": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "defaultValue": {"type": "string"},
                                                "allowedValues": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                        },
                                        "managedByTenantId": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "defaultValue": {"type": "string"},
                                                "allowedValues": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                        },
                                        "authorizations": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "defaultValue": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "principalId": {
                                                                "type": "string"
                                                            },
                                                            "roleDefinitionId": {
                                                                "type": "string"
                                                            },
                                                            "principalId"
                                                            "DisplayName": {
                                                                "type": "string"
                                                            },
                                                        },
                                                    },
                                                },
                                                "allowedValues": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "array",
                                                        "items": {
                                                            "type": "object",
                                                            "properties": {
                                                                "principalId": {
                                                                    "type": "string"
                                                                },
                                                                "roleDefinition"
                                                                "Id": {
                                                                    "type": "string"
                                                                },
                                                                "principalId"
                                                                "DisplayName": {
                                                                    "type": "string"
                                                                },
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                                "variables": {
                                    "type": "object",
                                    "properties": {
                                        "mspRegistrationName": {"type": "string"},
                                        "mspAssignmentName": {"type": "string"},
                                    },
                                },
                                "resources": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "type": {"type": "string"},
                                            "apiVersion": {"type": "string"},
                                            "name": {"type": "string"},
                                            "properties": {
                                                "type": "object",
                                                "properties": {
                                                    "registrationDefinitionName": {
                                                        "type": "string"
                                                    },
                                                    "description": {"type": "string"},
                                                    "managedByTenantId": {
                                                        "type": "string"
                                                    },
                                                    "authorizations": {
                                                        "type": "string"
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                                "outputs": {
                                    "type": "object",
                                    "properties": {
                                        "mspOfferName": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "value": {"type": "string"},
                                            },
                                        },
                                        "authorizations": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "value": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            },
                        }
                    }
                },
                "description": "Retrieve current azure offer template.",
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
                {
                    "name": "start_date",
                    "in": "query",
                    "required": False,
                    "description": "Start Date (inclusive) of the concurrent "
                    "usage in the form (YYYY-MM-DD).",
                    "schema": {"type": "string", "format": "date"},
                },
                {
                    "name": "end_date",
                    "in": "query",
                    "required": False,
                    "description": "End Date (exclusive) of the concurrent "
                    "usage in the form (YYYY-MM-DD).",
                    "schema": {"type": "string", "format": "date"},
                },
            ],
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "meta": {
                                        "type": "object",
                                        "properties": {
                                            "count": {
                                                "type": "integer",
                                                "example": 123,
                                            }
                                        },
                                    },
                                    "links": {
                                        "type": "object",
                                        "properties": {
                                            "first": {
                                                "type": "string",
                                                "nullable": True,
                                                "format": "uri",
                                            },
                                            "last": {
                                                "type": "string",
                                                "nullable": True,
                                                "format": "uri",
                                            },
                                            "next": {
                                                "type": "string",
                                                "nullable": True,
                                                "format": "uri",
                                            },
                                            "previous": {
                                                "type": "string",
                                                "nullable": True,
                                                "format": "uri",
                                            },
                                        },
                                    },
                                    "data": {
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
