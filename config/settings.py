"""
Django settings for the Layer Uploading & Mapping platform.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
# Behind the shared Nginx (geo-infra), which always sets X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# GeoLayers (:8081) and GeoTrak (:8000) share a host, and cookies ignore ports, so each
# app needs its own session cookie name or logging into one logs you out of the other.
SESSION_COOKIE_NAME = env("SESSION_COOKIE_NAME", default="geolayers_sessionid")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    # Local apps
    "apps.accounts",
    "apps.layers",
    "apps.maps",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.frontend_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgis://geolayers_user:geolayers_password@localhost:5432/geolayers",
        engine="django.contrib.gis.db.backends.postgis",
    )
}

# Reuse DB connections across requests (each map tile makes one auth call).
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:login"

# Production hardening (safe defaults; HTTPS flags stay off until TLS is fronted)
if not DEBUG:
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
    CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "same-origin"

# ---------------------------------------------------------------------------
# Django REST Framework / SimpleJWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("ACCESS_TOKEN_LIFETIME_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# Application-specific settings
# ---------------------------------------------------------------------------
MAPBOX_ACCESS_TOKEN = env("MAPBOX_ACCESS_TOKEN", default="")
# Martin is shared with GeoTrak and sits behind the shared Nginx (../geo-infra).
# Browser-facing tiles base. A path ("/tiles") is made absolute per request; a full URL is used as-is.
TILES_PUBLIC_URL = env("TILES_PUBLIC_URL", default="/tiles")
# Single Martin function source that serves every layer via ?layer=<table> (migration layers.0003).
MARTIN_LAYER_FUNCTION = env("MARTIN_LAYER_FUNCTION", default="geolayers_tile")
# Django -> Martin inside the geo_shared Docker network (used by the share-link tile proxy).
MARTIN_INTERNAL_URL = env("MARTIN_INTERNAL_URL", default="http://martin:3000")
# Nginx sends this in X-Tile-Auth-Secret on every tile auth subrequest.
# It must match GEOLAYERS_TILE_AUTH_SHARED_SECRET in ../geo-infra/.env.
TILE_AUTH_SHARED_SECRET = env("TILE_AUTH_SHARED_SECRET", default="")
OGR2OGR_PATH = env("OGR2OGR_PATH", default="ogr2ogr")

# Shapefiles are uploaded as a single .zip containing .shp/.shx/.dbf/.prj (+ optional .cpg/.qpj)
MAX_SHAPEFILE_UPLOAD_SIZE = env.int("MAX_SHAPEFILE_UPLOAD_SIZE", default=200 * 1024 * 1024)  # 200MB
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_SHAPEFILE_UPLOAD_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = min(MAX_SHAPEFILE_UPLOAD_SIZE, 10 * 1024 * 1024)
LAYER_TABLE_SCHEMA = env("LAYER_TABLE_SCHEMA", default="layers_data")
