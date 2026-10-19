"""Pruebas offline para la vista previa personalizada del boletín."""

from io import BytesIO
from datetime import datetime, timedelta, timezone as datetime_timezone
from smtplib import SMTPException
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.news import FeedSource

from .models import NewsletterSendAttempt, Preferences
from .newsletter_service import NewsletterArticle, NewsletterPreview

User = get_user_model()

ECONOMY_SOURCE = FeedSource(
    "Fuente economía",
    "https://feeds.example.test/economy.xml",
    "Economía",
)
TECHNOLOGY_SOURCE = FeedSource(
    "Fuente tecnología",
    "https://feeds.example.test/technology.xml",
    "Tecnología",
)
UNKNOWN_SOURCE = FeedSource(
    "Fuente desconocida",
    "https://feeds.example.test/unknown.xml",
    "Comunidad",
)


def rss_response(title: str, link: str = "https://articles.example.test/item") -> BytesIO:
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><item>
      <title>{title}</title><link>{link}</link>
      <pubDate>Sun, 18 Oct 2026 08:30:00 GMT</pubDate>
    </item></channel></rss>"""
    return BytesIO(content.encode("utf-8"))


class NewsletterPreviewTests(TestCase):
    def make_user(self, username: str, newsletter_topics: list[str], **options):
        user = User.objects.create_user(username=username, password="test-password")
        Preferences.objects.create(
            user=user,
            newsletter_topics=newsletter_topics,
            **options,
        )
        return user

    def configure_sources(self, sources):
        return patch(
            "accounts.newsletter_service.load_sources",
            return_value=sources,
        )

    def test_anonymous_visitor_is_redirected_to_login(self):
        with patch(
            "accounts.newsletter_service.load_sources",
            side_effect=AssertionError("no feeds for anonymous visitors"),
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('newsletter_preview')}",
        )

    def test_economy_user_sees_only_news_matching_newsletter_topics(self):
        user = self.make_user(
            "economy-reader",
            ["economy"],
            alert_topics=["technology"],
            newsletter_enabled=False,
        )
        self.client.force_login(user)
        responses = {
            ECONOMY_SOURCE.url: rss_response("Economía seleccionada"),
            TECHNOLOGY_SOURCE.url: rss_response("Tecnología no seleccionada"),
        }

        with (
            self.configure_sources([ECONOMY_SOURCE, TECHNOLOGY_SOURCE]) as load_sources,
            patch("app.news.urlopen", side_effect=lambda request, timeout: responses[request.full_url]) as urlopen,
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.args[0].full_url, ECONOMY_SOURCE.url)
        load_sources.assert_called_once()
        self.assertContains(response, "Economía seleccionada")
        self.assertNotContains(response, "Tecnología no seleccionada")
        self.assertContains(response, "esto no activa el envío automático")
        self.assertContains(response, "18/10/2026 10:30")

    def test_users_with_different_preferences_receive_different_articles(self):
        economy_user = self.make_user("reader-economy", ["economy"])
        technology_user = self.make_user("reader-technology", ["technology"])
        responses = {
            ECONOMY_SOURCE.url: rss_response("Solo economía"),
            TECHNOLOGY_SOURCE.url: rss_response("Solo tecnología"),
        }
        with (
            self.configure_sources([ECONOMY_SOURCE, TECHNOLOGY_SOURCE]),
            patch("app.news.urlopen", side_effect=lambda request, timeout: responses[request.full_url]),
        ):
            self.client.force_login(economy_user)
            economy_response = self.client.get(reverse("newsletter_preview"))
            self.client.force_login(technology_user)
            technology_response = self.client.get(reverse("newsletter_preview"))

        self.assertContains(economy_response, "Solo economía")
        self.assertNotContains(economy_response, "Solo tecnología")
        self.assertContains(technology_response, "Solo tecnología")
        self.assertNotContains(technology_response, "Solo economía")

    def test_unmapped_and_unselected_topics_are_not_downloaded(self):
        user = self.make_user("source-filter", ["economy", "science"])
        self.client.force_login(user)
        responses = {ECONOMY_SOURCE.url: rss_response("Economía")}

        with (
            self.configure_sources(
                [ECONOMY_SOURCE, TECHNOLOGY_SOURCE, UNKNOWN_SOURCE]
            ),
            patch("app.news.urlopen", side_effect=lambda request, timeout: responses[request.full_url]) as urlopen,
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertContains(response, "Economía")
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.args[0].full_url, ECONOMY_SOURCE.url)

    def test_duplicate_configured_source_is_downloaded_only_once(self):
        user = self.make_user("duplicate-source", ["economy"])
        self.client.force_login(user)
        duplicate = FeedSource(
            "Fuente economía duplicada",
            ECONOMY_SOURCE.url,
            "Economía",
        )

        with (
            self.configure_sources([ECONOMY_SOURCE, duplicate]),
            patch("app.news.urlopen", return_value=rss_response("Una sola consulta")) as urlopen,
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertEqual(urlopen.call_count, 1)
        self.assertContains(response, "Una sola consulta")

    def test_no_newsletter_topics_does_not_read_feed_configuration_or_fetch(self):
        user = self.make_user("no-topics", [], alert_topics=["economy"])
        self.client.force_login(user)

        with (
            patch(
                "accounts.newsletter_service.load_sources",
                side_effect=AssertionError("no configuration read without topics"),
            ) as load_sources,
            patch(
                "accounts.newsletter_service.fetch_news",
                side_effect=AssertionError("no fetch without topics"),
            ) as fetch_news,
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertContains(response, "Aún no has elegido temas")
        self.assertContains(response, reverse("preferences"))
        load_sources.assert_not_called()
        fetch_news.assert_not_called()

    def test_failed_feed_does_not_hide_articles_from_other_sources(self):
        user = self.make_user("resilient-reader", ["economy", "technology"])
        self.client.force_login(user)
        responses = {
            TECHNOLOGY_SOURCE.url: rss_response("Tecnología disponible"),
        }

        def local_open(request, timeout):
            if request.full_url == ECONOMY_SOURCE.url:
                raise URLError("fallo simulado")
            return responses[request.full_url]

        with (
            self.configure_sources([ECONOMY_SOURCE, TECHNOLOGY_SOURCE]),
            patch("app.news.urlopen", side_effect=local_open),
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertContains(response, "No se pudo consultar Fuente economía")
        self.assertContains(response, "Tecnología disponible")

    def test_preview_does_not_access_cli_tasks_or_send_email(self):
        user = self.make_user("no-side-effects", ["economy"])
        self.client.force_login(user)

        with (
            self.configure_sources([ECONOMY_SOURCE]),
            patch(
                "app.news.urlopen",
                return_value=rss_response("Vista previa"),
            ),
            patch(
                "app.tasks.list_pending_tasks",
                side_effect=AssertionError("no CLI task access"),
            ) as list_tasks,
            patch(
                "smtplib.SMTP",
                side_effect=AssertionError("no SMTP"),
            ) as smtp,
            patch(
                "django.core.mail.send_mail",
                side_effect=AssertionError("no email"),
            ) as send_mail,
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertEqual(response.status_code, 200)
        list_tasks.assert_not_called()
        smtp.assert_not_called()
        send_mail.assert_not_called()

    def test_untrusted_title_is_escaped_and_non_http_article_links_are_hidden(self):
        user = self.make_user("escaped-reader", ["economy"])
        self.client.force_login(user)
        content = BytesIO(
            b"""<?xml version="1.0"?>
            <rss version="2.0"><channel>
              <item><title>&lt;script&gt;alert(1)&lt;/script&gt;</title>
                <link>https://articles.example.test/safe</link></item>
              <item><title>Enlace no permitido</title>
                <link>javascript:alert(1)</link></item>
            </channel></rss>"""
        )

        with (
            self.configure_sources([ECONOMY_SOURCE]),
            patch("app.news.urlopen", return_value=content),
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>")
        self.assertNotContains(response, "Enlace no permitido")
        self.assertContains(response, 'href="https://articles.example.test/safe"')


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
)
class ManualNewsletterTests(TestCase):
    def make_user(
        self,
        username: str,
        email: str,
        *,
        verified: bool = True,
        topics: list[str] | None = None,
        **preference_options,
    ):
        user = User.objects.create_user(
            username=username,
            email=email,
            password="L0cal-test-passphrase!2026",
        )
        if verified:
            user.email_verified_at = timezone.now()
            user.save(update_fields={"email_verified_at"})
        Preferences.objects.create(
            user=user,
            newsletter_topics=topics or [],
            **preference_options,
        )
        return user

    @staticmethod
    def available_preview(**overrides):
        values = {
            "generated_at": datetime(2026, 10, 18, 10, 30, tzinfo=datetime_timezone.utc),
            "timezone_name": "Europe/Madrid",
            "newsletter_enabled": False,
            "selected_topics": ("economy",),
            "articles": (
                NewsletterArticle(
                    "Noticia de economía",
                    "Fuente economía",
                    "18/10/2026 12:30",
                    "https://articles.example.test/economy",
                ),
            ),
            "warnings": (),
            "has_selected_topics": True,
            "matched_source_count": 1,
        }
        values.update(overrides)
        return NewsletterPreview(**values)

    def post_manual_send(self, **posted_data):
        return self.client.post(reverse("send_manual_newsletter"), posted_data)

    def test_anonymous_and_unverified_users_cannot_send(self):
        anonymous = self.post_manual_send()
        self.assertRedirects(
            anonymous,
            f"{reverse('login')}?next={reverse('send_manual_newsletter')}",
            fetch_redirect_response=False,
        )

        user = self.make_user(
            "unverified-sender",
            "unverified@example.test",
            verified=False,
            topics=["economy"],
        )
        self.client.force_login(user)
        with patch(
            "accounts.newsletter_service.get_user_newsletter_preview",
            side_effect=AssertionError("unverified accounts must not generate mail"),
        ), patch("accounts.views.send_mail") as send_mail:
            response = self.post_manual_send()

        self.assertRedirects(
            response,
            reverse("newsletter_preview"),
            fetch_redirect_response=False,
        )
        send_mail.assert_not_called()
        self.assertFalse(NewsletterSendAttempt.objects.exists())

    def test_get_never_sends_and_manual_post_requires_csrf(self):
        user = self.make_user("get-is-safe", "get@example.test", topics=["economy"])
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(reverse("send_manual_newsletter")).status_code,
            405,
        )

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        with patch("accounts.views.send_mail") as send_mail:
            response = csrf_client.post(reverse("send_manual_newsletter"))

        self.assertEqual(response.status_code, 403)
        send_mail.assert_not_called()
        self.assertFalse(NewsletterSendAttempt.objects.exists())

    def test_sends_only_to_verified_users_email_and_ignores_tampered_fields(self):
        user = self.make_user(
            "spoof-resistant",
            "verified@example.test",
            topics=["economy"],
        )
        other_user = self.make_user(
            "not-the-recipient",
            "other@example.test",
            topics=["technology"],
        )
        self.client.force_login(user)

        with (
            patch(
                "accounts.views.get_user_newsletter_preview",
                return_value=self.available_preview(),
            ),
            patch("accounts.views.send_mail", return_value=1) as send_mail,
        ):
            response = self.post_manual_send(
                recipient="attacker@example.test",
                email="attacker@example.test",
                user_id=str(other_user.pk),
                user=str(other_user.pk),
            )

        self.assertRedirects(
            response,
            reverse("newsletter_preview"),
            fetch_redirect_response=False,
        )
        self.assertEqual(send_mail.call_args.kwargs["recipient_list"], [user.email])
        attempt = NewsletterSendAttempt.objects.get()
        self.assertEqual(attempt.user, user)
        self.assertEqual(attempt.recipient, user.email)
        self.assertEqual(attempt.status, NewsletterSendAttempt.Status.ACCEPTED)

    def test_uses_personalized_topics_timezone_and_never_reads_cli_tasks(self):
        user = self.make_user(
            "personalized-sender",
            "personalized@example.test",
            topics=["economy"],
            timezone_name="Europe/Paris",
        )
        self.client.force_login(user)
        sources = [ECONOMY_SOURCE, TECHNOLOGY_SOURCE]
        responses = {
            ECONOMY_SOURCE.url: rss_response("Economía para el boletín"),
            TECHNOLOGY_SOURCE.url: rss_response("Tecnología no seleccionada"),
        }

        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=sources,
            ),
            patch("app.news.urlopen", side_effect=lambda request, timeout: responses[request.full_url]),
            patch(
                "app.tasks.list_pending_tasks",
                side_effect=AssertionError("no CLI task access"),
            ) as list_tasks,
        ):
            response = self.post_manual_send()

        self.assertRedirects(
            response,
            reverse("newsletter_preview"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertIn("Economía para el boletín", mail.outbox[0].body)
        self.assertNotIn("Tecnología no seleccionada", mail.outbox[0].body)
        self.assertIn("18/10/2026 10:30", mail.outbox[0].body)
        self.assertNotIn("tarea", mail.outbox[0].body.lower())
        list_tasks.assert_not_called()
        self.assertEqual(
            NewsletterSendAttempt.objects.get().status,
            NewsletterSendAttempt.Status.ACCEPTED,
        )

    def test_automatic_disabled_does_not_prevent_manual_send(self):
        user = self.make_user(
            "manual-when-disabled",
            "disabled@example.test",
            topics=["economy"],
            newsletter_enabled=False,
        )
        self.client.force_login(user)
        with (
            patch(
                "accounts.views.get_user_newsletter_preview",
                return_value=self.available_preview(newsletter_enabled=False),
            ),
            patch("accounts.views.send_mail", return_value=1),
        ):
            response = self.post_manual_send()

        page = self.client.get(reverse("newsletter_preview"))
        self.assertRedirects(
            response,
            reverse("newsletter_preview"),
            fetch_redirect_response=False,
        )
        self.assertContains(page, "envío automático está desactivado")
        self.assertContains(page, "Enviarme mi boletín")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_console_backend_is_reported_as_a_simulation(self):
        user = self.make_user(
            "console-sender",
            "console@example.test",
            topics=["economy"],
        )
        self.client.force_login(user)
        with (
            patch(
                "accounts.views.get_user_newsletter_preview",
                return_value=self.available_preview(),
            ),
            patch("accounts.views.send_mail", return_value=1),
        ):
            response = self.post_manual_send()

        self.assertRedirects(
            response,
            reverse("newsletter_preview"),
            fetch_redirect_response=False,
        )
        self.assertContains(
            self.client.get(reverse("newsletter_preview")),
            "Simulación completada",
        )

    def test_missing_topics_or_news_do_not_send_or_create_attempts(self):
        user = self.make_user(
            "no-news-sender",
            "none@example.test",
            topics=["economy"],
        )
        self.client.force_login(user)

        for preview, expected_notice in (
            (
                self.available_preview(has_selected_topics=False, selected_topics=(), articles=()),
                "Elige al menos un tema",
            ),
            (
                self.available_preview(articles=()),
                "No hay noticias disponibles",
            ),
        ):
            with (
                self.subTest(expected_notice=expected_notice),
                patch("accounts.views.get_user_newsletter_preview", return_value=preview),
                patch("accounts.views.send_mail") as send_mail,
            ):
                response = self.post_manual_send()
                self.assertRedirects(
                    response,
                    reverse("newsletter_preview"),
                    fetch_redirect_response=False,
                )
                send_mail.assert_not_called()
                self.assertContains(self.client.get(reverse("newsletter_preview")), expected_notice)

        self.assertFalse(NewsletterSendAttempt.objects.exists())

    def test_throttles_repeated_requests_and_backend_failure_is_not_retried(self):
        user = self.make_user(
            "throttled-sender",
            "throttled@example.test",
            topics=["economy"],
        )
        self.client.force_login(user)
        with (
            patch(
                "accounts.views.get_user_newsletter_preview",
                return_value=self.available_preview(),
            ),
            patch("accounts.views.send_mail", return_value=1) as send_mail,
        ):
            self.post_manual_send()
            self.post_manual_send()

        self.assertEqual(send_mail.call_count, 1)
        self.assertEqual(NewsletterSendAttempt.objects.count(), 1)

        User.objects.filter(pk=user.pk).update(
            manual_newsletter_last_attempt_at=timezone.now() - timedelta(minutes=6)
        )
        with (
            patch(
                "accounts.views.get_user_newsletter_preview",
                return_value=self.available_preview(),
            ),
            patch(
                "accounts.views.send_mail",
                side_effect=SMTPException("simulated backend failure"),
            ) as failed_send,
        ):
            self.post_manual_send()
            self.post_manual_send()

        self.assertEqual(failed_send.call_count, 1)
        self.assertEqual(NewsletterSendAttempt.objects.count(), 2)
        failed_attempt = NewsletterSendAttempt.objects.latest("created_at")
        self.assertEqual(failed_attempt.status, NewsletterSendAttempt.Status.FAILED)

    def test_history_shows_only_the_users_latest_ten_attempts(self):
        user = self.make_user("history-owner", "history@example.test", topics=[])
        other_user = self.make_user("history-other", "other-history@example.test", topics=[])
        self.client.force_login(user)
        attempts = [
            NewsletterSendAttempt.objects.create(
                user=user,
                recipient=f"own-{number}@example.test",
                status=NewsletterSendAttempt.Status.FAILED,
            )
            for number in range(11)
        ]
        NewsletterSendAttempt.objects.create(
            user=other_user,
            recipient="private-other@example.test",
            status=NewsletterSendAttempt.Status.ACCEPTED,
        )

        with patch(
            "accounts.views.get_user_newsletter_preview",
            return_value=self.available_preview(
                has_selected_topics=False,
                selected_topics=(),
                articles=(),
            ),
        ):
            response = self.client.get(reverse("newsletter_preview"))

        self.assertContains(response, "Tus últimos intentos")
        self.assertContains(response, attempts[-1].recipient)
        self.assertNotContains(response, attempts[0].recipient)
        self.assertNotContains(response, "private-other@example.test")
        self.assertEqual(NewsletterSendAttempt.objects.filter(user=user).count(), 11)
