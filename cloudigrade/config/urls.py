"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from account.views import (AccountViewSet,
                           CloudAccountOverviewViewSet,
                           DailyInstanceActivityViewSet,
                           ImagesActivityOverviewViewSet,
                           InstanceEventViewSet,
                           InstanceViewSet,
                           MachineImageViewSet,
                           SysconfigViewSet,
                           UserViewSet)
from api import views as v2views

router_v1 = routers.DefaultRouter()
router_v1.register(r'account', AccountViewSet)
router_v1.register(r'event', InstanceEventViewSet)
router_v1.register(r'instance', InstanceViewSet)
router_v1.register(r'image', MachineImageViewSet)
router_v1.register(r'sysconfig', SysconfigViewSet, basename='sysconfig')
router_v1.register(r'report/accounts', CloudAccountOverviewViewSet,
                   basename='report-accounts')
router_v1.register(r'user', UserViewSet, basename='user')
router_v1.register(r'report/images', ImagesActivityOverviewViewSet,
                   basename='report-images')
router_v1.register(r'report/instances', DailyInstanceActivityViewSet,
                   basename='report-instances')

router_v2 = routers.DefaultRouter()
router_v2.register(r'accounts', v2views.AccountViewSet,
                   basename='v2-account')
router_v2.register(r'instances', v2views.InstanceViewSet,
                   basename='v2-instance')
router_v2.register(r'images', v2views.MachineImageViewSet,
                   basename='v2-machineimage')
router_v2.register(r'sysconfig', v2views.SysconfigViewSet,
                   basename='v2-sysconfig')

urlpatterns = [
    url(r'^api/v1/', include(router_v1.urls)),
    url(r'^v2/', include(router_v2.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    url(r'^healthz/', include('health_check.urls')),
    url(r'^auth/', include('dj_auth.urls')),
    url(r'^auth/', include('dj_auth.urls.authtoken')),
    path('admin/', admin.site.urls),
]
