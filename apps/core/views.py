from django.contrib.auth import logout as django_logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView, View


class LoginPageView(TemplateView):
    template_name = "registration/login.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
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


class MapBuilderPageView(LoginRequiredMixin, TemplateView):
    template_name = "maps/map_builder.html"
    login_url = "core:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["map_id"] = self.kwargs.get("map_id", "")
        return context
