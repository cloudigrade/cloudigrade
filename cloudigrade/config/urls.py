"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import path, include
from rest_framework import routers

from account.views import AccountViewSet

router = routers.DefaultRouter()
router.register(r'account', AccountViewSet)

urlpatterns = [
    url(r'^api/v1/', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    path('admin/', admin.site.urls),
]
