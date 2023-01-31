"""Module to expose our models in Django admin."""
from django.contrib import admin

from api.clouds.aws.models import AwsCloudAccount
from api.clouds.azure.models import AzureCloudAccount
from api.models import CloudAccount

admin.site.register(CloudAccount)
admin.site.register(AwsCloudAccount)
admin.site.register(AzureCloudAccount)
