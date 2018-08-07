from dj_auth import permissions
from djoser.views import (
    ActivationView as OriginalActivationView,
    PasswordResetConfirmView as OriginalPasswordResetConfirmView,
    PasswordResetView as OriginalPasswordResetView,
    RootView as OriginalRootView,
    SetPasswordView as OriginalSetPasswordView,
    SetUsernameView as OriginalSetUsernameView,
    TokenCreateView as OriginalTokenCreateView,
    TokenDestroyView as OriginalTokenDestroyView,
    UserView as OriginalUserView
)
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from djoser import utils
from djoser.conf import settings


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


class PasswordResetView(OriginalPasswordResetView):
    """
    Use this endpoint to send email to user with password reset link.
    """


class SetPasswordView(OriginalSetPasswordView):
    """
    Use this endpoint to change user password.
    """
    permission_classes = [permissions.IsAuthenticated]


class PasswordResetConfirmView(OriginalPasswordResetConfirmView):
    """
    Use this endpoint to finish reset password process.
    """


class ActivationView(OriginalActivationView):
    """
    Use this endpoint to activate user account.
    """


class SetUsernameView(OriginalSetUsernameView):
    """
    Use this endpoint to change user username.
    """
    permission_classes = [permissions.IsAuthenticated]


class UserView(OriginalUserView):
    """
    Use this endpoint to retrieve/update user.
    """
    permission_classes = [permissions.IsAuthenticated]
