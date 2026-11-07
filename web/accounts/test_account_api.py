"""Tests for Angular registration, email verification, and preferences APIs."""

import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_verification import send_verification_email
from .models import Preferences

User = get_user_model()
PASSWORD = "Api-test-passphrase!2026"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
    ANGULAR_FRONTEND_BASE_URL="https://frontend.example.test",
)
class AngularAccountApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get(reverse("api_csrf"))
        self.csrf_token = self.client.cookies["csrftoken"].value

    def post_json(self, url_name, payload, client=None, csrf=True):
        client = client or self.client
        headers = {}
        if csrf:
            headers["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
        return client.post(
            reverse(url_name),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def registration_payload(self, **overrides):
        payload = {
            "username": "api-new-user",
            "email": "new-user@example.test",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        payload.update(overrides)
        return payload

    def test_registration_creates_default_preferences_and_angular_link(self):
        response = self.post_json("api_register", self.registration_payload())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["email_status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
        user = User.objects.get(username="api-new-user")
        self.assertIsNone(user.email_verified_at)
        self.assertFalse(user.preferences.newsletter_enabled)
        self.assertEqual(user.preferences.newsletter_topics, [])
        self.assertIn(
            "https://frontend.example.test/verificar-email?token=",
            mail.outbox[0].body,
        )

    def test_registration_reports_invalid_and_duplicate_fields(self):
        invalid = self.post_json(
            "api_register",
            self.registration_payload(
                email="no-es-correo",
                password1="password",
                password2="otra",
            ),
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("email", invalid.json()["field_errors"])
        self.assertIn("password2", invalid.json()["field_errors"])
        self.assertFalse(User.objects.exists())

        weak_password = self.post_json(
            "api_register",
            self.registration_payload(
                username="weak-api-user",
                email="weak@example.test",
                password1="password",
                password2="password",
            ),
        )
        self.assertEqual(weak_password.status_code, 400)
        self.assertIn("password2", weak_password.json()["field_errors"])
        self.assertFalse(User.objects.exists())

        User.objects.create_user(
            username="existing-api-user",
            email="existing@example.test",
            password=PASSWORD,
        )
        duplicate_username = self.post_json(
            "api_register",
            self.registration_payload(username="existing-api-user"),
        )
        duplicate_email = self.post_json(
            "api_register",
            self.registration_payload(
                username="another-api-user",
                email="EXISTING@example.test",
            ),
        )

        self.assertEqual(duplicate_username.status_code, 400)
        self.assertIn("username", duplicate_username.json()["field_errors"])
        self.assertEqual(duplicate_email.status_code, 400)
        self.assertIn("email", duplicate_email.json()["field_errors"])
        self.assertEqual(User.objects.count(), 1)

    def test_registration_and_verification_writes_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        registration = self.post_json(
            "api_register",
            self.registration_payload(),
            client=client,
            csrf=False,
        )
        self.assertEqual(registration.status_code, 403)
        self.assertFalse(User.objects.exists())

        client.get(reverse("api_csrf"))
        response = self.post_json(
            "api_register",
            self.registration_payload(),
            client=client,
        )
        user = User.objects.get(username="api-new-user")
        token = parse_qs(urlsplit(mail.outbox[0].body.splitlines()[2]).query)[
            "token"
        ][0]
        verification = client.post(
            reverse("api_confirm_email"),
            data=json.dumps({"token": token}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(verification.status_code, 403)
        user.refresh_from_db()
        self.assertIsNone(user.email_verified_at)

    def test_verification_get_is_non_mutating_and_post_confirms_signed_token(self):
        user = User.objects.create_user(
            username="verify-api-user",
            email="verify-api@example.test",
            password=PASSWORD,
        )
        send_verification_email(
            user,
            frontend_base_url="https://frontend.example.test",
        )
        token = parse_qs(urlsplit(mail.outbox[0].body.splitlines()[2]).query)[
            "token"
        ][0]

        preview = self.client.get(
            reverse("api_verify_email"),
            {"token": token},
        )
        user.refresh_from_db()
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["state"], "confirm")
        self.assertIsNone(user.email_verified_at)

        confirmed = self.post_json("api_confirm_email", {"token": token})
        user.refresh_from_db()
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["state"], "verified")
        self.assertIsNotNone(user.email_verified_at)

        repeated = self.post_json("api_confirm_email", {"token": token})
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["state"], "already_verified")

    def test_invalid_or_expired_verification_token_is_rejected(self):
        invalid = self.client.get(
            reverse("api_verify_email"),
            {"token": "altered-or-missing"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["state"], "invalid")

        user = User.objects.create_user(
            username="expired-api-user",
            email="expired-api@example.test",
            password=PASSWORD,
        )
        send_verification_email(user)
        token = parse_qs(urlsplit(mail.outbox[-1].body.splitlines()[2]).query)[
            "token"
        ][0]
        with patch("accounts.email_verification.TOKEN_MAX_AGE", -1):
            expired = self.client.get(
                reverse("api_verify_email"),
                {"token": token},
            )
        self.assertEqual(expired.status_code, 400)
        self.assertEqual(expired.json()["state"], "invalid")

    def test_unverified_user_can_still_log_in(self):
        user = User.objects.create_user(
            username="unverified-api-user",
            email="unverified@example.test",
            password=PASSWORD,
        )

        response = self.post_json(
            "api_login",
            {"username": user.username, "password": PASSWORD},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])

    def test_resend_verification_requires_session_and_obeys_cooldown(self):
        anonymous = self.client.post(
            reverse("api_resend_verification"),
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(anonymous.status_code, 401)

        user = User.objects.create_user(
            username="resend-api-user",
            email="resend-api@example.test",
            password=PASSWORD,
        )
        self.client.force_login(user)
        sent = self.client.post(
            reverse("api_resend_verification"),
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        throttled = self.client.post(
            reverse("api_resend_verification"),
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(sent.status_code, 200)
        self.assertEqual(sent.json()["status"], "sent")
        self.assertEqual(throttled.status_code, 429)
        self.assertEqual(throttled.json()["status"], "throttled")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            "https://frontend.example.test/verificar-email?token=",
            mail.outbox[0].body,
        )
        user.refresh_from_db()
        self.assertIsNotNone(user.verification_email_sent_at)

        User.objects.filter(pk=user.pk).update(
            verification_email_sent_at=timezone.now()
            - timedelta(minutes=5, seconds=1)
        )
        sent_again = self.client.post(
            reverse("api_resend_verification"),
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(sent_again.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)

    def test_preferences_are_private_and_can_be_updated(self):
        first = User.objects.create_user(
            username="preferences-owner",
            email="owner@example.test",
            password=PASSWORD,
        )
        second = User.objects.create_user(
            username="other-preferences-owner",
            email="other@example.test",
            password=PASSWORD,
        )
        first_preferences = Preferences.objects.create(
            user=first,
            newsletter_topics=["economy"],
        )
        second_preferences = Preferences.objects.create(
            user=second,
            newsletter_topics=["science"],
        )

        anonymous = self.client.get(reverse("api_preferences"))
        self.assertEqual(anonymous.status_code, 401)

        self.client.force_login(first)
        own_data = self.client.get(reverse("api_preferences"))
        self.assertEqual(own_data.status_code, 200)
        self.assertEqual(own_data.json()["email"], first.email)
        self.assertEqual(
            own_data.json()["preferences"]["newsletter_topics"],
            ["economy"],
        )
        self.assertNotIn(second.email, own_data.content.decode())

        updated = self.post_json(
            "api_save_preferences",
            {
                "user_id": second.pk,
                "newsletter_topics": ["technology", "ai"],
                "newsletter_enabled": True,
                "newsletter_time": "08:15",
                "timezone_name": "Europe/Paris",
                "alerts_enabled": True,
                "alert_topics": ["science"],
                "daily_alert_limit": 10,
            },
        )

        self.assertEqual(updated.status_code, 200)
        first_preferences.refresh_from_db()
        second_preferences.refresh_from_db()
        self.assertEqual(
            first_preferences.newsletter_topics,
            ["technology", "ai"],
        )
        self.assertTrue(first_preferences.newsletter_enabled)
        self.assertEqual(first_preferences.newsletter_time.strftime("%H:%M"), "08:15")
        self.assertEqual(first_preferences.timezone_name, "Europe/Paris")
        self.assertTrue(first_preferences.alerts_enabled)
        self.assertEqual(first_preferences.alert_topics, ["science"])
        self.assertEqual(first_preferences.daily_alert_limit, 10)
        self.assertEqual(second_preferences.newsletter_topics, ["science"])

    def test_preferences_validation_and_writes_require_csrf(self):
        user = User.objects.create_user(
            username="validation-preferences",
            password=PASSWORD,
        )
        self.client.force_login(user)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        csrf_client.get(reverse("api_csrf"))

        bad_csrf = csrf_client.post(
            reverse("api_save_preferences"),
            data=json.dumps(
                {
                    "newsletter_topics": [],
                    "newsletter_enabled": False,
                    "newsletter_time": "09:00",
                    "timezone_name": "Invalid/Zone",
                    "alerts_enabled": False,
                    "alert_topics": ["not-a-topic"],
                    "daily_alert_limit": 11,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(bad_csrf.status_code, 403)

        invalid = self.post_json(
            "api_save_preferences",
            {
                "newsletter_topics": [],
                "newsletter_enabled": False,
                "newsletter_time": "09:00",
                "timezone_name": "Invalid/Zone",
                "alerts_enabled": False,
                "alert_topics": ["not-a-topic"],
                "daily_alert_limit": 11,
            },
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("timezone_name", invalid.json()["field_errors"])
        self.assertIn("alert_topics", invalid.json()["field_errors"])
        self.assertIn("daily_alert_limit", invalid.json()["field_errors"])
        self.assertFalse(Preferences.objects.filter(user=user).exists())
