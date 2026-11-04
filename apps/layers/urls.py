from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LayerGroupViewSet, LayerViewSet

router = DefaultRouter()
router.register("", LayerViewSet, basename="layer")

group_router = DefaultRouter()
group_router.register("", LayerGroupViewSet, basename="layer_group")

app_name = "layers_api"

urlpatterns = [
    path("", include(router.urls)),
]

# Mounted at /api/layer-groups/ in config/urls.py.
group_urlpatterns = [
    path("", include(group_router.urls)),
]
