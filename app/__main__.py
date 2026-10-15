"""Punto de entrada de la aplicación: python -m app."""

import argparse
import sys
from pathlib import Path

from app.briefing import TimezoneDataError, build_briefing
from app.email_sender import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailConnectionError,
    build_briefing_email,
    format_email_preview,
    load_email_settings,
    send_email,
)
from app.news import (
    DEMO_NEWS,
    FeedConfigError,
    fetch_news,
    load_sources,
)
from app.tasks import Task, add_task, complete_task, list_pending_tasks

FEEDS_PATH = Path(__file__).resolve().parent.parent / "data" / "feeds.json"


def positive_integer(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("debe ser un número entero") from error
    if limit <= 0:
        raise argparse.ArgumentTypeError("debe ser un entero positivo")
    return limit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gestiona tareas pendientes y consulta noticias RSS/Atom."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add_parser = commands.add_parser("add", help="Añadir una tarea")
    add_parser.add_argument("title", help="Texto de la tarea")

    commands.add_parser("list", help="Listar tareas pendientes")

    complete_parser = commands.add_parser(
        "complete", help="Completar una tarea por su ID"
    )
    complete_parser.add_argument("id", type=int, help="ID de la tarea")

    news_parser = commands.add_parser("news", help="Consultar noticias RSS/Atom")
    news_parser.add_argument(
        "--limit",
        type=positive_integer,
        default=5,
        help="Número máximo de noticias (por defecto: 5)",
    )
    news_parser.add_argument(
        "--demo",
        action="store_true",
        help="Mostrar ejemplos ficticios sin conexión",
    )

    briefing_parser = commands.add_parser(
        "briefing", help="Generar un boletín de noticias y tareas"
    )
    briefing_parser.add_argument(
        "--demo",
        action="store_true",
        help="Usar noticias y tareas de ejemplo sin consultar datos reales",
    )

    email_parser = commands.add_parser(
        "email", help="Previsualizar el boletín como correo de texto plano"
    )
    email_parser.add_argument(
        "--demo",
        action="store_true",
        help="Usar noticias y tareas de ejemplo sin consultar datos reales",
    )
    email_parser.add_argument(
        "--send",
        action="store_true",
        help="Enviar el correo mediante Gmail SMTP",
    )

    args = parser.parse_args()

    try:
        if args.command == "add":
            task_id = add_task(args.title)
            print(f"Tarea añadida con ID {task_id}.")
        elif args.command == "list":
            tasks = list_pending_tasks()
            if not tasks:
                print("No hay tareas pendientes.")
            else:
                for task in tasks:
                    print(f"{task.id}: {task.title}")
        elif args.command == "complete":
            if complete_task(args.id):
                print(f"Tarea {args.id} completada.")
            else:
                print(
                    "No hay una tarea pendiente con ese ID "
                    "(puede que no exista o ya esté completada)."
                )
        elif args.command == "news":
            if args.demo:
                print("MODO DEMO: las siguientes noticias son ficticias.")
                for item in DEMO_NEWS[: args.limit]:
                    print(f"\n{item.title}")
                    print(f"Fuente: {item.source} | Tema: {item.topic}")
                    print(f"Enlace: {item.link}")
            else:
                sources = load_sources(FEEDS_PATH)
                items, warnings = fetch_news(sources)
                for warning in warnings:
                    print(f"Aviso: {warning}", file=sys.stderr)
                if not items:
                    print("No hay noticias disponibles.")
                else:
                    for item in items[: args.limit]:
                        print(f"\n{item.title}")
                        print(f"Fuente: {item.source} | Tema: {item.topic}")
                        if item.published:
                            print(f"Fecha: {item.published}")
                        print(f"Enlace: {item.link}")
        elif args.command == "briefing":
            if args.demo:
                news_items = DEMO_NEWS
                pending_tasks = (
                    Task(id=1, title="[DEMO] Preparar una lista de compras."),
                    Task(id=2, title="[DEMO] Leer un artículo pendiente."),
                )
            else:
                sources = load_sources(FEEDS_PATH)
                news_items, warnings = fetch_news(sources)
                for warning in warnings:
                    print(f"Aviso: {warning}", file=sys.stderr)
                pending_tasks = list_pending_tasks()
            if args.demo:
                print("MODO DEMO: las noticias y tareas son ficticias.")
            print(build_briefing(news_items, pending_tasks))
        elif args.command == "email":
            email_settings = load_email_settings() if args.send else None
            if args.demo:
                news_items = DEMO_NEWS
                pending_tasks = (
                    Task(id=1, title="[DEMO] Preparar una lista de compras."),
                    Task(id=2, title="[DEMO] Leer un artículo pendiente."),
                )
                print("MODO DEMO: las noticias y tareas son ficticias.")
            elif not args.send:
                news_items = []
                pending_tasks = list_pending_tasks()
            else:
                sources = load_sources(FEEDS_PATH)
                news_items, warnings = fetch_news(sources)
                for warning in warnings:
                    print(f"Aviso: {warning}", file=sys.stderr)
                pending_tasks = list_pending_tasks()
            message = build_briefing_email(
                news_items,
                pending_tasks,
                sender=email_settings.sender if email_settings else None,
                recipient=email_settings.recipient if email_settings else None,
            )
            if email_settings is None:
                print(format_email_preview(message))
            else:
                send_email(message, email_settings)
                print(
                    "Gmail aceptó el mensaje para su envío; "
                    "esto no garantiza que llegue a la bandeja de entrada."
                )
    except FeedConfigError as error:
        print(f"Error en la configuración de feeds: {error}", file=sys.stderr)
        return 2
    except EmailConfigurationError as error:
        print(f"Error de configuración de correo: {error}", file=sys.stderr)
        return 2
    except EmailAuthenticationError as error:
        print(f"Error de autenticación: {error}", file=sys.stderr)
        return 3
    except EmailConnectionError as error:
        print(f"Error de conexión o envío: {error}", file=sys.stderr)
        return 4
    except TimezoneDataError as error:
        print(f"Error de zona horaria: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
