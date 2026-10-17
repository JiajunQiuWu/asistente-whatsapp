# Gestor de tareas

Aplicación de terminal para guardar tareas pendientes en SQLite y consultar
noticias de feeds RSS 2.0 o Atom. El código usa la biblioteca estándar de
Python; el boletín requiere `tzdata` en Windows cuando el sistema no incluye
datos de zona horaria.

El proyecto incluye además una aplicación web Django local en desarrollo para
registro, inicio de sesión y preferencias individuales. No es un despliegue de
producción ni envía boletines o alertas.

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
python -m app email-config
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
contraseña de aplicación de Gmail. Para guardarla en el Administrador de
credenciales de Windows, configura primero la dirección de la cuenta y ejecuta
el comando:

```powershell
$env:GMAIL_ADDRESS = "tu-cuenta@gmail.com"
$env:EMAIL_TO = "destinatario@ejemplo.com"
python -m app email-config
```

La contraseña se solicita de forma oculta y se guarda con `keyring`, usando el
servicio `asistente-whatsapp.gmail` y la dirección remitente como usuario. No se
escribe en un archivo. En el envío, el programa busca primero
`GMAIL_APP_PASSWORD`, después el Administrador de credenciales de Windows y,
si el almacén está disponible pero no hay una contraseña guardada, la solicita
de forma oculta. Si el almacén seguro no está disponible, informa del error y
no recurre a un almacenamiento en texto plano.

Para entornos automatizados, `--non-interactive` evita solicitar la contraseña.
Configura `GMAIL_APP_PASSWORD` en el entorno o guarda previamente la credencial
con `email-config`:

```powershell
python -m app email --send
python -m app email --send --non-interactive
python -m app email --demo --send
python -m app email --demo --send --non-interactive
```

El primer comando prepara el boletín con noticias de los feeds y tareas
pendientes reales. El segundo prepara solo contenido ficticio, pero **sí envía
un correo** al destinatario configurado. No ejecutamos estos comandos al probar
el proyecto. La conexión usa SMTP de Gmail con STARTTLS. Si Gmail acepta el
mensaje, la aplicación lo informa, pero esto no garantiza su llegada a la
bandeja de entrada. No hay reintentos.

La vista previa `python -m app email` no consulta credenciales. El comando
`email-config` configura una contraseña de aplicación, pero no envía correos.
No se implementa todavía el envío diario.

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
python web\manage.py test accounts
```

## Aplicación web local

El sitio web está separado de la CLI: `web\manage.py` es su punto de entrada,
`web\config` contiene la configuración y rutas del proyecto, y `web\accounts`
implementa autenticación y preferencias. Usa `web\db.sqlite3`, independiente de
`data\tasks.db`; no migra las tareas de terminal ni envía correo.

La dependencia del entorno es Django 6.1.2, comprobada con Python 3.14. Para
instalar o actualizar las dependencias desde PowerShell, en la raíz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

El modelo `accounts.User` basado en `AbstractUser` y el modelo de preferencias
ya están incluidos en la migración inicial. Ejecuta las migraciones:

```powershell
.\.venv\Scripts\python.exe web\manage.py migrate
```

Crea un usuario administrador para `/admin/`:

```powershell
.\.venv\Scripts\python.exe web\manage.py createsuperuser
```

Opcionalmente, antes de arrancar, genera y asigna una clave de desarrollo en
esta sesión de PowerShell:

```powershell
$env:DJANGO_SECRET_KEY = (& .\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
```

Arranca el servidor **solo en la interfaz local**, desde la raíz:

```powershell
.\.venv\Scripts\python.exe web\manage.py runserver 127.0.0.1:8000
```

Abre `http://127.0.0.1:8000/`. Puedes registrarte desde la página; después del
registro se te redirige al login y aparece el aviso «Cuenta creada correctamente.
Ya puedes iniciar sesión». Al guardar preferencias también se muestra una
confirmación. Los errores de validación aparecen junto al campo correspondiente;
las contraseñas no se vuelven a rellenar si el registro falla.
Administra usuarios y preferencias en `http://127.0.0.1:8000/admin/`.

La interfaz comparte una plantilla base y estilos locales en
`web\accounts\templates\accounts` y `web\accounts\static\accounts\css\site.css`.
Incluye formularios adaptables a móvil y escritorio; las preferencias se
presentan en bloques de boletín, temas y alertas. El sitio se identifica como
versión local en desarrollo y no envía correos ni alertas.

Pruebas de Django:

```powershell
.\.venv\Scripts\python.exe web\manage.py test accounts
```

La base de datos web, archivos `.env*` y configuración local se excluyen de
Git. `DEBUG` está habilitado y la clave de respaldo de settings es solo para
desarrollo: no expongas este servidor ni uses esta configuración en producción.
No hay recuperación ni verificación por correo, tareas programadas, alertas
reales ni integración con WhatsApp.
