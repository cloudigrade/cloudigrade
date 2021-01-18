"""URL configuration for cloudigrade."""
from django.urls import include, path

urlpatterns = [
    path("api/cloudigrade/v2/", include("api.urls")),
    path("internal/", include("internal.urls")),
]
