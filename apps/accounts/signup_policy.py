"""Public sign-up gate (env-controlled). Onetime bootstrap is separate."""
from django.conf import settings

PUBLIC_SIGNUP_CLOSED_MESSAGE = (
    "Public sign-ups are currently closed. "
    "We are not accepting new public accounts right now."
)


def public_signup_allowed() -> bool:
    return bool(settings.ALLOW_PUBLIC_SIGNUP)
