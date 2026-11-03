"""Pruebas de registro y verificación de correo sin conexiones externas."""

from datetime import timedelta
from smtplib import SMTPException
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_verification import send_verification_email

User = get_user_model()
STRONG_PASSWORD = "L0cal-test-passphrase!2026"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
    EMAIL_VERIFICATION_BASE_URL="https://trusted.example.test",
)
class EmailRegistrationTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            "username": "new-reader",
            "email": "reader@example.test",
            "password1": STRONG_PASSWORD,
            "password2": STRONG_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_registration_requires_a_valid_email_and_sends_verification(self):
        missing_email = self.client.post(
            reverse("register"),
            self.registration_data(email=""),
        )
        invalid_email = self.client.post(
            reverse("register"),
            self.registration_data(email="not-an-email"),
        )

        self.assertEqual(missing_email.status_code, 200)
        self.assertIn("email", missing_email.context["form"].errors)
        self.assertEqual(invalid_email.status_code, 200)
        self.assertIn("email", invalid_email.context["form"].errors)
        self.assertFalse(User.objects.exists())
        self.assertEqual(mail.outbox, [])

        response = self.client.post(reverse("register"), self.registration_data())

        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        user = User.objects.get(username="new-reader")
        self.assertEqual(user.email, "reader@example.test")
        self.assertIsNone(user.email_verified_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertIn("https://trusted.example.test/verificar-email/", mail.outbox[0].body)
        login_page = self.client.get(reverse("login"))
        self.assertContains(login_page, "El backend de correo aceptó el mensaje")

    def test_duplicate_email_is_rejected_case_insensitively_by_form_and_database(self):
        User.objects.create_user(
            username="existing-reader",
            email="Same.Address@example.test",
            password=STRONG_PASSWORD,
        )
        response = self.client.post(
            reverse("register"),
            self.registration_data(email="same.address@EXAMPLE.test"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="database-duplicate",
                    email="SAME.ADDRESS@Example.test",
                    password=STRONG_PASSWORD,
                )

    def test_existing_accounts_remain_unverified_and_can_login_and_preview(self):
        user = User.objects.create_user(
            username="legacy-user",
            email="legacy@example.test",
            password=STRONG_PASSWORD,
        )
        self.assertIsNone(user.email_verified_at)
        self.client.force_login(user)

        with patch(
            "accounts.views.get_user_newsletter_preview",
            return_value=type(
                "Preview",
                (),
                {
                    "newsletter_enabled": False,
                    "generated_at": timezone.now(),
                    "timezone_name": "Europe/Madrid",
                    "warnings": [],
                    "has_selected_topics": False,
                    "articles": [],
                    "matched_source_count": 0,
                },
            )(),
        ):
            preview = self.client.get(reverse("newsletter_preview"))
        preferences = self.client.get(reverse("preferences"))

        self.assertEqual(preview.status_code, 200)
        self.assertContains(preferences, "Pendiente de verificación")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
    EMAIL_VERIFICATION_BASE_URL="https://trusted.example.test",
)
class EmailVerificationLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="verify-reader",
            email="verify@example.test",
            password=STRONG_PASSWORD,
        )
        self.assertEqual(send_verification_email(self.user), "sent")
        self.token = parse_qs(urlsplit(
            mail.outbox[-1].body.splitlines()[2]
        ).query)["token"][0]

    def test_get_only_displays_confirmation_and_post_verifies(self):
        url = reverse("verify_email")
        response = self.client.get(url, {"token": self.token})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirma tu dirección")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)

        verified = self.client.post(url, {"token": self.token})

        self.assertEqual(verified.status_code, 200)
        self.assertContains(verified, "Correo verificado")
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.email_verified_at)

    def test_expired_altered_and_already_used_links_cannot_verify_again(self):
        with patch("accounts.email_verification.TOKEN_MAX_AGE", -1):
            expired = self.client.get(
                reverse("verify_email"),
                {"token": self.token},
            )
        self.assertEqual(expired.status_code, 400)
        self.assertContains(expired, "Enlace no válido", status_code=400)

        altered = self.client.get(
            reverse("verify_email"),
            {"token": f"{self.token}altered"},
        )
        self.assertEqual(altered.status_code, 400)

        first_use = self.client.post(
            reverse("verify_email"),
            {"token": self.token},
        )
        self.assertContains(first_use, "Correo verificado")
        already_used = self.client.post(
            reverse("verify_email"),
            {"token": self.token},
        )
        self.assertContains(already_used, "Enlace ya utilizado")

    def test_changing_email_invalidates_previous_link_and_verification(self):
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields={"email_verified_at"})
        self.user.email = "changed@example.test"
        self.user.save(update_fields={"email"})

        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)
        self.assertEqual(
            self.client.post(
                reverse("verify_email"),
                {"token": self.token},
            ).status_code,
            400,
        )
        self.assertIsNone(self.user.email_verified_at)

    def test_link_only_verifies_the_signed_user_not_tampered_parameters(self):
        other_user = User.objects.create_user(
            username="other-reader",
            email="other@example.test",
            password=STRONG_PASSWORD,
        )
        self.client.force_login(other_user)

        response = self.client.post(
            reverse("verify_email"),
            {
                "token": self.token,
                "user_id": other_user.pk,
                "email": other_user.email,
            },
        )

        self.assertContains(response, "Correo verificado")
        self.user.refresh_from_db()
        other_user.refresh_from_db()
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertIsNone(other_user.email_verified_at)

    def test_verification_post_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(reverse("verify_email"), {"token": self.token})

        response = csrf_client.post(
            reverse("verify_email"),
            {"token": self.token},
        )

        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
    EMAIL_VERIFICATION_BASE_URL="https://trusted.example.test",
)
class VerificationResendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="resend-reader",
            email="resend@example.test",
            password=STRONG_PASSWORD,
        )
        self.client.force_login(self.user)

    def test_resend_is_post_only_persists_cooldown_and_throttles(self):
        self.assertIsNone(self.user.email_verified_at)
        preferences = self.client.get(reverse("preferences"))
        self.assertContains(preferences, "Reenviar verificación")
        self.assertContains(
            preferences,
            f'action="{reverse("resend_verification_email")}"',
        )
        self.assertContains(preferences, 'method="post"')
        self.assertContains(preferences, 'name="csrfmiddlewaretoken"')
        self.assertEqual(
            self.client.get(reverse("resend_verification_email")).status_code,
            405,
        )

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        csrf_client.get(reverse("preferences"))
        self.assertEqual(
            csrf_client.post(reverse("resend_verification_email")).status_code,
            403,
        )

        response = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(response, reverse("preferences"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.user.refresh_from_db()
        first_sent_at = self.user.verification_email_sent_at
        self.assertIsNotNone(first_sent_at)
        self.assertContains(
            self.client.get(reverse("preferences")),
            "El backend de correo aceptó el mensaje",
        )

        throttled = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(throttled, reverse("preferences"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(
            self.client.get(reverse("preferences")),
            "Debes esperar al menos 5 minutos",
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.verification_email_sent_at, first_sent_at)

        User.objects.filter(pk=self.user.pk).update(
            verification_email_sent_at=timezone.now() - timedelta(minutes=5, seconds=1)
        )
        sent_again = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(sent_again, reverse("preferences"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 2)

    def test_failed_send_is_reported_and_does_not_reserve_the_cooldown(self):
        with patch(
            "accounts.email_verification.send_mail",
            side_effect=SMTPException("simulated failure"),
        ):
            failed = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(failed, reverse("preferences"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verification_email_sent_at)
        self.assertContains(
            self.client.get(reverse("preferences")),
            "No se pudo enviar el correo de verificación",
        )

        sent = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(sent, reverse("preferences"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.verification_email_sent_at)

    def test_backend_returning_zero_is_reported_as_failure(self):
        with patch("accounts.email_verification.send_mail", return_value=0):
            response = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(response, reverse("preferences"), fetch_redirect_response=False)
        self.assertEqual(mail.outbox, [])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verification_email_sent_at)
        self.assertContains(
            self.client.get(reverse("preferences")),
            "No se pudo enviar el correo de verificación",
        )

    def test_console_backend_is_reported_as_simulation_not_delivery(self):
        with (
            override_settings(
                EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
            ),
            patch("accounts.email_verification.send_mail", return_value=1),
        ):
            response = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(response, reverse("preferences"), fetch_redirect_response=False)
        self.assertContains(
            self.client.get(reverse("preferences")),
            "No se envió un correo real",
        )
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.verification_email_sent_at)

    def test_verified_user_cannot_request_another_verification_email(self):
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields={"email_verified_at"})

        response = self.client.post(reverse("resend_verification_email"))

        self.assertRedirects(response, reverse("preferences"), fetch_redirect_response=False)
        self.assertEqual(mail.outbox, [])
        self.assertContains(
            self.client.get(reverse("preferences")),
            "Tu dirección de correo ya está verificada.",
        )
