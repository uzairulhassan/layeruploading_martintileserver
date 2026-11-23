from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth import update_session_auth_hash
from django.db import connection, transaction
from rest_framework import generics, permissions, status, viewsets
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.api_errors import ErrorCode, error_response, stringify_detail

from .models import Role, User
from .permissions import CanManageRoles
from .security import (
    blacklist_user_refresh_tokens,
    clear_failed_logins,
    client_ip_from_request,
    is_login_locked,
    register_failed_login,
)
from .signup_policy import PUBLIC_SIGNUP_CLOSED_MESSAGE, public_signup_allowed
from .serializers import (
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    OnetimeRegisterSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    RoleSerializer,
    SessionLoginSerializer,
    TokenObtainPairWithUserSerializer,
    UsernameAvailabilitySerializer,
    UserSerializer,
    UserSummarySerializer,
)
from .throttling import (
    AuthLoginThrottle,
    AuthRegisterThrottle,
    AuthRefreshThrottle,
    AuthUsernameThrottle,
)

# Stable Postgres advisory-lock key for onetime bootstrap (empty-table race).
_ONETIME_ADVISORY_LOCK_KEY = 827_401_933


class BaseRegisterView(generics.CreateAPIView):
    """Shared create flow: validate → save. User must sign in afterwards."""

    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRegisterThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "detail": "Account created successfully. Please sign in.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class RegisterView(BaseRegisterView):
    """Public sign-up when ``ALLOW_PUBLIC_SIGNUP`` is on. Otherwise always 403."""

    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        if not public_signup_allowed():
            return error_response(
                request,
                message=PUBLIC_SIGNUP_CLOSED_MESSAGE,
                code=ErrorCode.PERMISSION_DENIED,
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)


class OnetimeRegisterView(BaseRegisterView):
    """One-shot bootstrap registration for the first Admin account."""

    serializer_class = OnetimeRegisterSerializer

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_ONETIME_ADVISORY_LOCK_KEY])
            if User.objects.exists():
                return error_response(
                    request,
                    message="Initial setup is already complete.",
                    code=ErrorCode.PERMISSION_DENIED,
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            return super().create(request, *args, **kwargs)


class UsernameAvailabilityView(APIView):
    """Live username check for signup / onetime / account forms."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthUsernameThrottle]

    def get(self, request):
        # Anonymous probing only while signup or first-time onetime is open.
        if not request.user.is_authenticated:
            if not public_signup_allowed() and User.objects.exists():
                return error_response(
                    request,
                    message="Username checks are not available.",
                    code=ErrorCode.PERMISSION_DENIED,
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        serializer = UsernameAvailabilitySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"available": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        username = serializer.validated_data["username"]
        qs = User.objects.filter(username__iexact=username)
        if request.user.is_authenticated:
            qs = qs.exclude(pk=request.user.pk)
        available = not qs.exists()
        return Response({"username": username, "available": available})


def _run_credential_gate(request, *, serializer):
    """Shared lockout + validate for session login and JWT token obtain.

    Returns ``(serializer, None)`` on success, or ``(None, error_response)`` on failure.
    """
    identifier = (request.data.get("username") or "").strip()
    client_ip = client_ip_from_request(request)

    if identifier and is_login_locked(client_ip=client_ip, identifier=identifier):
        return None, error_response(
            request,
            message="Too many failed sign-in attempts. Please try again later.",
            code=ErrorCode.THROTTLED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    try:
        serializer.is_valid(raise_exception=True)
    except AuthenticationFailed as exc:
        if identifier:
            register_failed_login(client_ip=client_ip, identifier=identifier)
        return None, error_response(
            request,
            message=stringify_detail(exc.detail) or "Invalid username/email or password.",
            code=ErrorCode.AUTHENTICATION_FAILED,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    clear_failed_logins(client_ip=client_ip, identifier=identifier)
    return serializer, None


class LoginView(APIView):
    """Browser sign-in: Django session only (no JWT in the response body)."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthLoginThrottle]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = SessionLoginSerializer(data=request.data, context={"request": request})
        serializer, error = _run_credential_gate(request, serializer=serializer)
        if error is not None:
            return error
        django_login(request, serializer.user)
        return Response({"user": UserSerializer(serializer.user).data}, status=status.HTTP_200_OK)


class ThrottledTokenObtainPairView(APIView):
    """JWT access/refresh for API clients (not used by the first-party UI)."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthLoginThrottle]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = TokenObtainPairWithUserSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer, error = _run_credential_gate(request, serializer=serializer)
        if error is not None:
            return error
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class ThrottledTokenRefreshView(TokenRefreshView):
    """JWT refresh with abuse throttling (API clients)."""

    throttle_classes = [AuthRefreshThrottle]


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        blacklist_user_refresh_tokens(request.user)
        django_logout(request)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ProfileUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(instance).data)


class AvatarView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if user.avatar:
            user.avatar.delete(save=False)
        user.avatar = serializer.validated_data["avatar"]
        user.save(update_fields=["avatar"])
        return Response(UserSerializer(user).data)

    def delete(self, request):
        user = request.user
        if user.avatar:
            user.avatar.delete(save=False)
            user.avatar = None
            user.save(update_fields=["avatar"])
        return Response(UserSerializer(user).data)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        update_session_auth_hash(request, user)
        blacklist_user_refresh_tokens(user)
        return Response({"detail": "Password updated successfully."})


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only user directory for share pickers (username / display only)."""

    queryset = User.objects.all().order_by("username")
    serializer_class = UserSummarySerializer
    permission_classes = [permissions.IsAuthenticated]
    search_param = "search"

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get(self.search_param)
        if search:
            qs = qs.filter(username__icontains=search)
        return qs.exclude(id=self.request.user.id)


class RoleViewSet(viewsets.ModelViewSet):
    """CRUD for roles. Restricted to staff / users with role-management permission."""

    queryset = Role.objects.all().prefetch_related("permissions", "users")
    serializer_class = RoleSerializer
    permission_classes = [CanManageRoles]
