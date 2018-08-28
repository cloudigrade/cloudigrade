from django.conf.urls import url
from django.contrib.auth import get_user_model

from dj_auth import views

User = get_user_model()


urlpatterns = [
    url(r'^me/$', views.UserView.as_view(), name='user'),
    url(
        r'^users/activate/$',
        views.ActivationView.as_view(),
        name='user-activate'
    ),
    url(
        r'^{0}/$'.format(User.USERNAME_FIELD),
        views.SetUsernameView.as_view(),
        name='set_username'
    ),
    url(r'^$', views.RootView.as_view(), name='root'),
]
