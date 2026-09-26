from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from django.urls import path, include

from .views import (
    AvatarView,
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    OnetimeRegisterView,
    RegisterView,
    RoleViewSet,
    UsernameAvailabilityView,
    UserViewSet,
)

router = DefaultRouter()
router.register("roles", RoleViewSet, basename="role")
router.register("users", UserViewSet, basename="user")

app_name = "accounts_api"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("onetime/", OnetimeRegisterView.as_view(), name="onetime"),
    path("username-available/", UsernameAvailabilityView.as_view(), name="username_available"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/", AvatarView.as_view(), name="me_avatar"),
    path("me/password/", ChangePasswordView.as_view(), name="me_password"),
    path("", include(router.urls)),
]
