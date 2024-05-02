"""Collection of tests targeting custom schema generation."""

from django.test import TestCase

from api.schemas import AzureOfferTemplateSchema, SysconfigSchema
from api.viewsets import SysconfigViewSet


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
                                "version": {"type": "string", "nullable": True},
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
