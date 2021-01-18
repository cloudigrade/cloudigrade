"""URL configuration for cloudigrade."""
from api.urls import urlpatterns as public_urlpatterns
from internal.urls import urlpatterns as internal_urlpatterns

urlpatterns = public_urlpatterns + internal_urlpatterns
