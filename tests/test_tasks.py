import tempfile
import unittest
from pathlib import Path

from app.tasks import add_task, complete_task, list_pending_tasks


class TaskStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "data" / "tasks.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_tasks_persist_and_completed_tasks_are_not_pending(self) -> None:
        task_id = add_task("  Comprar leche  ", self.database_path)

        reopened_tasks = list_pending_tasks(self.database_path)

        self.assertEqual([(task.id, task.title) for task in reopened_tasks], [
            (task_id, "Comprar leche")
        ])
        self.assertTrue(complete_task(task_id, self.database_path))
        self.assertEqual(list_pending_tasks(self.database_path), [])

    def test_add_rejects_blank_title(self) -> None:
        for title in ("", "   "):
            with self.subTest(title=title):
                with self.assertRaises(ValueError):
                    add_task(title, self.database_path)

    def test_complete_rejects_invalid_id(self) -> None:
        for task_id in (0, -1, True, "1"):
            with self.subTest(task_id=task_id):
                with self.assertRaises(ValueError):
                    complete_task(task_id, self.database_path)

    def test_complete_returns_false_for_missing_or_already_completed_task(self) -> None:
        self.assertFalse(complete_task(1, self.database_path))
        task_id = add_task("Llamar", self.database_path)
        self.assertTrue(complete_task(task_id, self.database_path))
        self.assertFalse(complete_task(task_id, self.database_path))


if __name__ == "__main__":
    unittest.main()
