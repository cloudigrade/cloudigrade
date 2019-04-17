"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from account.v2 import views as v2views
from account.views import (AccountViewSet,
                           CloudAccountOverviewViewSet,
                           DailyInstanceActivityViewSet,
                           ImagesActivityOverviewViewSet,
                           InstanceEventViewSet,
                           InstanceViewSet,
                           MachineImageViewSet,
                           SysconfigViewSet,
                           UserViewSet)

router = routers.DefaultRouter()
router.register(r'account', AccountViewSet)
router.register(r'event', InstanceEventViewSet)
router.register(r'instance', InstanceViewSet)
router.register(r'image', MachineImageViewSet)
router.register(r'sysconfig', SysconfigViewSet, basename='sysconfig')
router.register(r'report/accounts', CloudAccountOverviewViewSet,
                basename='report-accounts')
router.register(r'user', UserViewSet, basename='user')
router.register(r'report/images', ImagesActivityOverviewViewSet,
                basename='report-images')
router.register(r'report/instances', DailyInstanceActivityViewSet,
                basename='report-instances')

routerv2 = routers.DefaultRouter()
routerv2.register(r'account', v2views.AccountViewSet,
                  basename='v2-account')
routerv2.register(r'instance', v2views.InstanceViewSet,
                  basename='v2-instance')
routerv2.register(r'image', v2views.MachineImageViewSet,
                  basename='v2-machineimage')
routerv2.register(r'sysconfig', v2views.SysconfigViewSet,
                  basename='v2-sysconfig')

urlpatterns = [
    url(r'^api/v1/', include(router.urls)),
    url(r'^v2/', include(routerv2.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    url(r'^healthz/', include('health_check.urls')),
    url(r'^auth/', include('dj_auth.urls')),
    url(r'^auth/', include('dj_auth.urls.authtoken')),
    path('admin/', admin.site.urls),
]
