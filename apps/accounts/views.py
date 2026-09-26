from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, User
from .permissions import CanManageRoles
from .serializers import (
    OnetimeRegisterSerializer,
    RegisterSerializer,
    RoleSerializer,
    TokenObtainPairWithUserSerializer,
    UsernameAvailabilitySerializer,
    UserSerializer,
    UserSummarySerializer,
)


def _issue_tokens_and_session(request, user):
    """Establish a Django session and return a JWT pair + user payload."""
    refresh = RefreshToken.for_user(user)
    django_login(request, user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
    }


class BaseRegisterView(generics.CreateAPIView):
    """Shared create flow: validate → save → issue session + JWT."""

    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(_issue_tokens_and_session(request, user), status=status.HTTP_201_CREATED)


class RegisterView(BaseRegisterView):
    """Public sign-up. New users are assigned the ``User`` role and signed in."""

    serializer_class = RegisterSerializer


class OnetimeRegisterView(BaseRegisterView):
    """One-shot bootstrap registration for the first Admin account."""

    serializer_class = OnetimeRegisterSerializer

    def create(self, request, *args, **kwargs):
        if User.objects.exists():
            return Response(
                {"detail": "Initial setup is already complete."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)


class UsernameAvailabilityView(APIView):
    """Live username availability check for the sign-up / onetime forms."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        serializer = UsernameAvailabilitySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"available": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        username = serializer.validated_data["username"]
        available = not User.objects.filter(username__iexact=username).exists()
        return Response({"username": username, "available": available})


class LoginView(TokenObtainPairView):
    """Issues a JWT access/refresh pair AND establishes a Django session.

    Accepts username or email in the ``username`` field.
    """

    serializer_class = TokenObtainPairWithUserSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        django_login(request, serializer.user)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass
        django_logout(request)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only user directory, primarily used to populate share pickers."""

    queryset = User.objects.all().order_by("username")
    serializer_class = UserSummarySerializer
    permission_classes = [permissions.IsAuthenticated]
    search_param = "search"

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get(self.search_param)
        if search:
            qs = qs.filter(username__icontains=search) | qs.filter(email__icontains=search)
        return qs.exclude(id=self.request.user.id)


class RoleViewSet(viewsets.ModelViewSet):
    """CRUD for roles. Restricted to staff / users with role-management permission."""

    queryset = Role.objects.all().prefetch_related("permissions", "users")
    serializer_class = RoleSerializer
    permission_classes = [CanManageRoles]
