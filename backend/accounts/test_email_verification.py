"""Tests for verification-email delivery and account email invariants."""

from smtplib import SMTPException
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from .email_verification import send_verification_email, verify_email_token

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
    ANGULAR_FRONTEND_BASE_URL="https://frontend.example.test",
)
class VerificationEmailServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="verification-reader",
            email="verification@example.test",
            password="Verification-test-passphrase!2026",
        )

    def test_sends_signed_link_to_configured_angular_frontend(self):
        self.assertEqual(
            send_verification_email(
                self.user,
                frontend_base_url=settings.ANGULAR_FRONTEND_BASE_URL,
            ),
            "sent",
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        verification_url = mail.outbox[0].body.splitlines()[2]
        parsed_url = urlsplit(verification_url)
        self.assertEqual(
            f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}",
            "https://frontend.example.test/verificar-email",
        )
        self.assertTrue(parse_qs(parsed_url.query)["token"][0])
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.verification_email_sent_at)

    def test_failed_or_rejected_send_releases_the_resend_cooldown(self):
        with patch(
            "accounts.email_verification.send_mail",
            side_effect=SMTPException("simulated failure"),
        ):
            failed = send_verification_email(self.user)
        self.assertEqual(failed, "failed")
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verification_email_sent_at)

        with patch("accounts.email_verification.send_mail", return_value=0):
            rejected = send_verification_email(self.user)
        self.assertEqual(rejected, "failed")
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verification_email_sent_at)

        self.assertEqual(send_verification_email(self.user), "sent")
        self.assertEqual(len(mail.outbox), 1)

    def test_console_backend_is_reported_as_simulation(self):
        with (
            override_settings(
                EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
            ),
            patch("accounts.email_verification.send_mail", return_value=1),
        ):
            status = send_verification_email(self.user)

        self.assertEqual(status, "simulated")
        self.assertEqual(mail.outbox, [])

    def test_verified_and_missing_email_accounts_do_not_send(self):
        self.user.email = ""
        self.user.save(update_fields={"email"})
        self.assertEqual(send_verification_email(self.user), "missing_email")
        self.assertEqual(mail.outbox, [])

        self.user.email = "verification@example.test"
        User.objects.filter(pk=self.user.pk).update(
            email=self.user.email,
            email_verified_at=timezone.now(),
        )
        self.assertEqual(send_verification_email(self.user), "already_verified")
        self.assertEqual(mail.outbox, [])

    def test_email_change_invalidates_previous_verification(self):
        send_verification_email(
            self.user,
            frontend_base_url=settings.ANGULAR_FRONTEND_BASE_URL,
        )
        token = parse_qs(
            urlsplit(mail.outbox[0].body.splitlines()[2]).query
        )["token"][0]
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields={"email_verified_at"})

        self.user.email = "changed@example.test"
        self.user.save(update_fields={"email"})
        self.user.refresh_from_db()

        self.assertIsNone(self.user.email_verified_at)
        self.assertEqual(verify_email_token(token, confirm=True), (None, "invalid"))

    def test_case_insensitive_email_uniqueness_is_enforced_by_database(self):
        User.objects.create_user(
            username="existing-reader",
            email="Same.Address@example.test",
            password="Verification-test-passphrase!2026",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="database-duplicate",
                    email="SAME.ADDRESS@Example.test",
                    password="Verification-test-passphrase!2026",
                )
