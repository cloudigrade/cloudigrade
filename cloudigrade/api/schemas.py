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

    def __init__(self, descriptive_name, *args, **kwargs):
        """Initialize instance variables."""
        super(DescriptiveAutoSchema, self).__init__(*args, **kwargs)
        self.descriptive_name = descriptive_name
        self.an = "an" if descriptive_name.lower()[:1] in "aeiou" else "a"

    def get_description(self, path, method):
        """Construct a custom description string."""
        method_name = getattr(self.view, "action", method.lower())
        description = self.description_map.get(method_name, None)
        if description:
            return description.format(an=self.an, type=self.descriptive_name)
        else:
            return super(DescriptiveAutoSchema, self).get_description(path, method)


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
            },
        }
        return operation


class ConcurrentSchema(AutoSchema):
    """Schema for the concurrent usage viewset."""

    def get_operation(self, path, method):
        """
        Hard code schema for the concurrent usage get operation.

        TODO: Reassess the need for this when drf schema generation is improved.
        """
        operation = {
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
                },
            },
        }

        return operation
