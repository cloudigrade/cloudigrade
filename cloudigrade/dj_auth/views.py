from django.contrib.auth import get_user_model
from djoser import utils
from djoser.conf import settings
from djoser.views import (
    RootView as OriginalRootView,
    TokenCreateView as OriginalTokenCreateView,
    TokenDestroyView as OriginalTokenDestroyView,
    UserView as OriginalUserView
)
from rest_framework.response import Response

from dj_auth import permissions


class RootView(OriginalRootView):
    """
    Root endpoint - use one of sub endpoints.
    """


class TokenCreateView(OriginalTokenCreateView):
    """
    Use this endpoint to obtain user authentication token.
    """
    Users = get_user_model()

    serializer_class = OriginalTokenCreateView.serializer_class
    permission_classes = OriginalTokenCreateView.permission_classes

    def _action(self, serializer):
        token = utils.login_user(self.request, serializer.user)
        token_serializer_class = settings.SERIALIZERS.token
        request_user = self.Users.objects.get(
            username=self.request.data.get('username'))
        content = {
            'auth_token': token_serializer_class(token).data['auth_token'],
            'is_superuser': request_user.is_superuser
        }
        return Response(content)


class TokenDestroyView(OriginalTokenDestroyView):
    """
    Use this endpoint to logout user (remove user authentication token).
    """
    permission_classes = [permissions.IsAuthenticated]


class UserView(OriginalUserView):
    """
    Use this endpoint to retrieve/update user.
    """
    permission_classes = [permissions.IsAuthenticated]
