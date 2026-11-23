"""
Django settings for the Layer Uploading & Mapping platform.
"""
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

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
    "apps.accounts.apps.AccountsConfig",
    "apps.layers",
    "apps.maps",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.request_id.RequestIDMiddleware",
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
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "apps.accounts.password_validation.ComplexityPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# Entire GeoLayers product uses Saudi Arabia (Riyadh) time — no DST.
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
# Never gzip already-compressed media — Range requests for <video> break intermittently.
WHITENOISE_SKIP_COMPRESS_EXTENSIONS = (
    "jpg", "jpeg", "png", "gif", "webp", "zip", "gz", "tgz", "bz2", "tbz",
    "xz", "br", "swf", "flv", "woff", "woff2",
    "mp4", "webm", "mp3", "ogg", "mov",
)

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "core:login"
LOGOUT_REDIRECT_URL = "core:login"

# Session is the first-party browser credential (HttpOnly). JWT is for API clients.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_HTTPONLY = False  # readable by Auth.apiFetch
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", default="Lax")

# USE_TLS=True when HTTPS terminates in front of :8081 (Secure cookies + HSTS).
USE_TLS = env.bool("USE_TLS", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=USE_TLS)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=USE_TLS)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=USE_TLS)

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "same-origin"
    if USE_TLS:
        SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
        SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
        SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

# Shared by auth throttles and login lockout (file cache works across gunicorn threads).
_CACHE_DIR = BASE_DIR / ".cache" / "django"
try:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    _CACHE_DIR = Path("/tmp/geolayers-django-cache")
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(_CACHE_DIR),
        "TIMEOUT": 300,
    }
}

AUTH_LOGIN_LOCKOUT_ATTEMPTS = env.int("AUTH_LOGIN_LOCKOUT_ATTEMPTS", default=5)
AUTH_LOGIN_LOCKOUT_SECONDS = env.int("AUTH_LOGIN_LOCKOUT_SECONDS", default=900)

# Public /signup/ + POST /api/auth/register/. False = closed (default). Onetime bootstrap is separate.
ALLOW_PUBLIC_SIGNUP = env.bool("ALLOW_PUBLIC_SIGNUP", default=False)

# ---------------------------------------------------------------------------
# Django REST Framework / SimpleJWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "apps.core.exception_handler.custom_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": env("THROTTLE_AUTH_LOGIN", default="10/min"),
        "auth_register": env("THROTTLE_AUTH_REGISTER", default="5/min"),
        "auth_refresh": env("THROTTLE_AUTH_REFRESH", default="30/min"),
        "auth_username": env("THROTTLE_AUTH_USERNAME", default="30/min"),
    },
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
}

# ---------------------------------------------------------------------------
# Logging (request_id appears when present on the record)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "apps.core.logging_filters.RequestIDFilter",
        },
    },
    "formatters": {
        "standard": {
            "format": "%(levelname)s %(asctime)s [%(name)s] [request_id=%(request_id)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": env("LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
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
if not DEBUG and not TILE_AUTH_SHARED_SECRET:
    raise ImproperlyConfigured(
        "TILE_AUTH_SHARED_SECRET is required when DEBUG=False "
        "(must match GEOLAYERS_TILE_AUTH_SHARED_SECRET in geo_infra)."
    )

# Share links remain capability URLs; cap finite expiries (null = never expires, still revocable).
SHARE_LINK_MAX_TTL_DAYS = env.int("SHARE_LINK_MAX_TTL_DAYS", default=365)

OGR2OGR_PATH = env("OGR2OGR_PATH", default="ogr2ogr")

# Shapefiles are uploaded as a single .zip containing .shp/.shx/.dbf/.prj (+ optional .cpg/.qpj)
MAX_SHAPEFILE_UPLOAD_SIZE = env.int("MAX_SHAPEFILE_UPLOAD_SIZE", default=200 * 1024 * 1024)  # 200MB
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_SHAPEFILE_UPLOAD_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = min(MAX_SHAPEFILE_UPLOAD_SIZE, 10 * 1024 * 1024)
LAYER_TABLE_SCHEMA = env("LAYER_TABLE_SCHEMA", default="layers_data")
