"""Obtención de la vista previa de noticias según las preferencias del usuario."""

import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.mail import send_mail
from django.db import OperationalError, transaction
from django.db.models import Q
from django.utils import timezone

from app.news import FeedConfigError, FeedSource, NewsItem, fetch_news, load_sources

from .models import NewsletterSendAttempt, Preferences, TOPIC_CHOICES, User

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FEEDS_PATH = REPOSITORY_ROOT / "data" / "feeds.json"

# Los códigos guardados por Django se traducen a las etiquetas de data/feeds.json.
# IA y ciencia no tienen aún fuentes configuradas; los temas no mapeados se omiten.
FEED_TOPIC_BY_PREFERENCE = {
    "technology": "Tecnología",
    "economy": "Economía",
    "international": "Actualidad",
}
PREFERENCE_BY_FEED_TOPIC = {
    feed_topic: preference_topic
    for preference_topic, feed_topic in FEED_TOPIC_BY_PREFERENCE.items()
}
MAX_NEWS_ITEMS = 5
NEWSLETTER_SEND_INTERVAL = timedelta(minutes=5)

MANUAL_NEWSLETTER_MESSAGES = {
    "email_unverified": "Verifica tu correo antes de solicitar un boletín.",
    "no_topics": "Elige al menos un tema antes de solicitar el envío del boletín.",
    "no_news": "No hay noticias disponibles para tus temas; no se ha enviado el boletín.",
    "throttled": (
        "Ya has solicitado un boletín recientemente. "
        "Espera cinco minutos antes de volver a intentarlo."
    ),
    "busy": (
        "Otra solicitud podría estar procesando tu envío. Comprueba el "
        "historial y espera cinco minutos antes de volver a intentarlo."
    ),
    "failed": "No se pudo completar el envío. No se ha programado un reintento.",
    "uncertain": (
        "No se pudo confirmar el resultado del envío. No se realizará un "
        "reintento automático; comprueba tu correo antes de volver a solicitarlo."
    ),
    NewsletterSendAttempt.Status.SIMULATED: (
        "Simulación completada por el backend de consola; no se envió un "
        "correo real."
    ),
    NewsletterSendAttempt.Status.ACCEPTED: (
        "El backend aceptó el boletín. Esto no garantiza su llegada a Recibidos."
    ),
}


@dataclass(frozen=True)
class NewsletterArticle:
    """Validated news fields for API responses and personalized email."""

    title: str
    source: str
    published: str | None
    link: str
    topic: str = ""
    topic_code: str = ""
    summary: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class NewsletterPreview:
    """Datos de boletín ya seleccionados, sin presentación ni efectos laterales."""

    generated_at: datetime
    timezone_name: str
    newsletter_enabled: bool
    selected_topics: tuple[str, ...]
    articles: tuple[NewsletterArticle, ...]
    warnings: tuple[str, ...]
    has_selected_topics: bool
    matched_source_count: int


@dataclass(frozen=True)
class NewsPage:
    """Filtered news data returned by the Angular API."""

    preview: NewsletterPreview
    articles: tuple[NewsletterArticle, ...]
    topic_filters: tuple[dict[str, str], ...]
    active_topic: str
    selected_topic_label: str


def request_manual_newsletter(user: User) -> tuple[str, NewsletterSendAttempt | None]:
    """Reserve and synchronously send a personalized newsletter to its owner."""
    if user.email_verified_at is None:
        return "email_unverified", None

    preview = get_user_newsletter_preview(user)
    if not preview.has_selected_topics:
        return "no_topics", None
    if not preview.articles:
        return "no_news", None

    now = timezone.now()
    try:
        with transaction.atomic():
            reserved = (
                User.objects.filter(
                    pk=user.pk,
                    email=user.email,
                    email_verified_at__isnull=False,
                )
                .exclude(email="")
                .filter(
                    Q(manual_newsletter_last_attempt_at__isnull=True)
                    | Q(
                        manual_newsletter_last_attempt_at__lte=(
                            now - NEWSLETTER_SEND_INTERVAL
                        )
                    )
                )
                .update(manual_newsletter_last_attempt_at=now)
            )
            if not reserved:
                return "throttled", None

            attempt = NewsletterSendAttempt.objects.create(
                user=user,
                recipient=user.email,
            )
    except OperationalError as error:
        if "locked" not in str(error).lower():
            raise
        return "busy", None

    topic_labels = dict(TOPIC_CHOICES)
    selected_topics = ", ".join(
        topic_labels.get(topic, topic) for topic in preview.selected_topics
    )
    lines = [
        f"Tu boletín personal ({preview.generated_at:%d/%m/%Y %H:%M} "
        f"{preview.timezone_name})",
        f"Temas: {selected_topics}",
        "",
    ]
    for article in preview.articles:
        lines.extend(
            [
                article.title,
                article.source,
                f"Publicado: {article.published}" if article.published else "",
                article.link,
                "",
            ]
        )

    try:
        sent_count = send_mail(
            subject="Tu boletín personal",
            message="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[attempt.recipient],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException, ValueError):
        status = NewsletterSendAttempt.Status.UNCERTAIN
    else:
        if sent_count != 1:
            status = NewsletterSendAttempt.Status.FAILED
        elif settings.EMAIL_BACKEND == (
            "django.core.mail.backends.console.EmailBackend"
        ):
            status = NewsletterSendAttempt.Status.SIMULATED
        else:
            status = NewsletterSendAttempt.Status.ACCEPTED

    attempt.status = status
    attempt.save(update_fields={"status"})
    return status, attempt


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.hostname is not None
        and (port is None or 1 <= port <= 65535)
        and parsed.username is None
        and parsed.password is None
    )


def _localized_date(item: NewsItem, user_timezone: ZoneInfo) -> str | None:
    if item.published_at is not None:
        return item.published_at.astimezone(user_timezone).strftime(
            "%d/%m/%Y %H:%M"
        )
    return item.published


def get_user_newsletter_preview(
    user: User,
    generated_at: datetime | None = None,
) -> NewsletterPreview:
    """Obtiene noticias para el usuario sin modificar preferencias ni datos locales."""
    preference = Preferences.objects.filter(user=user).first()
    selected_topics = tuple(preference.newsletter_topics) if preference else ()
    newsletter_enabled = preference.newsletter_enabled if preference else False
    timezone_name = preference.timezone_name if preference else settings.TIME_ZONE
    warnings: list[str] = []

    try:
        user_timezone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError):
        user_timezone = ZoneInfo(settings.TIME_ZONE)
        timezone_name = settings.TIME_ZONE
        warnings.append(
            "La zona horaria guardada no es válida; se muestra la zona "
            f"predeterminada {timezone_name}."
        )

    current_time = generated_at or timezone.now()
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("La fecha de generación debe incluir una zona horaria.")
    local_generated_at = current_time.astimezone(user_timezone)

    if not selected_topics:
        return NewsletterPreview(
            generated_at=local_generated_at,
            timezone_name=timezone_name,
            newsletter_enabled=newsletter_enabled,
            selected_topics=(),
            articles=(),
            warnings=tuple(warnings),
            has_selected_topics=False,
            matched_source_count=0,
        )

    source_topics = {
        FEED_TOPIC_BY_PREFERENCE[topic]
        for topic in selected_topics
        if topic in FEED_TOPIC_BY_PREFERENCE
    }
    try:
        configured_sources = load_sources(FEEDS_PATH)
    except FeedConfigError as error:
        warnings.append(f"No se pudo cargar la configuración de fuentes: {error}")
        configured_sources = []

    selected_sources: list[FeedSource] = []
    seen_urls: set[str] = set()
    for source in configured_sources:
        if source.topic not in source_topics or source.url in seen_urls:
            continue
        selected_sources.append(source)
        seen_urls.add(source.url)

    news_items, feed_warnings = fetch_news(selected_sources)
    warnings.extend(feed_warnings)
    articles = tuple(
        NewsletterArticle(
            title=item.title,
            source=item.source,
            published=_localized_date(item, user_timezone),
            link=item.link,
            topic=item.topic,
            topic_code=PREFERENCE_BY_FEED_TOPIC.get(item.topic, ""),
            summary=item.summary,
            image_url=item.image_url if _is_http_url(item.image_url or "") else None,
        )
        for item in news_items
        if _is_http_url(item.link)
    )[:MAX_NEWS_ITEMS]

    return NewsletterPreview(
        generated_at=local_generated_at,
        timezone_name=timezone_name,
        newsletter_enabled=newsletter_enabled,
        selected_topics=selected_topics,
        articles=articles,
        warnings=tuple(warnings),
        has_selected_topics=True,
        matched_source_count=len(selected_sources),
    )


def get_user_news_page(
    user: User,
    selected_filter: str = "",
    preview: NewsletterPreview | None = None,
) -> NewsPage:
    """Build the same topic-filtered news page for Django and Angular."""
    if preview is None:
        preview = get_user_newsletter_preview(user)
    topic_labels = dict(TOPIC_CHOICES)
    topic_filters = tuple(
        {"code": code, "label": topic_labels[code]}
        for code in preview.selected_topics
        if code in FEED_TOPIC_BY_PREFERENCE
    )
    valid_filters = {topic["code"] for topic in topic_filters}
    active_topic = selected_filter if selected_filter in valid_filters else ""
    articles = tuple(
        article
        for article in preview.articles
        if not active_topic or article.topic_code == active_topic
    )
    return NewsPage(
        preview=preview,
        articles=articles,
        topic_filters=topic_filters,
        active_topic=active_topic,
        selected_topic_label=topic_labels.get(active_topic, ""),
    )
