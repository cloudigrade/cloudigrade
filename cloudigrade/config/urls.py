"""URL configuration for cloudigrade."""
from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path("api/cloudigrade/v2/", include("api.urls")),
    path("internal/", include("internal.urls")),
]

if not settings.IS_PRODUCTION:
    # Allow the standard Django admin only in not-production environments.
    from django.contrib import admin

    urlpatterns += [
        path("api-auth/", include("rest_framework.urls")),
        path("admin/", admin.site.urls),
    ]
