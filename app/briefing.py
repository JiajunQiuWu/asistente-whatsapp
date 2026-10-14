"""Construcción de boletines en texto plano a partir de noticias y tareas."""

from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.news import NewsItem
from app.tasks import Task

MAX_BRIEFING_ITEMS = 5
MADRID_TIMEZONE = "Europe/Madrid"
WEEKDAYS_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


class TimezoneDataError(RuntimeError):
    """No están instalados los datos de zona horaria necesarios."""


def _format_madrid_datetime(value: datetime | None) -> str:
    try:
        madrid_timezone = ZoneInfo(MADRID_TIMEZONE)
    except ZoneInfoNotFoundError as error:
        raise TimezoneDataError(
            "No se encontraron los datos horarios de Europe/Madrid. "
            "Instálalos con: python -m pip install -r requirements.txt"
        ) from error

    timestamp = value if value is not None else datetime.now(madrid_timezone)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("La fecha de generación debe incluir una zona horaria.")
    local_time = timestamp.astimezone(madrid_timezone)
    weekday = WEEKDAYS_ES[local_time.weekday()]
    month = MONTHS_ES[local_time.month - 1]
    return (
        f"{weekday}, {local_time.day} de {month} de {local_time.year}, "
        f"{local_time:%H:%M} ({MADRID_TIMEZONE})"
    )


def build_briefing(
    news_items: Sequence[NewsItem],
    pending_tasks: Sequence[Task],
    generated_at: datetime | None = None,
) -> str:
    """Devuelve un boletín en texto plano sin imprimir ni modificar los datos."""
    lines = [
        "BOLETÍN PERSONAL",
        f"Fecha y hora: {_format_madrid_datetime(generated_at)}",
        "",
        "NOTICIAS",
    ]

    selected_news = news_items[:MAX_BRIEFING_ITEMS]
    if selected_news:
        for index, item in enumerate(selected_news, start=1):
            lines.extend(
                (
                    f"{index}. {item.title}",
                    f"   Fuente: {item.source}",
                    f"   Enlace: {item.link}",
                )
            )
    else:
        lines.append("No hay noticias disponibles.")

    lines.extend(("", "TAREAS PENDIENTES"))
    selected_tasks = pending_tasks[:MAX_BRIEFING_ITEMS]
    if selected_tasks:
        lines.extend(f"- {task.title}" for task in selected_tasks)
    else:
        lines.append("No hay tareas pendientes.")

    return "\n".join(lines)
