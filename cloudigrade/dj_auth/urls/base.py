from django.conf.urls import url

from dj_auth import views


urlpatterns = [
    url(r'^me/$', views.UserView.as_view(), name='user'),
    url(r'^$', views.RootView.as_view(), name='root'),
]
