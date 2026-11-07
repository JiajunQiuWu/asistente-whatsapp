"""Legacy page URLs retained as redirects to the Angular application."""

from django.urls import path

from .legacy_views import redirect_to_frontend, retired_legacy_action

urlpatterns = [
    path("", redirect_to_frontend, {"frontend_path": "noticias"}, name="home"),
    path(
        "noticias/",
        redirect_to_frontend,
        {"frontend_path": "noticias"},
        name="news",
    ),
    path(
        "registro/",
        redirect_to_frontend,
        {"frontend_path": "registro"},
        name="register",
    ),
    path(
        "login/",
        redirect_to_frontend,
        {"frontend_path": "login"},
        name="login",
    ),
    path("logout/", retired_legacy_action, name="logout"),
    path(
        "preferencias/",
        redirect_to_frontend,
        {"frontend_path": "preferencias"},
        name="preferences",
    ),
    path(
        "boletin/",
        redirect_to_frontend,
        {"frontend_path": "boletin"},
        name="newsletter_preview",
    ),
    path(
        "boletin/enviar/",
        retired_legacy_action,
        name="send_manual_newsletter",
    ),
    path(
        "verificar-email/",
        redirect_to_frontend,
        {"frontend_path": "verificar-email"},
        name="verify_email",
    ),
    path(
        "reenviar-verificacion/",
        retired_legacy_action,
        name="resend_verification_email",
    ),
]
