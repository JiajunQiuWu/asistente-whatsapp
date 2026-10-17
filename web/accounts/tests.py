"""Pruebas locales de registro, autenticación y privacidad de preferencias."""

from datetime import time
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .forms import PreferencesForm, RegistrationForm
from .models import Preferences

User = get_user_model()
STRONG_PASSWORD = "L0cal-test-passphrase!2026"


class RegistrationAndAuthenticationTests(TestCase):
    def test_registration_creates_user_and_default_preferences_then_redirects_login(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "nueva-persona",
                "password1": STRONG_PASSWORD,
                "password2": STRONG_PASSWORD,
            },
        )

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        login_page = self.client.get(reverse("login"))
        self.assertContains(
            login_page,
            "Cuenta creada correctamente. Ya puedes iniciar sesión",
        )
        self.assertContains(login_page, 'role="status"')
        user = User.objects.get(username="nueva-persona")
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        preferences = user.preferences
        self.assertFalse(preferences.newsletter_enabled)
        self.assertEqual(preferences.newsletter_time, time(9, 0))
        self.assertEqual(preferences.timezone_name, "Europe/Madrid")
        self.assertFalse(preferences.alerts_enabled)
        self.assertEqual(preferences.daily_alert_limit, 3)

    def test_registration_rejects_mismatched_and_weak_passwords(self):
        mismatch = self.client.post(
            reverse("register"),
            {
                "username": "mismatch-user",
                "password1": STRONG_PASSWORD,
                "password2": "Different-password-123!",
            },
        )
        weak = self.client.post(
            reverse("register"),
            {
                "username": "weak-user",
                "password1": "password",
                "password2": "password",
            },
        )

        self.assertEqual(mismatch.status_code, 200)
        self.assertIn("password2", mismatch.context["form"].errors)
        self.assertEqual(weak.status_code, 200)
        self.assertIn("password2", weak.context["form"].errors)
        self.assertFalse(User.objects.filter(username__in=["mismatch-user", "weak-user"]).exists())
        self.assertContains(mismatch, 'role="alert"')
        self.assertContains(mismatch, 'value="mismatch-user"')
        self.assertNotContains(mismatch, f'value="{STRONG_PASSWORD}"')

    def test_registration_field_errors_are_rendered_next_to_fields(self):
        User.objects.create_user(username="existing-user", password=STRONG_PASSWORD)

        response = self.client.post(
            reverse("register"),
            {
                "username": "existing-user",
                "password1": STRONG_PASSWORD,
                "password2": STRONG_PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_username"')
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, "Ya existe")
        self.assertEqual(User.objects.filter(username="existing-user").count(), 1)

    def test_login_and_post_logout_use_django_authentication(self):
        user = User.objects.create_user(
            username="login-user",
            password=STRONG_PASSWORD,
        )

        invalid_login = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "incorrecta"},
        )
        self.assertEqual(invalid_login.status_code, 200)
        self.assertContains(invalid_login, 'role="alert"')

        login_response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": STRONG_PASSWORD},
        )
        self.assertRedirects(login_response, reverse("preferences"))
        self.assertEqual(self.client.get(reverse("preferences")).status_code, 200)

        logout_response = self.client.post(reverse("logout"))
        self.assertRedirects(logout_response, reverse("login"))
        self.assertRedirects(
            self.client.get(reverse("preferences")),
            f"{reverse('login')}?next={reverse('preferences')}",
        )

    def test_logout_rejects_get(self):
        user = User.objects.create_user(username="logout-user", password=STRONG_PASSWORD)
        self.client.force_login(user)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 405)

    def test_csrf_protects_registration_login_and_logout_posts(self):
        csrf_client = Client(enforce_csrf_checks=True)
        user = User.objects.create_user(
            username="csrf-user",
            password=STRONG_PASSWORD,
        )

        self.assertEqual(csrf_client.post(reverse("register"), {}).status_code, 403)
        self.assertEqual(csrf_client.post(reverse("login"), {}).status_code, 403)
        csrf_client.force_login(user)
        self.assertEqual(csrf_client.post(reverse("logout")).status_code, 403)

    def test_private_pages_redirect_anonymous_users_to_login(self):
        for url_name in ("home", "preferences"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={reverse(url_name)}",
                )


class PreferencesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="preferences-user",
            password=STRONG_PASSWORD,
        )
        self.preferences = Preferences.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_preferences_form_saves_independent_topic_sets_and_options(self):
        response = self.client.post(
            reverse("preferences"),
            {
                "newsletter_topics": ["ai", "science"],
                "newsletter_enabled": "on",
                "newsletter_time": "08:15",
                "timezone_name": "Europe/Paris",
                "alerts_enabled": "on",
                "alert_topics": ["economy", "international"],
                "daily_alert_limit": "10",
            },
        )

        self.assertRedirects(
            response,
            reverse("preferences"),
            fetch_redirect_response=False,
        )
        saved_page = self.client.get(reverse("preferences"))
        self.assertContains(saved_page, "Tus preferencias se han guardado.")
        self.assertContains(saved_page, 'role="status"')
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.newsletter_topics, ["ai", "science"])
        self.assertTrue(self.preferences.newsletter_enabled)
        self.assertEqual(self.preferences.newsletter_time, time(8, 15))
        self.assertEqual(self.preferences.timezone_name, "Europe/Paris")
        self.assertTrue(self.preferences.alerts_enabled)
        self.assertEqual(
            self.preferences.alert_topics,
            ["economy", "international"],
        )
        self.assertEqual(self.preferences.daily_alert_limit, 10)

    def test_preferences_form_rejects_alert_limits_outside_one_to_ten(self):
        for limit in ("0", "11"):
            with self.subTest(limit=limit):
                form = PreferencesForm(
                    data={
                        "newsletter_time": "09:00",
                        "timezone_name": "Europe/Madrid",
                        "daily_alert_limit": limit,
                    },
                    instance=self.preferences,
                )
                self.assertFalse(form.is_valid())
                self.assertIn("daily_alert_limit", form.errors)

    def test_preferences_form_rejects_unknown_topics_and_timezone(self):
        form = PreferencesForm(
            data={
                "newsletter_topics": ["unknown"],
                "newsletter_time": "09:00",
                "timezone_name": "Not/A_Timezone",
                "alert_topics": ["ai"],
                "daily_alert_limit": "3",
            },
            instance=self.preferences,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("newsletter_topics", form.errors)
        self.assertIn("timezone_name", form.errors)

    def test_users_keep_separate_preferences_and_cannot_change_each_others(self):
        other_user = User.objects.create_user(
            username="other-user",
            password=STRONG_PASSWORD,
        )
        other_preferences = Preferences.objects.create(
            user=other_user,
            newsletter_topics=["economy"],
            alert_topics=["science"],
        )

        response = self.client.post(
            reverse("preferences"),
            {
                "user": str(other_user.pk),
                "newsletter_topics": ["technology"],
                "newsletter_time": "10:30",
                "timezone_name": "Europe/Madrid",
                "alert_topics": ["ai"],
                "daily_alert_limit": "4",
            },
        )

        self.assertRedirects(response, reverse("preferences"))
        self.preferences.refresh_from_db()
        other_preferences.refresh_from_db()
        self.assertEqual(self.preferences.newsletter_topics, ["technology"])
        self.assertEqual(self.preferences.alert_topics, ["ai"])
        self.assertEqual(other_preferences.newsletter_topics, ["economy"])
        self.assertEqual(other_preferences.alert_topics, ["science"])

        self.client.force_login(other_user)
        other_page = self.client.get(reverse("preferences"))
        self.assertEqual(other_page.status_code, 200)
        self.assertContains(
            other_page,
            'value="economy" id="id_newsletter_topics_2" checked',
        )
        self.assertNotContains(
            other_page,
            'value="technology" id="id_newsletter_topics_1" checked',
        )

    def test_preferences_page_and_save_do_not_send_email(self):
        with (
            patch("smtplib.SMTP", side_effect=AssertionError("no SMTP from preferences")),
            patch("django.core.mail.send_mail", side_effect=AssertionError("no mail")),
        ):
            get_response = self.client.get(reverse("preferences"))
            post_response = self.client.post(
                reverse("preferences"),
                {
                    "newsletter_topics": ["ai"],
                    "newsletter_time": "09:00",
                    "timezone_name": "Europe/Madrid",
                    "alert_topics": [],
                    "daily_alert_limit": "3",
                },
            )

        self.assertEqual(get_response.status_code, 200)
        self.assertRedirects(post_response, reverse("preferences"))

    def test_admin_registers_custom_user_and_preferences(self):
        self.assertTrue(admin.site.is_registered(User))
        self.assertTrue(admin.site.is_registered(Preferences))
