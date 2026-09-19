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
    RegisterSerializer,
    RoleSerializer,
    TokenObtainPairWithUserSerializer,
    UserSerializer,
    UserSummarySerializer,
)


class RegisterView(generics.CreateAPIView):
    """Public sign-up endpoint. New users start with no roles assigned."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    """Issues a JWT access/refresh pair AND establishes a Django session.

    The session lets server-rendered template pages (dashboard, map builder)
    know the user is signed in, while the JWT pair is used by the frontend
    JS for calls against the DRF API (with silent refresh on expiry).
    """

    serializer_class = TokenObtainPairWithUserSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            username = request.data.get("username")
            user = User.objects.filter(username=username).first()
            if user is not None:
                django_login(request, user)
        return response


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
