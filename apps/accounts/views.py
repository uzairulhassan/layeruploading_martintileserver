from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from rest_framework import generics, permissions, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, User
from .permissions import CanManageRoles
from .serializers import (
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    OnetimeRegisterSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    RoleSerializer,
    TokenObtainPairWithUserSerializer,
    UsernameAvailabilitySerializer,
    UserSerializer,
    UserSummarySerializer,
)


class BaseRegisterView(generics.CreateAPIView):
    """Shared create flow: validate → save. User must sign in afterwards."""

    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]

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
    """Public sign-up. New users are assigned the ``User`` role."""

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
    """Live username availability check for the sign-up / onetime / account forms."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
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
        serializer.save()
        django_login(request, request.user)
        return Response({"detail": "Password updated successfully."})


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
