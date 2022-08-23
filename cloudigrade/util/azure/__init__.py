"""Helper utility package to wrap up common Azure operations."""
from django.conf import settings

from util.azure.identity import (
    get_cloudigrade_credentials,
    get_cloudigrade_subscription_id,
)


# Azure Permissions
#
# Azure permissions or roles are defined via their object ids, this
# unfortunately has the side effect of making it very hard to reference
# what a specific id is, this section is a way to map these azure ids
# to a developer readable name to be used in our template.
#
# The role definition id's referenced here below are Azure
# built-in roles. The id's are static in nature and are documented
# here: https://docs.microsoft.com/en-us/azure/role-based-access-control/built-in-roles
#
# The Reader role allows us to view all resources as needed when doing the
# initial azure vm discovery for managed tenant subscriptions.
#
# Reader:
AZURE_READER_ROLE_ID = "acdd72a7-3385-48ef-bd42-f606fba81ae7"

# The Managed Services Registration assignment Delete Role allows us
# to view the managed tenant lighthouse registration assignments and
# provides us the ability to delete the customer managed tenant
# delegation upon an azure account deletion.
#
# Managed Services Registration assignment Delete Role:
AZURE_MS_REG_ASSIGNMENT_DELETE_ROLE_ID = "91c1777a-f3dc-4fae-b103-61d183457e46"

# Azure Lighthouse ARM Template Offer
ARM_TEMPLATE_NAME = f"cloudigrade-{settings.CLOUDIGRADE_ENVIRONMENT}"
ARM_TEMPLATE = {
    "$schema": "https://schema.management.azure.com/schemas/"
    "2019-08-01/subscriptionDeploymentTemplate.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {
        "mspOfferName": {
            "type": "string",
            "defaultValue": f"{ARM_TEMPLATE_NAME}",
            "allowedValues": [f"{ARM_TEMPLATE_NAME}"],
        },
        "mspOfferDescription": {
            "type": "string",
            "defaultValue": "",
            "allowedValues": [""],
        },
        "managedByTenantId": {
            "type": "string",
            "defaultValue": f"{settings.AZURE_TENANT_ID}",
            "allowedValues": [f"{settings.AZURE_TENANT_ID}"],
        },
        "authorizations": {
            "type": "array",
            "defaultValue": [
                {
                    "principalId": f"{settings.AZURE_SP_OBJECT_ID}",
                    "principalIdDisplayName": f"{ARM_TEMPLATE_NAME}",
                    "roleDefinitionId": f"{AZURE_READER_ROLE_ID}",
                },
                {
                    "principalId": f"{settings.AZURE_SP_OBJECT_ID}",
                    "principalIdDisplayName": f"{ARM_TEMPLATE_NAME}",
                    "roleDefinitionId": f"{AZURE_MS_REG_ASSIGNMENT_DELETE_ROLE_ID}",
                },
            ],
            "allowedValues": [
                [
                    {
                        "principalId": f"{settings.AZURE_SP_OBJECT_ID}",
                        "principalIdDisplayName": f"{ARM_TEMPLATE_NAME}",
                        "roleDefinitionId": f"{AZURE_READER_ROLE_ID}",
                    },
                    {
                        "principalId": f"{settings.AZURE_SP_OBJECT_ID}",
                        "principalIdDisplayName": f"{ARM_TEMPLATE_NAME}",
                        "roleDefinitionId": f"{AZURE_MS_REG_ASSIGNMENT_DELETE_ROLE_ID}",
                    },
                ]
            ],
        },
    },
    "variables": {
        "mspRegistrationName": "[guid(parameters('mspOfferName'))]",
        "mspAssignmentName": "[guid(parameters('mspOfferName'))]",
    },
    "resources": [
        {
            "type": "Microsoft.ManagedServices/registrationDefinitions",
            "apiVersion": "2020-02-01-preview",
            "name": "[variables('mspRegistrationName')]",
            "properties": {
                "registrationDefinitionName": "[parameters('mspOfferName')]",
                "description": "[parameters('mspOfferDescription')]",
                "managedByTenantId": "[parameters('managedByTenantId')]",
                "authorizations": "[parameters('authorizations')]",
            },
        },
        {
            "type": "Microsoft.ManagedServices/registrationAssignments",
            "apiVersion": "2020-02-01-preview",
            "name": "[variables('mspAssignmentName')]",
            "dependsOn": [
                "[resourceId('Microsoft.ManagedServices/"
                "registrationDefinitions/', variables('mspRegistrationName'))]"
            ],
            "properties": {
                "registrationDefinitionId": "[resourceId('Microsoft.ManagedServ"
                "ices/registrationDefinitions/', "
                "variables('mspRegistrationName'))]"
            },
        },
    ],
    "outputs": {
        "mspOfferName": {
            "type": "string",
            "value": "[concat('Managed by', ' ', parameters('mspOfferName'))]",
        },
        "authorizations": {
            "type": "array",
            "value": "[parameters('authorizations')]",
        },
    },
}
