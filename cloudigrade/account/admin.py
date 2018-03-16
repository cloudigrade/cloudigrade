"""Module to expose our models in Django admin."""
from django.contrib import admin

from account.models import Account, Instance, InstanceEvent

admin.site.register(Account, admin.ModelAdmin)
admin.site.register(Instance, admin.ModelAdmin)
admin.site.register(InstanceEvent, admin.ModelAdmin)
