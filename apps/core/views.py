from django.contrib.auth import logout as django_logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import RedirectView, TemplateView, View

from apps.accounts.models import User


class LoginPageView(TemplateView):
    template_name = "registration/login.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
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
    """Clears the Django session. The frontend JS calls the JWT logout API
    endpoint first (to blacklist the refresh token) and then hits this view.
    """

    def post(self, request, *args, **kwargs):
        django_logout(request)
        return redirect("core:login")

    def get(self, request, *args, **kwargs):
        django_logout(request)
        return redirect("core:login")


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"
    login_url = "core:login"


class LayerListPageView(LoginRequiredMixin, TemplateView):
    template_name = "layers/layer_list.html"
    login_url = "core:login"


class MapListPageView(LoginRequiredMixin, TemplateView):
    template_name = "maps/map_list.html"
    login_url = "core:login"


class MapNewRedirectView(LoginRequiredMixin, RedirectView):
    """/maps/new/ opens the create-map modal on the Maps page."""

    permanent = False
    login_url = "core:login"

    def get_redirect_url(self, *args, **kwargs):
        return f"{reverse('core:map_list')}?new=1"


class MapBuilderPageView(LoginRequiredMixin, TemplateView):
    template_name = "maps/map_builder.html"
    login_url = "core:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["map_id"] = self.kwargs["map_id"]
        return context
