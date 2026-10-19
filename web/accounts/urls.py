"""Rutas web para registro, autenticación y preferencias."""

from django.urls import path

from .views import (
    UserLoginView,
    logout_view,
    newsletter_preview,
    preferences,
    register,
    resend_verification_email,
    verify_email,
)

urlpatterns = [
    path("", preferences, name="home"),
    path("registro/", register, name="register"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
    path("preferencias/", preferences, name="preferences"),
    path("boletin/", newsletter_preview, name="newsletter_preview"),
    path("verificar-email/", verify_email, name="verify_email"),
    path(
        "reenviar-verificacion/",
        resend_verification_email,
        name="resend_verification_email",
    ),
]
