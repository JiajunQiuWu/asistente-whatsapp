"""URL patterns for the Angular JSON API."""

from django.urls import path

from .api_views import (
    api_confirm_email,
    api_login,
    api_logout,
    api_news,
    api_newsletter_history,
    api_newsletter_preview,
    api_send_manual_newsletter,
    api_preferences,
    api_register,
    api_resend_verification,
    api_verify_email,
    api_save_preferences,
    csrf_cookie,
    current_session,
)

urlpatterns = [
    path("csrf/", csrf_cookie, name="api_csrf"),
    path("session/", current_session, name="api_session"),
    path("login/", api_login, name="api_login"),
    path("logout/", api_logout, name="api_logout"),
    path("news/", api_news, name="api_news"),
    path("newsletter/", api_newsletter_preview, name="api_newsletter_preview"),
    path(
        "newsletter/send/",
        api_send_manual_newsletter,
        name="api_send_manual_newsletter",
    ),
    path(
        "newsletter/history/",
        api_newsletter_history,
        name="api_newsletter_history",
    ),
    path("register/", api_register, name="api_register"),
    path("preferences/", api_preferences, name="api_preferences"),
    path(
        "preferences/save/",
        api_save_preferences,
        name="api_save_preferences",
    ),
    path(
        "preferences/resend-verification/",
        api_resend_verification,
        name="api_resend_verification",
    ),
    path("verify-email/", api_verify_email, name="api_verify_email"),
    path(
        "verify-email/confirm/",
        api_confirm_email,
        name="api_confirm_email",
    ),
]
