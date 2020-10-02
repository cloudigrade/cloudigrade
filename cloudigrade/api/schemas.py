"""Custom DRF Schemas."""
from rest_framework.schemas.openapi import AutoSchema


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
