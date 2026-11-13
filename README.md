# Asistente personal de noticias y tareas

Proyecto en desarrollo que combina una aplicación web de noticias y boletines personalizados con una herramienta de tareas por terminal.

La **interfaz web está desarrollada en Angular** y se comunica con una **API Django**. Permite registrar usuarios, verificar su correo, iniciar sesión, elegir preferencias, consultar noticias RSS/Atom por tema y generar y enviar manualmente boletines por correo electrónico. Django gestiona sesiones, protección CSRF, validación, correo y administración.

La CLI de Python sigue disponible para gestionar tareas en SQLite y consultar noticias, pero sus tareas **no están integradas** con las cuentas de la web.

> **Estado:** desarrollo local. El repositorio no incluye un despliegue público listo para producción. La integración con WhatsApp, los envíos diarios automáticos y las alertas reales están pendientes.

## Inicio rápido: aplicación web

Necesitas Python 3.14, Node.js y npm, y un entorno virtual de Python. En PowerShell, desde la raíz del repositorio:

```powershell
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\.venv\\Scripts\\python.exe backend\\manage.py migrate
.\\.venv\\Scripts\\python.exe backend\\manage.py runserver localhost:8000
```

En una segunda terminal:

```powershell
Set-Location frontend
npm install
npm start
```

Abre **http://localhost:4200/**. La aplicación dirige a Noticias y solicita iniciar sesión cuando corresponde. Usa `localhost` en ambos servicios para que las cookies y la protección CSRF funcionen correctamente. Para configurar Gmail, verificar cuentas y ejecutar pruebas, consulta las secciones posteriores.

## Arquitectura y funcionalidades

| Componente | Función |
| --- | --- |
| `frontend/` | SPA Angular: autenticación, noticias, preferencias, boletín e historial |
| `backend/` | Django: API, usuarios, sesiones, CSRF, verificación de correo, RSS y envío manual |
| `app/` | CLI Python: tareas, noticias y boletines de terminal |
| `data/feeds.json` | Fuentes RSS/Atom y sus temas |

El correo de verificación usa enlaces firmados con caducidad. El envío manual exige correo verificado, se dirige a la dirección de la cuenta y tiene un límite de un intento cada cinco minutos. La aceptación del mensaje por SMTP no garantiza su entrega. La aplicación no programa envíos automáticos.

## Seguridad y publicación

**No publiques el servidor de desarrollo de Django en Internet.** Antes de desplegar, configura y verifica como mínimo:

- `DEBUG=False`, una `DJANGO_SECRET_KEY` secreta y persistente y `ALLOWED_HOSTS` limitado a tus dominios.
- HTTPS, cookies seguras, CSRF y proxy inverso correctamente configurados.
- `ANGULAR_FRONTEND_BASE_URL` con la URL pública real de Angular y enlaces de verificación bajo dominios controlados.
- Secretos SMTP fuera de Git, permisos mínimos y gestión segura de credenciales.
- Migraciones, archivos estáticos, copias de seguridad, registro de errores y pruebas de seguridad antes de admitir usuarios reales.

Se recomienda servir Angular y `/api/` bajo el mismo origen para simplificar cookies y CSRF. **Esta lista no certifica que el proyecto sea seguro para producción**; requiere una revisión de configuración, dependencias y despliegue.

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

Los comandos sin `--demo` preparan contenido real; los comandos con
`--demo` usan contenido ficticio. **Todos los ejemplos anteriores incluyen
`--send` y por tanto pueden enviar un correo real** al destinatario configurado. No ejecutamos estos comandos al probar
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
python backend\manage.py check
python backend\manage.py test accounts
```

## Aplicación web local

El backend Django está separado de la CLI: `backend\manage.py` es su punto de
entrada, `backend\config` contiene la configuración y rutas del proyecto, y
`backend\accounts` implementa autenticación, preferencias y boletines. Usa `backend\db.sqlite3`,
independiente de `data\tasks.db`; no migra ni consulta las tareas de terminal.

La dependencia del entorno es Django 6.1.2, comprobada con Python 3.14. Para
instalar o actualizar las dependencias desde PowerShell, en la raíz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

El modelo `accounts.User` basado en `AbstractUser` y el modelo de preferencias
están en la migración inicial. La migración de verificación añade el estado y
el envío de verificación, además de una restricción de unicidad de correo sin
distinguir mayúsculas/minúsculas. Comprueba los correos existentes y se detiene
mostrando las cuentas en conflicto; no borra ni combina usuarios. La migración
del envío manual añade el registro de intentos y el control de frecuencia; una
migración posterior añade estados para simulaciones y resultados inciertos.
Resuelve cualquier conflicto de correo manualmente y aplica las migraciones:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
```

Las cuentas previas conservan sus credenciales y quedan sin verificar. Los
correos vacíos de cuentas existentes se permiten para no impedir la migración;
el formulario de registro sí exige una dirección válida y única. La CLI y su
base `data\tasks.db` no se modifican.

Crea un usuario administrador para `/admin/`:

```powershell
.\.venv\Scripts\python.exe backend\manage.py createsuperuser
```

Opcionalmente, antes de arrancar, genera y asigna una clave de desarrollo en
esta sesión de PowerShell:

```powershell
$env:DJANGO_SECRET_KEY = (& .\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
```

En desarrollo Django imprime los correos de verificación en la consola y no
abre conexiones SMTP; esta es la opción predeterminada. Para elegir el backend
SMTP, reutiliza la cuenta Gmail y la contraseña que la CLI guarda en el
Administrador de credenciales de Windows. Gmail exige verificación en dos
pasos y una contraseña de aplicación. Desde la raíz del proyecto, configura la
cuenta y guarda la contraseña de forma oculta (este comando no envía correo):

```powershell
$env:GMAIL_ADDRESS = "tu-cuenta@gmail.com"
python -m app email-config
```

Después, en la misma sesión de PowerShell, activa SMTP de Django y arranca el
servidor:

```powershell
$env:DJANGO_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
$env:EMAIL_HOST = "smtp.gmail.com"
$env:EMAIL_PORT = "587"
$env:EMAIL_USE_TLS = "true"
$env:EMAIL_TIMEOUT = "10"
$env:EMAIL_HOST_USER = $env:GMAIL_ADDRESS
$env:DEFAULT_FROM_EMAIL = $env:GMAIL_ADDRESS
$env:EMAIL_VERIFICATION_BASE_URL = "http://localhost:8000"
.\.venv\Scripts\python.exe backend\manage.py runserver localhost:8000
```

El backend web reutiliza la recuperación segura de keyring de la CLI y nunca
solicita la contraseña interactivamente. También acepta `GMAIL_APP_PASSWORD` o
`EMAIL_HOST_PASSWORD` en el entorno, si ya utilizas esa opción; no la pongas en
un archivo ni la imprimas. Si el backend SMTP está seleccionado y no encuentra
la contraseña en el entorno ni en keyring, Django se detiene con un mensaje de
configuración claro. Gmail usa STARTTLS, puerto 587 y timeout de 10 segundos.
El origen de los enlaces se toma únicamente de
`EMAIL_VERIFICATION_BASE_URL`, no de la cabecera `Host`; usa una URL bajo tu
control. En local el valor predeterminado es `http://localhost:8000`. Los
registros y reenvíos desde Angular usan `ANGULAR_FRONTEND_BASE_URL` para
construir el enlace de la SPA. Django ya no renderiza pantallas de usuario:
ofrece la API, Admin y redirecciones temporales de compatibilidad.

Arranca el servidor **solo en la interfaz local**, desde la raíz:

```powershell
.\.venv\Scripts\python.exe backend\manage.py runserver localhost:8000
```

Administra usuarios y preferencias en `http://localhost:8000/admin/`.

La interfaz de usuario está en Angular (`frontend\`), mientras Django conserva
las sesiones, CSRF, validación de API, lógica de noticias y boletines, correo y
Admin. El envío manual requiere correo verificado, usa la dirección de la
sesión, limita cada cuenta a un intento cada cinco minutos y conserva los
estados de aceptado, simulación, fallo e incertidumbre. No activa el envío
automático ni consulta tareas de la CLI.

La configuración de fuentes se lee desde `data/feeds.json`, con una ruta
absoluta derivada del código, no del directorio actual. Los códigos `technology`,
`economy` e `international` se corresponden explícitamente con las etiquetas
`Tecnología`, `Economía` y `Actualidad` de las fuentes. Las preferencias IA y
ciencia todavía no tienen feeds configurados; temas y fuentes desconocidos se
omiten. Cada consulta usa el lector RSS/Atom compartido con la CLI, con espera
máxima de 10 segundos, límite de 1 MiB por respuesta y deduplicación de URL de
fuente dentro de la petición.

Pruebas:

Las pruebas Django usan feeds simulados y el backend de correo en memoria; no
necesitan Internet ni envían correos reales. Ejecuta también las pruebas de la
CLI para conservar la cobertura existente:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py test accounts
```

Las pruebas Django usan feeds y correo simulados; no envían mensajes reales.
Para comprobar la interfaz, inicia Angular y usa la API local según los pasos
de la sección siguiente.

La base de datos web, archivos `.env*` y configuración local se excluyen de
Git. `DEBUG` está habilitado y la clave de respaldo de settings es solo para
desarrollo: no expongas este servidor ni uses esta configuración en producción.
No hay recuperación de contraseña, cambio de correo desde la web, programación
diaria, alertas reales ni integración con WhatsApp.

## Interfaz Angular y API Django

La aplicación Angular standalone de `frontend\` es la interfaz de usuario. El
lockfile resuelve Angular 22.2.4, Angular CLI 22.2.6 y TypeScript 6.0.3; se
comprobó con Node 24.21.0 y npm 11.19.0. El frontend usa TypeScript estricto;
Django ofrece la API, Admin, SQLite, sesiones y la lógica de
autenticación/noticias. No hace falta configurar variables nuevas para el
desarrollo local ni cambiar el backend de correo.

Para desarrollo, inicia Django en una terminal desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py runserver localhost:8000
```

En otra terminal, instala las dependencias del frontend una vez e inicia Angular:

```powershell
Set-Location frontend
npm install
npm start
```

Abre **`http://localhost:4200/`**; la aplicación redirige a `/noticias` y
solicita el inicio de sesión si no hay una sesión Django activa. Usa `localhost`
en ambos servidores y en el navegador; no mezcles `localhost` con
`127.0.0.1`, ya que las cookies de sesión y CSRF se vinculan al nombre del
host. Angular envía sus llamadas relativas `/api/` mediante
`frontend\proxy.conf.json` a `http://localhost:8000`; su cliente HTTP obtiene
primero la cookie CSRF y envía `csrftoken` en la cabecera `X-CSRFToken`.
El proxy conserva el `Host` local del navegador para que Django pueda validar
el origen de Angular sin desactivar CSRF ni añadir otros orígenes confiables.

La API ofrece `GET /api/csrf/`, `GET /api/session/`, `POST /api/login/`,
`POST /api/logout/`, `GET /api/news/?tema=technology`, `POST /api/register/`,
`GET /api/verify-email/?token=...`, `POST /api/verify-email/confirm/`,
`GET /api/preferences/`, `POST /api/preferences/save/` y
`POST /api/preferences/resend-verification/`, `GET /api/newsletter/`,
`POST /api/newsletter/send/` y `GET /api/newsletter/history/`. Django valida
los formularios, mantiene la sesión, protege las escrituras con CSRF y limita
las preferencias, vista previa e historial al usuario autenticado.
La salida Angular está en `frontend\src\`; sus estilos propios viven en
`frontend\src\styles.css` y junto a cada componente. Django conserva sus
plantillas y recursos estáticos necesarios para Admin, pero no una interfaz
HTML de usuario.

Angular contiene las pantallas de login, registro, verificación de correo,
preferencias, Noticias con filtro por tema, vista previa del boletín y su
historial. El envío manual es síncrono: la API solo informa del resultado
después de que Django termine de llamar al backend de correo; «aceptado» no
garantiza la entrega. Se mantienen la verificación obligatoria, el destinatario
de la sesión y el límite de un intento cada cinco minutos. Registro y reenvío
generan enlaces firmados a `ANGULAR_FRONTEND_BASE_URL/verificar-email`; el token
sigue teniendo caducidad de 24 horas, solo se consume al confirmar con POST y
continúa ligado al usuario y correo actuales. En desarrollo
`ANGULAR_FRONTEND_BASE_URL` toma por defecto `http://localhost:4200`; en
producción configura explícitamente `ANGULAR_FRONTEND_BASE_URL` con el origen
público real de Angular. Si no se define, el valor de respaldo configurado es
`EMAIL_VERIFICATION_BASE_URL`, que no necesariamente sirve la SPA. La misma
configuración controla enlaces de verificación nuevos y redirecciones de las
antiguas rutas de pantalla. Por ejemplo:

```powershell
$env:ANGULAR_FRONTEND_BASE_URL = "https://app.ejemplo.com"
```

No es necesario cambiar `EMAIL_VERIFICATION_BASE_URL`, el backend de correo ni
otras variables existentes. Si la SPA se sirve bajo una ruta base, ajusta
también el `base href` de Angular. Para producción, publica el frontend y
enruta `/api/` al mismo origen para conservar las cookies de sesión y CSRF sin
CORS. Las antiguas rutas GET de pantallas (`/`, `/noticias/`, `/registro/`,
`/login/`, `/preferencias/`, `/boletin/` y `/verificar-email/`) redirigen
temporalmente a sus rutas Angular; el token de los enlaces antiguos se
transporta sin validarlo ni consumirlo. Los antiguos POST de registro, login,
preferencias y verificación se rechazan; logout, envío manual y reenvío antiguos
responden `410 Gone` sin efectos. La API y `/admin/` no se redirigen.

Prueba el flujo migrado en `http://localhost:4200/registro`: crea una cuenta;
con el backend de consola, copia de la consola Django el enlace que termina en
`/verificar-email?token=...`, ábrelo y confirma. Luego inicia sesión en
`/login`, guarda o modifica los temas, horario, zona y alertas en
`/preferencias`, y prueba «Reenviar verificación» (el segundo envío inmediato
se limita durante cinco minutos). También puedes abrir directamente
`http://localhost:4200/registro`, `/verificar-email?token=...` o
`/preferencias`; la última ruta requiere sesión. Tras verificar el correo,
inicia sesión, selecciona al menos un tema con fuentes disponibles y abre
`http://localhost:4200/boletin`. Solicita el envío manual allí; con el backend
de consola se registra una simulación, no un correo real. Consulta el estado y
el destinatario en `http://localhost:4200/historial`. La pantalla del boletín
también informa si el correo no está verificado y enlaza a la verificación;
desde `/preferencias` puedes reenviar el enlace.

Para comprobar la implementación:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py test accounts
Set-Location frontend
npm run build
npm test
```
