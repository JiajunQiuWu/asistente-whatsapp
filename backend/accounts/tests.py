"""Tests for shared account forms and Django Admin registration."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import PreferencesForm
from .models import Preferences

User = get_user_model()


class PreferencesFormValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="preferences-validation-user",
            password="Preferences-test-passphrase!2026",
        )
        self.preferences = Preferences.objects.create(user=self.user)

    def test_alert_limit_must_be_between_one_and_ten(self):
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

    def test_unknown_topics_and_timezone_are_rejected(self):
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


class AdminTests(TestCase):
    def test_admin_registers_models_and_keeps_login_route(self):
        self.assertTrue(admin.site.is_registered(User))
        self.assertTrue(admin.site.is_registered(Preferences))
        response = self.client.get(reverse("admin:login"))
        self.assertEqual(response.status_code, 200)

    def test_admin_remains_restricted_to_authenticated_staff(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('admin:login')}?next=/admin/")

        staff_user = User.objects.create_superuser(
            username="admin-staff",
            email="admin@example.test",
            password="Admin-test-passphrase!2026",
        )
        self.client.force_login(staff_user)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
