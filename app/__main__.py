"""Punto de entrada de la aplicación: python -m app."""

import argparse
import sys

from app.tasks import add_task, complete_task, list_pending_tasks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Añade, consulta y completa tareas pendientes."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add_parser = commands.add_parser("add", help="Añadir una tarea")
    add_parser.add_argument("title", help="Texto de la tarea")

    commands.add_parser("list", help="Listar tareas pendientes")

    complete_parser = commands.add_parser(
        "complete", help="Completar una tarea por su ID"
    )
    complete_parser.add_argument("id", type=int, help="ID de la tarea")

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
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
