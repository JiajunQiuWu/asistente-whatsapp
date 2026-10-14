"""Operaciones de persistencia para las tareas."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "tasks.db"


@dataclass(frozen=True)
class Task:
    id: int
    title: str


def _connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(database_path)


def initialize_database(database_path: Path = DATABASE_PATH) -> None:
    with closing(_connect(database_path)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                completed INTEGER NOT NULL DEFAULT 0
                    CHECK (completed IN (0, 1))
            )
            """
        )


def add_task(title: str, database_path: Path = DATABASE_PATH) -> int:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("El texto de la tarea no puede estar vacío.")

    initialize_database(database_path)
    with closing(_connect(database_path)) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO tasks (title) VALUES (?)",
            (title.strip(),),
        )
        return cursor.lastrowid


def list_pending_tasks(database_path: Path = DATABASE_PATH) -> list[Task]:
    initialize_database(database_path)
    with closing(_connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT id, title FROM tasks WHERE completed = ? ORDER BY id",
            (0,),
        ).fetchall()
    return [Task(id=row[0], title=row[1]) for row in rows]


def complete_task(task_id: int, database_path: Path = DATABASE_PATH) -> bool:
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id <= 0:
        raise ValueError("El ID debe ser un número entero positivo.")

    initialize_database(database_path)
    with closing(_connect(database_path)) as connection, connection:
        cursor = connection.execute(
            "UPDATE tasks SET completed = ? WHERE id = ? AND completed = ?",
            (1, task_id, 0),
        )
        return cursor.rowcount == 1
