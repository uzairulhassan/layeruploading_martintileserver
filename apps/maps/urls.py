from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MapProjectViewSet

router = DefaultRouter()
router.register("", MapProjectViewSet, basename="map")

app_name = "maps_api"

urlpatterns = [
    path("", include(router.urls)),
]
