from django.conf import settings
from django.middleware.csrf import get_token

from apps.accounts.signup_policy import PUBLIC_SIGNUP_CLOSED_MESSAGE, public_signup_allowed


def frontend_settings(request):
    get_token(request)  # ensure csrftoken cookie for Auth.apiFetch (session + CSRF)
    return {
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,
        "ALLOW_PUBLIC_SIGNUP": public_signup_allowed(),
        "PUBLIC_SIGNUP_CLOSED_MESSAGE": PUBLIC_SIGNUP_CLOSED_MESSAGE,
        "TIME_ZONE": settings.TIME_ZONE,
        "SHARE_LINK_MAX_TTL_DAYS": int(getattr(settings, "SHARE_LINK_MAX_TTL_DAYS", 365) or 365),
    }
