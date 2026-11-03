"""Obtención de la vista previa de noticias según las preferencias del usuario."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone

from app.news import FeedConfigError, FeedSource, NewsItem, fetch_news, load_sources

from .models import Preferences, User

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


@dataclass(frozen=True)
class NewsletterArticle:
    """Campos aptos para mostrar en HTML sin confiar en contenido de feeds."""

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
