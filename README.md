# Gestor de tareas

Primera etapa del asistente personal: una aplicación de terminal para guardar
tareas pendientes en SQLite. Usa solo la biblioteca estándar de Python.

## Requisitos

- Windows
- Python 3.14
- El entorno virtual `.venv` del proyecto

## Preparación

Abre PowerShell en la carpeta del proyecto y activa el entorno:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell impide activar el entorno, puedes llamar directamente al
intérprete del entorno en los comandos de abajo sustituyendo `python` por
`.\.venv\Scripts\python.exe`.

## Uso

Ejecuta los comandos desde la carpeta del proyecto:

```powershell
python -m app add "Preparar presentación"
python -m app list
python -m app complete 1
python -m app list
```

`add` muestra el ID asignado a la tarea. `list` solo muestra tareas pendientes.
`complete` recibe el ID que mostró `add`; un ID no entero se rechaza y un ID
inválido o que no corresponda a una tarea pendiente no modifica los datos.

La base de datos se crea automáticamente en `data/tasks.db` al ejecutar por
primera vez cualquiera de los comandos.

## Persistencia

Las tareas permanecen guardadas al cerrar la aplicación porque se almacenan en
`data/tasks.db`. Para comprobarlo, añade una tarea, cierra la terminal, abre
otra en la carpeta del proyecto y ejecuta `python -m app list`: la tarea seguirá
apareciendo hasta que la completes.

## Pruebas

Desde la carpeta del proyecto, ejecuta las pruebas con el entorno activado:

```powershell
python -m unittest discover -s tests -v
```
