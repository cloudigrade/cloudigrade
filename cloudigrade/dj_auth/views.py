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
    UserCreateView as OriginalUserCreateView,
    UserDeleteView as OriginalUserDeleteView,
    UserView as OriginalUserView
)


class RootView(OriginalRootView):
    """
    Root endpoint - use one of sub endpoints.
    """


class UserCreateView(OriginalUserCreateView):
    """
    Use this endpoint to register new user.
    """


class UserDeleteView(OriginalUserDeleteView):
    """
    Use this endpoint to remove actually authenticated user
    """
    permission_classes = [permissions.IsAuthenticated]


class TokenCreateView(OriginalTokenCreateView):
    """
    Use this endpoint to obtain user authentication token.
    """


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
