import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from zoneinfo import ZoneInfo

from app.briefing import build_briefing
from app.email_sender import build_briefing_email, format_email_preview
from app.news import DEMO_NEWS
from app.tasks import Task, add_task, list_pending_tasks

FIXED_TIME = datetime(2026, 10, 15, 7, 30, tzinfo=timezone.utc)


class BriefingTests(unittest.TestCase):
    def test_builds_localized_briefing_with_up_to_five_items(self) -> None:
        news_items = (*DEMO_NEWS, DEMO_NEWS[0])
        tasks = tuple(Task(id=index, title=f"Tarea {index}") for index in range(1, 7))

        briefing = build_briefing(news_items, tasks, FIXED_TIME)

        self.assertIn(
            "jueves, 15 de octubre de 2026, 09:30 (Europe/Madrid)",
            briefing,
        )
        self.assertEqual(briefing.count("   Enlace:"), 5)
        self.assertEqual(briefing.count("- Tarea "), 5)
        self.assertIn("[FICTICIA]", briefing)
        self.assertIn("Fuente: DEMO (ficticia)", briefing)

    def test_reports_empty_news_and_task_states(self) -> None:
        briefing = build_briefing([], [], FIXED_TIME)

        self.assertIn("No hay noticias disponibles.", briefing)
        self.assertIn("No hay tareas pendientes.", briefing)

    def test_generating_briefing_does_not_change_stored_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "tasks.db"
            add_task("Conservar esta tarea", database_path)
            before = list_pending_tasks(database_path)

            build_briefing(DEMO_NEWS, before, FIXED_TIME)

            after = list_pending_tasks(database_path)
            self.assertEqual(after, before)

    def test_demo_command_does_not_read_or_modify_real_tasks(self) -> None:
        from app import __main__ as application

        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "briefing", "--demo"]),
            patch.object(
                application, "list_pending_tasks", side_effect=AssertionError
            ) as list_tasks,
            patch.object(
                application, "load_sources", side_effect=AssertionError
            ) as load_sources,
            patch.object(
                application, "fetch_news", side_effect=AssertionError
            ) as fetch_news,
            patch.object(application, "add_task", side_effect=AssertionError) as add,
            patch.object(
                application, "complete_task", side_effect=AssertionError
            ) as complete,
            redirect_stdout(output),
        ):
            self.assertEqual(application.main(), 0)

        self.assertIn("MODO DEMO", output.getvalue())
        self.assertIn("[FICTICIA]", output.getvalue())
        self.assertIn("[DEMO] Preparar una lista de compras.", output.getvalue())
        list_tasks.assert_not_called()
        load_sources.assert_not_called()
        fetch_news.assert_not_called()
        add.assert_not_called()
        complete.assert_not_called()

    def test_email_message_uses_subject_and_reused_briefing_content(self) -> None:
        message = build_briefing_email(
            DEMO_NEWS,
            [Task(id=1, title="[DEMO] Comprobar el contenido.")],
        )

        self.assertEqual(message["Subject"], "Boletín personal")
        self.assertEqual(message.get_content_type(), "text/plain")
        self.assertIn("BOLETÍN PERSONAL", message.get_content())
        self.assertIn("[FICTICIA]", message.get_content())
        self.assertIn("[DEMO] Comprobar el contenido.", message.get_content())
        self.assertIn(
            "Vista previa: no se ha enviado ningún correo",
            format_email_preview(message),
        )

    def test_email_demo_command_does_not_access_real_data(self) -> None:
        from app import __main__ as application

        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email", "--demo"]),
            patch.object(
                application, "list_pending_tasks", side_effect=AssertionError
            ) as list_tasks,
            patch.object(
                application, "load_sources", side_effect=AssertionError
            ) as load_sources,
            patch.object(
                application, "fetch_news", side_effect=AssertionError
            ) as fetch_news,
            patch.object(application, "add_task", side_effect=AssertionError) as add,
            patch.object(
                application, "complete_task", side_effect=AssertionError
            ) as complete,
            redirect_stdout(output),
        ):
            self.assertEqual(application.main(), 0)

        preview = output.getvalue()
        self.assertIn("Vista previa: no se ha enviado ningún correo", preview)
        self.assertIn("Asunto: Boletín personal", preview)
        self.assertIn("[FICTICIA]", preview)
        self.assertIn("[DEMO] Preparar una lista de compras.", preview)
        list_tasks.assert_not_called()
        load_sources.assert_not_called()
        fetch_news.assert_not_called()
        add.assert_not_called()
        complete.assert_not_called()

    def test_briefing_keeps_tasks_when_a_feed_fails(self) -> None:
        from app import __main__ as application

        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            database_path = temp_dir / "tasks.db"
            feeds_path = temp_dir / "feeds.json"
            feed_url = "https://feeds.example.test/news.xml"
            feed_name = "Feed local de prueba"
            add_task("Terminar el informe", database_path)
            feeds_path.write_text(
                json.dumps(
                    [
                        {
                            "name": feed_name,
                            "url": feed_url,
                            "topic": "Pruebas",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            errors = io.StringIO()
            with (
                patch.object(sys, "argv", ["app", "briefing"]),
                patch.object(application, "FEEDS_PATH", feeds_path),
                patch.object(
                    application,
                    "list_pending_tasks",
                    side_effect=lambda: list_pending_tasks(database_path),
                ),
                patch(
                    "app.news.urlopen",
                    side_effect=URLError("fallo de red simulado"),
                ) as urlopen,
                redirect_stdout(output),
                redirect_stderr(errors),
            ):
                self.assertEqual(application.main(), 0)

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)
        self.assertIn(feed_url, urlopen.call_args.args[0].full_url)
        self.assertIn(feed_name, errors.getvalue())
        self.assertIn("fallo de red simulado", errors.getvalue())
        self.assertIn("Terminar el informe", output.getvalue())
        self.assertNotIn("No hay tareas pendientes.", output.getvalue())

    def test_naive_generation_datetime_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_briefing([], [], datetime(2026, 10, 15, 9, 30))

    def test_generated_time_uses_madrid_offset(self) -> None:
        madrid_time = datetime(2026, 10, 15, 9, 30, tzinfo=ZoneInfo("Europe/Madrid"))
        briefing = build_briefing([], [], madrid_time)
        self.assertIn("jueves, 15 de octubre de 2026, 09:30", briefing)


if __name__ == "__main__":
    unittest.main()
