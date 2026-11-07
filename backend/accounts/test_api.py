"""Tests for the session-authenticated Angular JSON API."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.news import NewsItem

from .models import Preferences

User = get_user_model()
PASSWORD = "Api-test-passphrase!2026"


class SessionApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="api-reader",
            password=PASSWORD,
        )

    def json_post(self, client, url_name, payload, csrf_token=None):
        headers = (
            {"HTTP_X_CSRFTOKEN": csrf_token}
            if csrf_token is not None
            else {}
        )
        return client.post(
            reverse(url_name),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def test_csrf_endpoint_sets_cookie_and_session_endpoint_is_public(self):
        client = Client(enforce_csrf_checks=True)

        csrf_response = client.get(reverse("api_csrf"))
        session_response = client.get(reverse("api_session"))

        self.assertEqual(csrf_response.status_code, 200)
        self.assertIn("csrftoken", client.cookies)
        self.assertEqual(
            session_response.json(),
            {"authenticated": False, "user": None},
        )

    def test_login_rejects_missing_csrf_and_invalid_credentials(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("api_csrf"))
        token = client.cookies["csrftoken"].value

        missing_csrf = self.json_post(client, "api_login", {
            "username": self.user.username,
            "password": PASSWORD,
        })
        invalid_login = self.json_post(client, "api_login", {
            "username": self.user.username,
            "password": "incorrecta",
        }, token)

        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(invalid_login.status_code, 401)
        self.assertEqual(
            invalid_login.json()["detail"],
            "Nombre de usuario o contraseña incorrectos.",
        )
        self.assertFalse(client.session.get("_auth_user_id"))

    def test_valid_login_creates_session_and_logout_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("api_csrf"))
        token = client.cookies["csrftoken"].value

        login_response = self.json_post(client, "api_login", {
            "username": self.user.username,
            "password": PASSWORD,
        }, token)
        session_response = client.get(reverse("api_session"))
        missing_csrf_logout = client.post(reverse("api_logout"))
        logout_response = client.post(
            reverse("api_logout"),
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(
            login_response.json(),
            {
                "authenticated": True,
                "user": {"username": self.user.username},
            },
        )
        self.assertEqual(session_response.json()["authenticated"], True)
        self.assertEqual(missing_csrf_logout.status_code, 403)
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json(), {"authenticated": False, "user": None})
        self.assertEqual(client.get(reverse("api_session")).json()["authenticated"], False)

    def test_angular_dev_origin_passes_csrf_with_proxy_host_preserved(self):
        client = Client(enforce_csrf_checks=True)
        client.get(
            reverse("api_csrf"),
            HTTP_HOST="localhost:4200",
        )

        response = client.post(
            reverse("api_login"),
            data=json.dumps(
                {"username": self.user.username, "password": PASSWORD}
            ),
            content_type="application/json",
            HTTP_HOST="localhost:4200",
            HTTP_ORIGIN="http://localhost:4200",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

        self.assertEqual(response.status_code, 200)

    def test_logout_rejects_anonymous_users_and_get_requests(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("api_csrf"))
        token = client.cookies["csrftoken"].value

        get_response = client.get(reverse("api_logout"))
        anonymous_logout = client.post(
            reverse("api_logout"),
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(anonymous_logout.status_code, 401)


class NewsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="news-api-reader",
            password=PASSWORD,
        )
        Preferences.objects.create(
            user=self.user,
            newsletter_topics=["economy", "technology"],
        )
        self.articles = [
            NewsItem(
                title="Noticia de economía",
                source="Fuente económica",
                topic="Economía",
                published=None,
                published_at=None,
                link="https://news.example.test/economia",
                summary="<p>Resumen <strong>económico</strong> &amp; datos.</p>",
            ),
            NewsItem(
                title="Noticia de tecnología",
                source="Fuente tecnológica",
                topic="Tecnología",
                published=None,
                published_at=None,
                link="https://news.example.test/tecnologia",
            ),
        ]

    def test_news_requires_authentication_without_loading_feeds(self):
        with patch(
            "accounts.api_views.get_user_news_page",
            side_effect=AssertionError("anonymous requests must not load news"),
        ) as get_news:
            response = self.client.get(reverse("api_news"))

        self.assertEqual(response.status_code, 401)
        get_news.assert_not_called()

    def test_news_reuses_preference_filter_and_returns_only_requested_topic(self):
        self.client.force_login(self.user)
        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=[],
            ),
            patch(
                "accounts.newsletter_service.fetch_news",
                return_value=(self.articles, ()),
            ),
        ):
            response = self.client.get(
                reverse("api_news"),
                {"tema": "economy"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_topic"], "economy")
        self.assertEqual(
            [article["title"] for article in payload["articles"]],
            ["Noticia de economía"],
        )
        self.assertEqual(
            payload["articles"][0]["summary"],
            "Resumen económico & datos.",
        )
        self.assertEqual(
            payload["topic_filters"],
            [
                {"code": "economy", "label": "Economía"},
                {"code": "technology", "label": "Tecnología"},
            ],
        )

    def test_unknown_news_filter_falls_back_to_all_selected_topics(self):
        self.client.force_login(self.user)
        with (
            patch("accounts.newsletter_service.load_sources", return_value=[]),
            patch(
                "accounts.newsletter_service.fetch_news",
                return_value=(self.articles, ()),
            ),
        ):
            response = self.client.get(
                reverse("api_news"),
                {"tema": "unknown"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_topic"], "")
        self.assertEqual(len(payload["articles"]), 2)
