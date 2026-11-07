"""Offline tests for newsletter preparation and the Angular newsletter API."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as datetime_timezone
from smtplib import SMTPException
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db import connection

from app.news import FeedSource, NewsItem

from .models import NewsletterSendAttempt, Preferences
from .newsletter_service import (
    NewsletterArticle,
    NewsletterPreview,
    get_user_news_page,
    get_user_newsletter_preview,
)

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


def make_preview(**overrides):
    values = {
        "generated_at": datetime(
            2026, 10, 18, 10, 30, tzinfo=datetime_timezone.utc
        ),
        "timezone_name": "Europe/Madrid",
        "newsletter_enabled": False,
        "selected_topics": ("economy",),
        "articles": (
            NewsletterArticle(
                "Noticia de economía",
                "Fuente economía",
                "18/10/2026 12:30",
                "https://articles.example.test/economy",
                "Economía",
                "economy",
            ),
        ),
        "warnings": (),
        "has_selected_topics": True,
        "matched_source_count": 1,
    }
    values.update(overrides)
    return NewsletterPreview(**values)


class NewsletterPreviewServiceTests(TestCase):
    def make_user(self, username, topics, **options):
        user = User.objects.create_user(username=username, email=f"{username}@example.test")
        Preferences.objects.create(
            user=user,
            newsletter_topics=topics,
            **options,
        )
        return user

    def test_preview_uses_only_selected_feed_topics_and_api_filters_articles(self):
        user = self.make_user("economy-reader", ["economy"])
        items = (
            NewsItem(
                title="Economía seleccionada",
                source="Fuente economía",
                topic="Economía",
                published=None,
                published_at=None,
                link="https://articles.example.test/economy",
            ),
            NewsItem(
                title="Tecnología no seleccionada",
                source="Fuente tecnología",
                topic="Tecnología",
                published=None,
                published_at=None,
                link="https://articles.example.test/technology",
            ),
        )
        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=[ECONOMY_SOURCE, TECHNOLOGY_SOURCE],
            ) as load_sources,
            patch(
                "accounts.newsletter_service.fetch_news",
                return_value=(items, ()),
            ) as fetch_news,
        ):
            preview = get_user_newsletter_preview(user)
            page = get_user_news_page(user, "economy", preview)

        self.assertEqual(preview.selected_topics, ("economy",))
        self.assertEqual([article.title for article in page.articles], ["Economía seleccionada"])
        self.assertEqual(page.active_topic, "economy")
        self.assertEqual(load_sources.call_count, 1)
        self.assertEqual(
            [source.topic for source in fetch_news.call_args.args[0]],
            ["Economía"],
        )

    def test_no_topics_does_not_load_or_fetch_feeds(self):
        user = self.make_user("no-topics-reader", [])
        with (
            patch(
                "accounts.newsletter_service.load_sources",
                side_effect=AssertionError("no feeds without selected topics"),
            ) as load_sources,
            patch(
                "accounts.newsletter_service.fetch_news",
                side_effect=AssertionError("no fetch without selected topics"),
            ) as fetch_news,
        ):
            preview = get_user_newsletter_preview(user)

        self.assertFalse(preview.has_selected_topics)
        self.assertEqual(preview.articles, ())
        load_sources.assert_not_called()
        fetch_news.assert_not_called()

    def test_preview_separates_users_and_ignores_duplicate_or_unmapped_sources(self):
        economy_user = self.make_user("economy-only", ["economy", "science"])
        technology_user = self.make_user("technology-only", ["technology"])
        duplicate_economy = FeedSource(
            "Fuente economía duplicada",
            ECONOMY_SOURCE.url,
            "Economía",
        )
        unknown_source = FeedSource(
            "Fuente desconocida",
            "https://feeds.example.test/unknown.xml",
            "Comunidad",
        )
        items = (
            NewsItem(
                title="Economía",
                source="Fuente economía",
                topic="Economía",
                published=None,
                published_at=None,
                link="https://articles.example.test/economy",
            ),
            NewsItem(
                title="Tecnología",
                source="Fuente tecnología",
                topic="Tecnología",
                published=None,
                published_at=None,
                link="https://articles.example.test/technology",
            ),
        )

        def fetch_selected(sources):
            source_topics = {source.topic for source in sources}
            return (
                tuple(item for item in items if item.topic in source_topics),
                (),
            )

        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=[
                    ECONOMY_SOURCE,
                    duplicate_economy,
                    TECHNOLOGY_SOURCE,
                    unknown_source,
                ],
            ),
            patch(
                "accounts.newsletter_service.fetch_news",
                side_effect=fetch_selected,
            ) as fetch_news,
        ):
            economy_preview = get_user_newsletter_preview(economy_user)
            economy_sources = fetch_news.call_args.args[0]
            technology_preview = get_user_newsletter_preview(technology_user)

        self.assertEqual(
            [article.title for article in economy_preview.articles],
            ["Economía"],
        )
        self.assertEqual(
            [source.topic for source in economy_sources],
            ["Economía"],
        )
        self.assertEqual(
            [article.title for article in technology_preview.articles],
            ["Tecnología"],
        )

    def test_feed_warnings_do_not_hide_available_articles(self):
        user = self.make_user("partial-feed-reader", ["economy"])
        item = NewsItem(
            title="Noticia disponible",
            source="Fuente economía",
            topic="Economía",
            published=None,
            published_at=None,
            link="https://articles.example.test/economy",
        )
        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=[ECONOMY_SOURCE],
            ),
            patch(
                "accounts.newsletter_service.fetch_news",
                return_value=((item,), ("Una fuente falló.",)),
            ),
        ):
            preview = get_user_newsletter_preview(user)

        self.assertEqual([article.title for article in preview.articles], ["Noticia disponible"])
        self.assertEqual(preview.warnings, ("Una fuente falló.",))

    def test_preview_does_not_send_email_or_read_cli_tasks(self):
        user = self.make_user("no-side-effects-reader", ["economy"])
        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=[ECONOMY_SOURCE],
            ),
            patch(
                "accounts.newsletter_service.fetch_news",
                return_value=((), ()),
            ),
            patch(
                "accounts.newsletter_service.send_mail",
                side_effect=AssertionError("preview must not send mail"),
            ) as send_mail,
            patch(
                "app.tasks.list_pending_tasks",
                side_effect=AssertionError("preview must not read CLI tasks"),
            ) as list_tasks,
        ):
            get_user_newsletter_preview(user)

        send_mail.assert_not_called()
        list_tasks.assert_not_called()

    def test_unsafe_article_urls_are_excluded_from_preview(self):
        user = self.make_user("url-reader", ["economy"])
        unsafe_article = NewsItem(
            title="No se debe mostrar",
            source="Fuente economía",
            topic="Economía",
            published=None,
            published_at=None,
            link="javascript:alert(1)",
        )
        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=[ECONOMY_SOURCE],
            ),
            patch(
                "accounts.newsletter_service.fetch_news",
                return_value=((unsafe_article,), ()),
            ),
        ):
            preview = get_user_newsletter_preview(user)

        self.assertEqual(preview.articles, ())


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
)
class NewsletterApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="newsletter-api-user",
            email="newsletter-api@example.test",
            password="Newsletter-test-passphrase!2026",
            email_verified_at=timezone.now(),
        )
        Preferences.objects.create(
            user=self.user,
            newsletter_topics=["economy"],
            timezone_name="Europe/Paris",
        )
        self.client.force_login(self.user)
        self.preview = make_preview()

    def post_send(self, payload=None, client=None):
        return (client or self.client).post(
            reverse("api_send_manual_newsletter"),
            data=json.dumps(payload or {}),
            content_type="application/json",
        )

    def test_preview_api_serializes_personalized_and_empty_previews(self):
        with patch(
            "accounts.api_views.get_user_newsletter_preview",
            return_value=self.preview,
        ):
            response = self.client.get(reverse("api_newsletter_preview"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["timezone_name"], "Europe/Madrid")
        self.assertEqual(payload["articles"][0]["title"], "Noticia de economía")
        self.assertTrue(payload["email_verified"])

        empty_preview = make_preview(
            selected_topics=(),
            articles=(),
            has_selected_topics=False,
            matched_source_count=0,
        )
        with patch(
            "accounts.api_views.get_user_newsletter_preview",
            return_value=empty_preview,
        ):
            empty_response = self.client.get(reverse("api_newsletter_preview"))

        self.assertEqual(empty_response.json()["articles"], [])
        self.assertFalse(empty_response.json()["has_selected_topics"])

    def test_anonymous_preview_history_and_send_are_rejected(self):
        self.client.logout()
        with patch("accounts.newsletter_service.send_mail") as send_mail:
            preview = self.client.get(reverse("api_newsletter_preview"))
            history = self.client.get(reverse("api_newsletter_history"))
            send = self.post_send()

        self.assertEqual(preview.status_code, 401)
        self.assertEqual(history.status_code, 401)
        self.assertEqual(send.status_code, 401)
        send_mail.assert_not_called()

    def test_anonymous_manual_send_is_rejected_without_side_effects(self):
        self.client.logout()
        with patch("accounts.newsletter_service.send_mail") as send_mail:
            response = self.post_send()

        self.assertEqual(response.status_code, 401)
        send_mail.assert_not_called()
        self.assertFalse(NewsletterSendAttempt.objects.exists())

    def test_manual_send_uses_verified_session_email_and_ignores_client_fields(self):
        other_user = User.objects.create_user(
            username="other-newsletter-user",
            email="other@example.test",
            password="Newsletter-test-passphrase!2026",
        )
        with (
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                return_value=self.preview,
            ),
            patch("accounts.newsletter_service.send_mail", return_value=1) as send_mail,
        ):
            response = self.post_send(
                {
                    "recipient": "attacker@example.test",
                    "user_id": other_user.pk,
                }
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], NewsletterSendAttempt.Status.ACCEPTED)
        send_mail.assert_called_once()
        self.assertEqual(
            send_mail.call_args.kwargs["recipient_list"],
            [self.user.email],
        )
        attempt = NewsletterSendAttempt.objects.get()
        self.assertEqual(attempt.user, self.user)
        self.assertEqual(attempt.recipient, self.user.email)
        self.assertEqual(attempt.status, NewsletterSendAttempt.Status.ACCEPTED)

    def test_manual_send_is_post_only_csrf_protected_and_accepts_csrf(self):
        get_response = self.client.get(reverse("api_send_manual_newsletter"))
        self.assertEqual(get_response.status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        with patch("accounts.newsletter_service.send_mail") as send_mail:
            rejected = self.post_send(client=csrf_client)
        self.assertEqual(rejected.status_code, 403)
        send_mail.assert_not_called()
        self.assertFalse(NewsletterSendAttempt.objects.exists())

        csrf_client.get(reverse("api_csrf"))
        csrf_token = csrf_client.cookies["csrftoken"].value
        with (
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                return_value=self.preview,
            ),
            patch("accounts.newsletter_service.send_mail", return_value=1) as send_mail,
        ):
            accepted = csrf_client.post(
                reverse("api_send_manual_newsletter"),
                data="{}",
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf_token,
            )
        self.assertEqual(accepted.status_code, 200)
        send_mail.assert_called_once()

    def test_unverified_empty_and_throttled_sends_have_no_email_side_effect(self):
        self.user.email_verified_at = None
        self.user.save(update_fields={"email_verified_at"})
        with (
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                side_effect=AssertionError("unverified account must not fetch feeds"),
            ),
            patch("accounts.newsletter_service.send_mail") as send_mail,
        ):
            unverified = self.post_send()
        self.assertEqual(unverified.status_code, 403)
        self.assertEqual(unverified.json()["status"], "email_unverified")
        send_mail.assert_not_called()
        self.assertFalse(NewsletterSendAttempt.objects.exists())

        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields={"email_verified_at"})
        for preview, expected_status in (
            (make_preview(articles=()), "no_news"),
            (
                make_preview(
                    selected_topics=(),
                    articles=(),
                    has_selected_topics=False,
                ),
                "no_topics",
            ),
        ):
            with (
                patch(
                    "accounts.newsletter_service.get_user_newsletter_preview",
                    return_value=preview,
                ),
                patch("accounts.newsletter_service.send_mail") as send_mail,
            ):
                response = self.post_send()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["status"], expected_status)
            send_mail.assert_not_called()
        self.assertFalse(NewsletterSendAttempt.objects.exists())

        User.objects.filter(pk=self.user.pk).update(
            manual_newsletter_last_attempt_at=timezone.now()
        )
        with patch("accounts.newsletter_service.send_mail") as send_mail:
            throttled = self.post_send()
        self.assertEqual(throttled.status_code, 429)
        self.assertEqual(throttled.json()["status"], "throttled")
        send_mail.assert_not_called()

    def test_simulation_failure_and_uncertain_send_statuses_are_preserved(self):
        with (
            override_settings(
                EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
            ),
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                return_value=self.preview,
            ),
            patch("accounts.newsletter_service.send_mail", return_value=1),
        ):
            simulated = self.post_send()
        self.assertEqual(simulated.status_code, 200)
        self.assertEqual(simulated.json()["status"], NewsletterSendAttempt.Status.SIMULATED)

        User.objects.filter(pk=self.user.pk).update(
            manual_newsletter_last_attempt_at=timezone.now() - timedelta(minutes=6)
        )
        with (
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                return_value=self.preview,
            ),
            patch("accounts.newsletter_service.send_mail", return_value=0),
        ):
            failed = self.post_send()
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(failed.json()["status"], NewsletterSendAttempt.Status.FAILED)

        User.objects.filter(pk=self.user.pk).update(
            manual_newsletter_last_attempt_at=timezone.now() - timedelta(minutes=6)
        )
        with (
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                return_value=self.preview,
            ),
            patch(
                "accounts.newsletter_service.send_mail",
                side_effect=SMTPException("simulated failure"),
            ),
        ):
            uncertain = self.post_send()
        self.assertEqual(uncertain.status_code, 502)
        self.assertEqual(
            uncertain.json()["status"],
            NewsletterSendAttempt.Status.UNCERTAIN,
        )
        with patch("accounts.newsletter_service.send_mail") as send_mail:
            throttled_uncertain = self.post_send()
        self.assertEqual(throttled_uncertain.status_code, 429)
        self.assertEqual(throttled_uncertain.json()["status"], "throttled")
        send_mail.assert_not_called()

    def test_manual_send_uses_personalized_feed_content_when_automatic_is_disabled(self):
        self.assertFalse(self.user.preferences.newsletter_enabled)

        def fetch_selected(sources):
            topic_names = {source.topic for source in sources}
            articles = (
                NewsItem(
                    title="Economía elegida",
                    source="Fuente economía",
                    topic="Economía",
                    published=None,
                    published_at=None,
                    link="https://articles.example.test/economy",
                ),
                NewsItem(
                    title="Tecnología ajena",
                    source="Fuente tecnología",
                    topic="Tecnología",
                    published=None,
                    published_at=None,
                    link="https://articles.example.test/technology",
                ),
            )
            return tuple(article for article in articles if article.topic in topic_names), ()

        with (
            patch(
                "accounts.newsletter_service.load_sources",
                return_value=[ECONOMY_SOURCE, TECHNOLOGY_SOURCE],
            ),
            patch(
                "accounts.newsletter_service.fetch_news",
                side_effect=fetch_selected,
            ),
            patch("accounts.newsletter_service.send_mail", return_value=1) as send_mail,
        ):
            response = self.post_send()

        self.assertEqual(response.status_code, 200)
        message = send_mail.call_args.kwargs["message"]
        self.assertIn("Economía elegida", message)
        self.assertNotIn("Tecnología ajena", message)

    def test_attempt_is_reserved_before_mail_outside_the_transaction(self):
        transaction_depth = len(connection.atomic_blocks)

        def verify_reservation(**_kwargs):
            self.assertEqual(len(connection.atomic_blocks), transaction_depth)
            attempt = NewsletterSendAttempt.objects.get(user=self.user)
            self.assertEqual(attempt.recipient, self.user.email)
            self.assertEqual(attempt.status, NewsletterSendAttempt.Status.PENDING)
            return 1

        with (
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                return_value=self.preview,
            ),
            patch(
                "accounts.newsletter_service.send_mail",
                side_effect=verify_reservation,
            ),
        ):
            response = self.post_send()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            NewsletterSendAttempt.objects.get().status,
            NewsletterSendAttempt.Status.ACCEPTED,
        )

    def test_history_is_limited_and_isolated_to_the_session_user(self):
        own_attempts = [
            NewsletterSendAttempt.objects.create(
                user=self.user,
                recipient=f"own-{index}@example.test",
                status=NewsletterSendAttempt.Status.FAILED,
            )
            for index in range(11)
        ]
        other_user = User.objects.create_user(
            username="history-other-user",
            email="history-other@example.test",
            password="Newsletter-test-passphrase!2026",
        )
        NewsletterSendAttempt.objects.create(
            user=other_user,
            recipient=other_user.email,
            status=NewsletterSendAttempt.Status.ACCEPTED,
        )

        response = self.client.get(reverse("api_newsletter_history"))

        self.assertEqual(response.status_code, 200)
        attempts = response.json()["attempts"]
        self.assertEqual(len(attempts), 10)
        self.assertEqual(attempts[0]["recipient"], own_attempts[-1].recipient)
        self.assertNotIn(
            own_attempts[0].recipient,
            [attempt["recipient"] for attempt in attempts],
        )
        self.assertNotIn(
            other_user.email,
            [attempt["recipient"] for attempt in attempts],
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="asistente@example.test",
)
class ConcurrentManualNewsletterTests(TransactionTestCase):
    reset_sequences = True

    def test_simultaneous_api_posts_reserve_only_one_attempt(self):
        user = User.objects.create_user(
            username="concurrent-sender",
            email="concurrent@example.test",
            password="Newsletter-test-passphrase!2026",
            email_verified_at=timezone.now(),
        )
        Preferences.objects.create(user=user, newsletter_topics=["economy"])
        preview = make_preview()
        preview_barrier = Barrier(2)
        sends = []

        def shared_preview(_user):
            preview_barrier.wait(timeout=5)
            return preview

        def record_send(**_kwargs):
            sends.append(True)
            return 1

        clients = [Client(), Client()]
        for client in clients:
            client.force_login(user)

        def post(client):
            return client.post(
                reverse("api_send_manual_newsletter"),
                data="{}",
                content_type="application/json",
            )

        with (
            patch(
                "accounts.newsletter_service.get_user_newsletter_preview",
                side_effect=shared_preview,
            ),
            patch("accounts.newsletter_service.send_mail", side_effect=record_send),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(post, client) for client in clients]
                results = [future.result(timeout=10) for future in futures]

        self.assertEqual(len(results), 2)
        self.assertTrue(all(response.status_code in {200, 429, 409} for response in results))
        self.assertEqual(len(sends), 1)
        self.assertEqual(NewsletterSendAttempt.objects.filter(user=user).count(), 1)
