from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from apps.layers.tile_auth import validate_tile_request
from apps.layers.tile_proxy import serve_shared_tile

urlpatterns = [
    path("admin/", admin.site.urls),
    # Behind Nginx this path is served by Nginx + Martin directly; the view is the no-Nginx fallback.
    path("x/<str:token>/<int:z>/<int:x>/<int:y>.pbf", serve_shared_tile, name="shared_tile"),
    # Nginx auth_request target (blocked publicly by Nginx; see ../geo-infra).
    path("tiles-auth/validate/", validate_tile_request, name="tile_auth_validate"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/layers/", include("apps.layers.urls")),
    path("api/maps/", include("apps.maps.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Serve uploaded media in production when no separate reverse-proxy is used.
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
