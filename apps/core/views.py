from django.contrib.auth import REDIRECT_FIELD_NAME, logout as django_logout
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import RedirectView, TemplateView, View

from apps.accounts.models import User
from apps.core.login_redirect import (
    GeoLayersLoginRequiredMixin,
    resolve_post_login_path,
    should_keep_next,
)


class LoginPageView(TemplateView):
    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["redirect_field_name"] = REDIRECT_FIELD_NAME
        return context

    def get(self, request, *args, **kwargs):
        raw_next = request.GET.get(REDIRECT_FIELD_NAME)

        if request.user.is_authenticated:
            return redirect(resolve_post_login_path(raw_next))

        if REDIRECT_FIELD_NAME in request.GET and not should_keep_next(raw_next):
            return redirect("core:login")

        return super().get(request, *args, **kwargs)


class SignupPageView(TemplateView):
    template_name = "registration/signup.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
        return super().get(request, *args, **kwargs)


class OnetimePageView(TemplateView):
    """Bootstrap page for registering the first Admin account.

    Once any user exists, the URL is closed and visitors are sent to login.
    """

    template_name = "registration/onetime.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
        if User.objects.exists():
            return redirect("core:login")
        return super().get(request, *args, **kwargs)


class LogoutView(View):
    """POST-only HTML logout fallback. UI uses ``POST /api/auth/logout/`` then ``/login/``."""

    http_method_names = ["post", "head", "options"]

    def post(self, request, *args, **kwargs):
        django_logout(request)
        return redirect("core:login")


class DashboardView(GeoLayersLoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"


class LayerListPageView(GeoLayersLoginRequiredMixin, TemplateView):
    template_name = "layers/layer_list.html"


class MapListPageView(GeoLayersLoginRequiredMixin, TemplateView):
    template_name = "maps/map_list.html"


class MapNewRedirectView(GeoLayersLoginRequiredMixin, RedirectView):
    """/maps/new/ opens the create-map modal on the Maps page."""

    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return f"{reverse('core:map_list')}?new=1"


class MapBuilderPageView(GeoLayersLoginRequiredMixin, TemplateView):
    template_name = "maps/map_builder.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["map_id"] = self.kwargs["map_id"]
        return context


class AccountPageView(GeoLayersLoginRequiredMixin, TemplateView):
    template_name = "accounts/account.html"


class SecurityPageView(GeoLayersLoginRequiredMixin, TemplateView):
    template_name = "accounts/security.html"
