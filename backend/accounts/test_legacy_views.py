"""Compatibility and side-effect tests for retired Django page URLs."""

import json
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_verification import send_verification_email
from .models import NewsletterSendAttempt, Preferences

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
    ANGULAR_FRONTEND_BASE_URL="https://frontend.example.test/app/",
)
class LegacyPageRedirectTests(TestCase):
    def test_legacy_screen_gets_temporarily_redirect_to_angular(self):
        routes = {
            "/": "/app/noticias",
            "/noticias/": "/app/noticias",
            "/registro/": "/app/registro",
            "/login/": "/app/login",
            "/preferencias/": "/app/preferencias",
            "/boletin/": "/app/boletin",
        }
        for legacy_path, frontend_path in routes.items():
            with self.subTest(path=legacy_path):
                response = self.client.get(legacy_path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    response["Location"],
                    f"https://frontend.example.test{frontend_path}",
                )

    def test_old_verification_link_preserves_encoded_token_without_consuming_it(self):
        user = User.objects.create_user(
            username="legacy-verification-user",
            email="legacy-verification@example.test",
            password="Legacy-test-passphrase!2026",
        )
        self.assertEqual(send_verification_email(user), "sent")
        token = parse_qs(
            urlsplit(mail.outbox[0].body.splitlines()[2]).query
        )["token"][0]

        response = self.client.get(
            reverse("verify_email"),
            {"token": token},
        )

        self.assertEqual(response.status_code, 302)
        location = urlsplit(response["Location"])
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}",
            "https://frontend.example.test/app/verificar-email",
        )
        self.assertEqual(parse_qs(location.query)["token"], [token])
        self.assertIn("%3A", response["Location"])
        user.refresh_from_db()
        self.assertIsNone(user.email_verified_at)

    def test_legacy_page_posts_are_rejected_without_account_or_preference_changes(self):
        user = User.objects.create_user(
            username="legacy-post-user",
            email="legacy-post@example.test",
            password="Legacy-test-passphrase!2026",
        )
        preferences = Preferences.objects.create(
            user=user,
            newsletter_topics=["economy"],
        )
        self.client.force_login(user)

        registration = self.client.post(
            reverse("register"),
            {
                "username": "should-not-exist",
                "email": "new@example.test",
                "password1": "Legacy-test-passphrase!2026",
                "password2": "Legacy-test-passphrase!2026",
            },
        )
        login = self.client.post(
            reverse("login"),
            {"username": "legacy-post-user", "password": "wrong-password"},
        )
        preference_update = self.client.post(
            reverse("preferences"),
            {"newsletter_topics": ["science"], "newsletter_enabled": "on"},
        )

        self.assertEqual(registration.status_code, 405)
        self.assertEqual(login.status_code, 405)
        self.assertEqual(preference_update.status_code, 405)
        self.assertFalse(User.objects.filter(username="should-not-exist").exists())
        preferences.refresh_from_db()
        self.assertEqual(preferences.newsletter_topics, ["economy"])
        self.assertEqual(mail.outbox, [])

    def test_retired_action_posts_do_not_send_or_change_session(self):
        user = User.objects.create_user(
            username="legacy-action-user",
            email="legacy-action@example.test",
            password="Legacy-test-passphrase!2026",
            email_verified_at=timezone.now(),
        )
        self.client.force_login(user)
        session_key = self.client.session.session_key
        routes = (
            "logout",
            "send_manual_newsletter",
            "resend_verification_email",
        )

        for route_name in routes:
            with self.subTest(route=route_name):
                response = self.client.post(reverse(route_name), data={})
                self.assertEqual(response.status_code, 410)

        self.assertEqual(self.client.session.session_key, session_key)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(NewsletterSendAttempt.objects.exists())
        user.refresh_from_db()
        self.assertIsNone(user.verification_email_sent_at)

    def test_legacy_verification_post_cannot_consume_token(self):
        user = User.objects.create_user(
            username="legacy-post-verification",
            email="legacy-post-verification@example.test",
            password="Legacy-test-passphrase!2026",
        )
        send_verification_email(user)
        token = parse_qs(
            urlsplit(mail.outbox[0].body.splitlines()[2]).query
        )["token"][0]

        response = self.client.post(reverse("verify_email"), {"token": token})

        self.assertEqual(response.status_code, 405)
        user.refresh_from_db()
        self.assertIsNone(user.email_verified_at)

    def test_api_authentication_responses_remain_json(self):
        login = self.client.post(
            reverse("api_login"),
            data=json.dumps({"username": "unknown", "password": "wrong"}),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 401)
        self.assertEqual(login.json()["detail"], "Nombre de usuario o contraseña incorrectos.")
