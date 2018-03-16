"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from account.views import AccountViewSet, ReportViewSet

router = routers.DefaultRouter()
router.register(r'account', AccountViewSet)
router.register(r'report', ReportViewSet, base_name='report')

urlpatterns = [
    url(r'^api/v1/', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    path('admin/', admin.site.urls),
]
