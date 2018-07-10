"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from account.views import (AccountViewSet,
                           CloudAccountOverviewViewSet,
                           DailyInstanceActivityViewSet,
                           InstanceEventViewSet,
                           InstanceViewSet,
                           MachineImageViewSet,
                           ReportViewSet,
                           SysconfigViewSet)

router = routers.DefaultRouter()
router.register(r'account', AccountViewSet)
router.register(r'event', InstanceEventViewSet)
router.register(r'instance', InstanceViewSet)
router.register(r'image', MachineImageViewSet)
router.register(r'report', ReportViewSet, base_name='report')
router.register(r'sysconfig', SysconfigViewSet, base_name='sysconfig')
router.register(r'report/accounts', CloudAccountOverviewViewSet,
                base_name='report-accounts')
router.register(r'report/instances', DailyInstanceActivityViewSet,
                base_name='report-instances')

urlpatterns = [
    url(r'^api/v1/', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    url(r'^healthz/', include('health_check.urls')),
    url(r'^auth/', include('dj_auth.urls')),
    url(r'^auth/', include('dj_auth.urls.authtoken')),
    path('admin/', admin.site.urls),
]
