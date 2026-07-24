from django.conf import settings


def frontend_settings(request):
    return {
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,
        "MARTIN_TILE_SERVER_URL": settings.MARTIN_TILE_SERVER_URL,
    }
