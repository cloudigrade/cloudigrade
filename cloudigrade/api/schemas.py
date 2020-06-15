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
            "operationId": self._get_operation_id(path, method).capitalize(),
            "responses": {
                "200": {
                    "content": {
                        "application/json": {"schema": {"items": {}, "type": "object"}}
                    },
                    "description": "Retrieve current system configuration.",
                }
            },
        }
        return operation
