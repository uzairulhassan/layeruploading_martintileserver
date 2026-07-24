from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("login/", views.LoginPageView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("layers/", views.LayerListPageView.as_view(), name="layer_list"),
    path("maps/", views.MapListPageView.as_view(), name="map_list"),
    path("maps/new/", views.MapBuilderPageView.as_view(), name="map_new"),
    path("maps/<uuid:map_id>/", views.MapBuilderPageView.as_view(), name="map_builder"),
]
