"""Pruebas offline para la vista previa personalizada del boletín."""

from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.news import FeedSource

from .models import Preferences

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
        self.assertContains(response, "Esta consulta manual no lo activa")
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
