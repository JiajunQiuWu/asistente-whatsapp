# Gestor de tareas

Aplicación de terminal para guardar tareas pendientes en SQLite y consultar
noticias de feeds RSS 2.0 o Atom. El código usa la biblioteca estándar de
Python; el boletín requiere `tzdata` en Windows cuando el sistema no incluye
datos de zona horaria.

## Requisitos

- Windows
- Python 3.14
- El entorno virtual `.venv` del proyecto

## Preparación

Abre PowerShell en la carpeta del proyecto y activa el entorno:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
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
python -m app news
python -m app news --limit 10
python -m app news --demo
python -m app briefing
python -m app briefing --demo
python -m app email --demo
python -m app email --demo --send
```

`add` muestra el ID asignado a la tarea. `list` solo muestra tareas pendientes.
`complete` recibe el ID que mostró `add`; un ID no entero se rechaza y un ID
inválido o que no corresponda a una tarea pendiente no modifica los datos.

La base de datos se crea automáticamente en `data/tasks.db` al ejecutar por
primera vez cualquiera de los comandos.

## Noticias

El comando `news` consulta los feeds configurados en `data/feeds.json`. Muestra
hasta cinco noticias por defecto; `--limit` acepta un entero positivo. Solo se
imprimen los datos disponibles del feed: título, fuente, tema, fecha cuando
existe y enlace. Los elementos sin fecha aparecen al final y no se les asigna
una fecha inventada. Los feeds que fallen producen un aviso y no impiden leer
las otras fuentes.

La configuración inicial contiene feeds RSS públicos de BBC News para
tecnología, economía (sección Business) y actualidad internacional. Si quieres
añadir fuentes, edita `data/feeds.json` y agrega objetos con esta forma:

```json
{
  "name": "Nombre de la fuente",
  "url": "https://ejemplo.com/feed.xml",
  "topic": "Tecnología"
}
```

Cada objeto debe incluir nombre, URL HTTP o HTTPS y tema. Para probar la
presentación sin conexión, `python -m app news --demo` muestra ejemplos
marcados explícitamente como ficticios; no consulta la red.

## Boletín

`python -m app briefing` genera un boletín en texto con la fecha y hora de
`Europe/Madrid`, hasta cinco noticias y hasta cinco tareas pendientes. Los
artículos incluyen título, fuente y enlace; si no hay noticias o tareas, el
boletín lo indica. Generarlo solo consulta las tareas y no las modifica.

`python -m app briefing --demo` usa noticias y tareas de ejemplo, claramente
identificadas, sin acceder a la base de datos real ni a Internet. La función
`build_briefing` de `app/briefing.py` construye y devuelve el texto sin
imprimirlo, para que pueda reutilizarse desde otra interfaz.

## Vista previa de correo

`python -m app email` crea un correo de texto plano con el asunto "Boletín
personal" y muestra el asunto y el cuerpo en la terminal. Sin `--send`, el
programa no consulta Internet ni abre una conexión SMTP. Para mantener la vista
previa offline, no incluye noticias; sí consulta las tareas pendientes locales.

`python -m app email --demo` muestra la vista previa con noticias y tareas
ficticias. No consulta Internet ni accede a la base de datos real.

## Envío por Gmail

El envío solo ocurre al añadir `--send`. Antes, configura estas variables de
entorno en la sesión de PowerShell:

```powershell
$env:GMAIL_ADDRESS = "tu-cuenta@gmail.com"
$env:EMAIL_TO = "destinatario@ejemplo.com"
```

La cuenta remitente debe tener habilitada la verificación en dos pasos y una
contraseña de aplicación de Gmail. Puedes definir `GMAIL_APP_PASSWORD` en el
entorno antes de ejecutar el programa; si no está definida, el programa la
solicita de forma oculta. No la escribas en el código ni la compartas.

```powershell
python -m app email --send
python -m app email --demo --send
```

El primer comando prepara el boletín con noticias de los feeds y tareas
pendientes reales. El segundo prepara solo contenido ficticio, pero **sí envía
un correo** al destinatario configurado. No ejecutamos estos comandos al probar
el proyecto. La conexión usa SMTP de Gmail con STARTTLS. Si Gmail acepta el
mensaje, la aplicación lo informa, pero esto no garantiza su llegada a la
bandeja de entrada. No hay reintentos.

En Windows, Python puede no tener instalados los datos de zonas horarias que
necesita `ZoneInfo`. Instala la dependencia desde la carpeta del proyecto:

```powershell
python -m pip install -r requirements.txt
```

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
