"""Scoped rate limits for authentication endpoints."""
from rest_framework.throttling import AnonRateThrottle


class AuthLoginThrottle(AnonRateThrottle):
    scope = "auth_login"


class AuthRegisterThrottle(AnonRateThrottle):
    scope = "auth_register"


class AuthRefreshThrottle(AnonRateThrottle):
    scope = "auth_refresh"


class AuthUsernameThrottle(AnonRateThrottle):
    scope = "auth_username"
