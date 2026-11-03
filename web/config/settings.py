"""Configuración local de Django para el sitio de preferencias."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Esta clave permite arrancar el proyecto en local. Define DJANGO_SECRET_KEY
# para usar una clave propia y no reutilices este valor fuera de desarrollo.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-local-development-only-change-before-deployment",
)

# El sitio es exclusivamente local: runserver se documenta ligado a 127.0.0.1.
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts.apps.AccountsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# La base web es independiente de la base SQLite de la CLI (data/tasks.db).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "TEST": {"NAME": ":memory:"},
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "news"
LOGOUT_REDIRECT_URL = "login"

EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
SMTP_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
SMTP_SELECTED = EMAIL_BACKEND == SMTP_EMAIL_BACKEND
EMAIL_HOST = os.environ.get(
    "EMAIL_HOST",
    "smtp.gmail.com" if SMTP_SELECTED else "",
)
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get(
    "EMAIL_HOST_USER",
    os.environ.get("GMAIL_ADDRESS", ""),
)
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD") or os.environ.get(
    "GMAIL_APP_PASSWORD",
    "",
)
EMAIL_USE_TLS = os.environ.get(
    "EMAIL_USE_TLS",
    "true" if SMTP_SELECTED else "false",
).lower() in {
    "1",
    "true",
    "yes",
}
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "webmaster@localhost",
)
EMAIL_VERIFICATION_BASE_URL = os.environ.get(
    "EMAIL_VERIFICATION_BASE_URL",
    "http://localhost:8000",
)

if SMTP_SELECTED:
    if not EMAIL_HOST_USER:
        raise ImproperlyConfigured(
            "Configura GMAIL_ADDRESS o EMAIL_HOST_USER para habilitar "
            "el backend SMTP de Django."
        )
    if not EMAIL_HOST_PASSWORD:
        from app.email_sender import (
            EmailConfigurationError,
            EmailCredentialStoreError,
            get_app_password_non_interactive,
        )

        try:
            EMAIL_HOST_PASSWORD = get_app_password_non_interactive(EMAIL_HOST_USER)
        except EmailConfigurationError as error:
            raise ImproperlyConfigured(
                "No se encontró la contraseña de aplicación de Gmail. "
                "Configura GMAIL_APP_PASSWORD o guárdala con "
                "`python -m app email-config`."
            ) from error
        except EmailCredentialStoreError as error:
            raise ImproperlyConfigured(
                "No se pudo acceder a la credencial Gmail de Windows. "
                "Configura GMAIL_APP_PASSWORD o revisa el Administrador de "
                "credenciales y ejecuta `python -m app email-config`."
            ) from error
