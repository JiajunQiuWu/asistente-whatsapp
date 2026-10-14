"""Carga y lectura de feeds RSS 2.0 y Atom con la biblioteca estándar."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

FEED_TIMEOUT_SECONDS = 10


class FeedConfigError(ValueError):
    """La configuración de fuentes no tiene la estructura esperada."""


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    topic: str


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    topic: str
    published: str | None
    published_at: datetime | None
    link: str


DEMO_NEWS = (
    NewsItem(
        title="[FICTICIA] Ciudad Ejemplo prueba autobuses eléctricos autónomos.",
        source="DEMO (ficticia)",
        topic="Tecnología",
        published=None,
        published_at=None,
        link="https://example.invalid/demo/tecnologia",
    ),
    NewsItem(
        title="[FICTICIA] El Banco Imaginario presenta una moneda de prueba.",
        source="DEMO (ficticia)",
        topic="Economía",
        published=None,
        published_at=None,
        link="https://example.invalid/demo/economia",
    ),
    NewsItem(
        title="[FICTICIA] La isla inventada inaugura un observatorio marino.",
        source="DEMO (ficticia)",
        topic="Actualidad",
        published=None,
        published_at=None,
        link="https://example.invalid/demo/actualidad",
    ),
    NewsItem(
        title="[FICTICIA] Un equipo escolar cultiva plantas en un laboratorio.",
        source="DEMO (ficticia)",
        topic="Ciencia",
        published=None,
        published_at=None,
        link="https://example.invalid/demo/ciencia",
    ),
    NewsItem(
        title="[FICTICIA] El tranvía de Villa Modelo amplía su recorrido.",
        source="DEMO (ficticia)",
        topic="Comunidad",
        published=None,
        published_at=None,
        link="https://example.invalid/demo/comunidad",
    ),
)


def _validate_url(url: object, index: int) -> str:
    if not isinstance(url, str) or not url.strip():
        raise FeedConfigError(f"La fuente {index} debe tener una URL.")

    cleaned_url = url.strip()
    try:
        parsed = urlsplit(cleaned_url)
        port = parsed.port
        valid_authority = (
            parsed.hostname is not None
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError as error:
        raise FeedConfigError(f"La URL de la fuente {index} no es válida.") from error

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not valid_authority
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise FeedConfigError(
            f"La URL de la fuente {index} debe ser HTTP o HTTPS y tener un host válido."
        )
    return cleaned_url


def load_sources(config_path: Path) -> list[FeedSource]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FeedConfigError(
            f"No se pudo leer {config_path}: {error}"
        ) from error

    if not isinstance(config, list):
        raise FeedConfigError("El archivo debe contener una lista de fuentes.")

    sources: list[FeedSource] = []
    for index, entry in enumerate(config, start=1):
        if not isinstance(entry, dict):
            raise FeedConfigError(f"La fuente {index} debe ser un objeto JSON.")
        name = entry.get("name")
        topic = entry.get("topic")
        if not isinstance(name, str) or not name.strip():
            raise FeedConfigError(f"La fuente {index} debe tener un nombre.")
        if not isinstance(topic, str) or not topic.strip():
            raise FeedConfigError(f"La fuente {index} debe tener un tema.")
        sources.append(
            FeedSource(
                name=name.strip(),
                url=_validate_url(entry.get("url"), index),
                topic=topic.strip(),
            )
        )
    return sources


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, child_name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == child_name:
            text = "".join(child.itertext()).strip()
            return text or None
    return None


def _date_value(value: str | None) -> tuple[str | None, datetime | None]:
    if not value:
        return None, None

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value, None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return value, parsed.astimezone(timezone.utc)


def _rss_link(item: ET.Element) -> str | None:
    return _child_text(item, "link")


def _atom_link(entry: ET.Element) -> str | None:
    links = [child for child in entry if _local_name(child.tag) == "link"]
    for link in links:
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href", "").strip() or None
    for link in links:
        if link.get("href"):
            return link.get("href", "").strip() or None
    return None


def _make_item(
    entry: ET.Element,
    source: FeedSource,
    link: str | None,
    date_value: str | None,
) -> NewsItem | None:
    title = _child_text(entry, "title")
    if not title or not link:
        return None
    published, published_at = _date_value(date_value)
    return NewsItem(
        title=title,
        source=source.name,
        topic=source.topic,
        published=published,
        published_at=published_at,
        link=link,
    )


def parse_feed(content: bytes, source: FeedSource) -> list[NewsItem]:
    root = ET.fromstring(content)
    root_name = _local_name(root.tag)
    if root_name == "rss":
        channel = next(
            (child for child in root if _local_name(child.tag) == "channel"),
            None,
        )
        if channel is None:
            raise ValueError("El RSS no contiene un canal.")
        elements = [child for child in channel if _local_name(child.tag) == "item"]
        items = [
            _make_item(
                element,
                source,
                _rss_link(element),
                _child_text(element, "pubDate"),
            )
            for element in elements
        ]
    elif root_name == "feed":
        entries = [child for child in root if _local_name(child.tag) == "entry"]
        items = [
            _make_item(
                entry,
                source,
                _atom_link(entry),
                _child_text(entry, "published") or _child_text(entry, "updated"),
            )
            for entry in entries
        ]
    else:
        raise ValueError("Formato no compatible: se esperaba RSS 2.0 o Atom.")
    return [item for item in items if item is not None]


def _sort_key(item: NewsItem) -> tuple[bool, float]:
    if item.published_at is None:
        return True, 0
    return False, -item.published_at.timestamp()


def fetch_news(sources: list[FeedSource]) -> tuple[list[NewsItem], list[str]]:
    items_by_link: dict[str, NewsItem] = {}
    warnings: list[str] = []

    for source in sources:
        try:
            _validate_url(source.url, 1)
            request = Request(
                source.url,
                headers={"User-Agent": "AsistentePersonal/1.0 (RSS reader)"},
            )
            with urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
                items = parse_feed(response.read(), source)
        except (URLError, TimeoutError, OSError, ET.ParseError, ValueError) as error:
            warnings.append(f"No se pudo consultar {source.name}: {error}")
            continue

        for item in items:
            items_by_link.setdefault(item.link, item)

    return sorted(items_by_link.values(), key=_sort_key), warnings
