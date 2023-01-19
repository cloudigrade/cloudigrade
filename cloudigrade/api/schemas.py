"""Custom DRF Schemas."""
from rest_framework.schemas.openapi import AutoSchema


class DescriptiveAutoSchema(AutoSchema):
    """Improved AutoSchema that generates method-specific descriptions."""

    description_map = {
        "create": "Create {an} {type}.",
        "retrieve": "Retrieve {an} {type}.",
        "list": "List {type}s.",
        "update": "Update {an} {type}.",
        "partial_update": "Partially update {an} {type}.",
        "destroy": "Delete {an} {type}.",
    }

    def __init__(self, descriptive_name, custom_responses=None, *args, **kwargs):
        """Initialize instance variables."""
        super(DescriptiveAutoSchema, self).__init__(*args, **kwargs)
        self.descriptive_name = descriptive_name
        self.an = "an" if descriptive_name.lower()[:1] in "aeiou" else "a"
        self.custom_responses = custom_responses

    def get_description(self, path, method):
        """Construct a custom description string."""
        method_name = getattr(self.view, "action", method.lower())
        description = self.description_map.get(method_name, None)
        if description:
            return description.format(an=self.an, type=self.descriptive_name)
        else:
            return super(DescriptiveAutoSchema, self).get_description(path, method)

    def get_responses(self, path, method):
        """Return a custom responses object if given, else use super implementation."""
        if self.custom_responses and method in self.custom_responses:
            return self.custom_responses[method]
        return super(DescriptiveAutoSchema, self).get_responses(path, method)


class SysconfigSchema(AutoSchema):
    """Schema for the sysconfig viewset."""

    def get_operation(self, path, method):
        """
        Hard code schema for the sysconfig get operation.

        TODO: Reassess the need for this when drf schema generation is improved.
        """
        operation = {
            "operationId": "listSysconfigViewSets",
            "responses": {
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
                                    "version": {
                                        "type": "string",
                                        "nullable": True,
                                    },
                                },
                            }
                        }
                    },
                    "description": "Retrieve current system configuration.",
                }
            },
        }
        return operation


class AzureOfferTemplateSchema(AutoSchema):
    """Schema for the AzureOfferTemplate viewset."""

    def get_operation(self, path, method):
        """
        Hard code schema for the AzureOfferTemplate get operation.

        TODO: Reassess the need for this when drf schema generation is improved.
        """
        operation = {
            "operationId": "listAzureOfferTemplateViewSets",
            "description": "Get ARM offer template populated "
            "with ids used by this installation.",
            "responses": {
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
                                                        "description": {
                                                            "type": "string"
                                                        },
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
            },
        }

        return operation
