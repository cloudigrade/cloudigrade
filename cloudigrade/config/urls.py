"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from api import views

router = routers.DefaultRouter()
router.register(r'accounts', views.AccountViewSet,
                basename='v2-account')
router.register(r'instances', views.InstanceViewSet,
                basename='v2-instance')
router.register(r'images', views.MachineImageViewSet,
                basename='v2-machineimage')
router.register(r'sysconfig', views.SysconfigViewSet,
                basename='v2-sysconfig')
router.register(r'concurrent', views.DailyConcurrentUsageViewSet,
                basename='v2-concurrent')

urlpatterns = [
    url(r'^v2/', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    url(r'^healthz/', include('health_check.urls')),
    path('admin/', admin.site.urls),
]
