"""Construye correos del boletín y gestiona credenciales/envío con Gmail SMTP.

Este módulo lo usa la interfaz de ``app/__main__.py``:

* ``email`` sin ``--send`` crea un mensaje y lo muestra como vista previa;
* ``email-config`` pide una contraseña oculta y la guarda en Windows;
* ``email --send`` carga la configuración, crea el boletín y lo envía por SMTP.

El flujo de ``email --send`` es: validar remitente/destinatario, buscar la
contraseña en el entorno, después en Windows Credential Manager y, si se
permite la interacción, pedirla con ``getpass``. Después se crea el correo,
se negocia TLS, se autentica y se entrega el mensaje al servidor SMTP.

La vista previa no carga credenciales ni abre conexión. Este módulo no programa
envíos futuros ni reintenta los fallos de SMTP.
"""

# Bibliotecas estándar: entrada oculta, variables de entorno y protocolo SMTP/TLS.
import getpass
import os
import smtplib
import ssl

# Clases estándar para el objeto correo, datos de configuración y validación
# básica de direcciones.
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Mapping, Sequence

# Tipos de datos y función de boletín que ya utiliza el resto de la aplicación.
from app.briefing import build_briefing
from app.news import NewsItem
from app.tasks import Task

# Valores que identifican el asunto y el servidor de Gmail.
EMAIL_SUBJECT = "Boletín personal"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 20

# Identificador de servicio de keyring; el correo remitente sirve como usuario.
KEYRING_SERVICE = "asistente-whatsapp.gmail"


class EmailConfigurationError(ValueError):
    """Error recuperable de entradas: dirección, contraseña o configuración ausente.

    La CLI traduce este error a un mensaje para el usuario y código de salida 2.
    """


class EmailAuthenticationError(RuntimeError):
    """Gmail rechazó el inicio de sesión SMTP; la CLI devuelve código 3."""


class EmailConnectionError(RuntimeError):
    """Falló la conexión/protocolo SMTP; la CLI devuelve código 4."""


class EmailCredentialStoreError(RuntimeError):
    """No se pudo utilizar el almacén seguro; la CLI devuelve código 5."""


@dataclass(frozen=True)
class EmailSettings:
    """Datos de envío ya validados.

    ``sender`` identifica la cuenta Gmail y ``recipient`` el destino. La
    contraseña se oculta en la representación del objeto para evitar que un
    ``print(settings)`` accidental la muestre.
    """

    sender: str
    recipient: str
    password: str = field(repr=False)


def _secure_keyring_backend():
    """Devuelve exclusivamente el backend del Administrador de credenciales.

    No se acepta cualquier backend de keyring: algunos guardan secretos sin
    cifrar. Si WinVault no está instalado o disponible, se informa del fallo.

    Devuelve el backend solo si es WinVaultKeyring y tiene prioridad válida.
    Convierte errores de importación o del sistema operativo en un error seguro
    y reconocible por la CLI.
    """
    # Importar keyring dentro de la función mantiene la vista previa
    # independiente de esta dependencia.
    try:
        import keyring
    except ImportError as error:
        raise EmailCredentialStoreError(
            "No está disponible keyring. Instala las dependencias del proyecto."
        ) from error

    # Se importa el backend explícito de Windows en lugar de aceptar el backend
    # predeterminado de cualquier plataforma.
    try:
        from keyring.backends import Windows
    except ImportError as error:
        raise EmailCredentialStoreError(
            "No está disponible el almacén seguro de credenciales de Windows."
        ) from error
    # get_keyring() elige el backend activo. Rechazamos backends alternativos
    # para no guardar accidentalmente contraseñas sin protección.
    try:
        backend = keyring.get_keyring()
        if (
            not isinstance(backend, Windows.WinVaultKeyring)
            or backend.priority <= 0
        ):
            raise EmailCredentialStoreError(
                "No está disponible el Administrador de credenciales seguro de Windows."
            )
    except EmailCredentialStoreError:
        raise
    except (
        ImportError,
        RuntimeError,
        OSError,
        keyring.errors.KeyringError,
        Windows.pywintypes.error,
    ) as error:
        raise EmailCredentialStoreError(
            "No se pudo acceder al almacén seguro de credenciales de Windows."
        ) from error
    return backend


def save_app_password(sender: str, password: str) -> None:
    """Guarda la contraseña bajo el servicio y la cuenta indicados.

    Nunca escribe el secreto en un archivo ni lo incluye en los errores
    presentados al usuario.

    ``sender`` queda como nombre de usuario y ``KEYRING_SERVICE`` como servicio
    dentro del Administrador de credenciales de Windows.
    """
    # La biblioteca real se carga solo al solicitar almacenamiento seguro.
    try:
        import keyring
        from keyring.backends import Windows
    except ImportError as error:
        raise EmailCredentialStoreError(
            "No está disponible keyring. Instala las dependencias del proyecto."
        ) from error
    # set_password delega el almacenamiento cifrado a WinVaultKeyring.
    try:
        _secure_keyring_backend().set_password(KEYRING_SERVICE, sender, password)
    except (
        RuntimeError,
        OSError,
        keyring.errors.KeyringError,
        Windows.pywintypes.error,
    ):
        raise EmailCredentialStoreError(
            "No se pudo guardar la contraseña en el almacén seguro de Windows."
        ) from None


def _get_app_password(sender: str, non_interactive: bool) -> str:
    """Obtiene el secreto del almacén o, si se permite, lo pide oculto.

    La llamada a esta función solo ocurre cuando no se definió
    ``GMAIL_APP_PASSWORD`` en el entorno. Primero intenta keyring. Si el
    almacén no tiene ese registro, solo solicita la contraseña en modo
    interactivo; ``non_interactive=True`` termina con un error sin esperar
    entrada de teclado.
    """
    try:
        import keyring
        from keyring.backends import Windows
    except ImportError as error:
        raise EmailCredentialStoreError(
            "No está disponible keyring. Instala las dependencias del proyecto."
        ) from error
    # Recupera el registro identificado por servicio y dirección remitente.
    try:
        password = _secure_keyring_backend().get_password(KEYRING_SERVICE, sender)
    except (
        RuntimeError,
        OSError,
        keyring.errors.KeyringError,
        Windows.pywintypes.error,
    ):
        raise EmailCredentialStoreError(
            "No se pudo leer la contraseña del almacén seguro de Windows."
        ) from None

    if password:
        return password
    if non_interactive:
        # Automatizaciones no deben quedarse esperando entrada de teclado.
        raise EmailConfigurationError(
            "No se encontró GMAIL_APP_PASSWORD ni una contraseña guardada "
            "para esta cuenta. Ejecuta `python -m app email-config`."
        )

    # getpass evita mostrar los caracteres mientras se escriben.
    try:
        password = getpass.getpass("Contraseña de aplicación de Gmail: ")
    except EOFError as error:
        raise EmailConfigurationError(
            "No se pudo solicitar la contraseña de aplicación."
        ) from error
    if not password:
        raise EmailConfigurationError("La contraseña de aplicación no puede estar vacía.")
    return password


def _validated_address(value: str | None, variable_name: str) -> str:
    """Comprueba una dirección sencilla antes de usarla en cabeceras o SMTP.

    La validación rechaza valores vacíos, espacios, nombres de presentación,
    listas de destinatarios y saltos de línea. ``variable_name`` solo aparece
    en el error para que se sepa qué variable de entorno corregir.
    """
    if not value or value != value.strip() or any(char.isspace() for char in value):
        raise EmailConfigurationError(
            f"Configura {variable_name} con una dirección de correo válida."
        )

    # parseaddr detecta valores del tipo "Nombre <correo@dominio>" que aquí no
    # se aceptan: se espera solo una dirección en cada variable.
    display_name, address = parseaddr(value)
    if (
        display_name
        or address != value
        or address.count("@") != 1
        or not all(address.split("@"))
        or any(char in value for char in "\r\n,;")
    ):
        raise EmailConfigurationError(
            f"Configura {variable_name} con una dirección de correo válida."
        )
    return address


def load_email_settings(
    environ: Mapping[str, str] | None = None,
    *,
    non_interactive: bool = False,
) -> EmailSettings:
    """Valida direcciones y resuelve la contraseña en el orden previsto.

    Prioridad: variable GMAIL_APP_PASSWORD, almacén seguro de Windows y,
    finalmente, solicitud interactiva salvo que ``non_interactive`` sea True.

    ``environ`` permite pasar un mapa alternativo en pruebas; si no se indica,
    se consultan las variables del proceso. Devuelve un ``EmailSettings`` listo
    para usar con ``send_email``.
    """
    environment = os.environ if environ is None else environ
    sender = _validated_address(environment.get("GMAIL_ADDRESS"), "GMAIL_ADDRESS")
    recipient = _validated_address(environment.get("EMAIL_TO"), "EMAIL_TO")
    password = environment.get("GMAIL_APP_PASSWORD")
    if password:
        # El entorno tiene prioridad; en este caso no hace falta abrir keyring.
        return EmailSettings(sender=sender, recipient=recipient, password=password)

    # La contraseña no estaba en el entorno: intenta Windows y, en su caso,
    # pregunta de forma oculta.
    password = _get_app_password(sender, non_interactive)
    return EmailSettings(sender=sender, recipient=recipient, password=password)


def configure_email_account(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Solicita ocultamente la contraseña y la registra en Windows Credential Manager.

    Devuelve la dirección configurada para que la CLI pueda confirmar qué cuenta
    se configuró sin mostrar el secreto. No se conecta a Gmail ni verifica que
    la contraseña sea válida; eso se comprobará solo al enviar.
    """
    environment = os.environ if environ is None else environ
    sender = _validated_address(environment.get("GMAIL_ADDRESS"), "GMAIL_ADDRESS")
    # Comprueba que existe un almacén seguro antes de pedirle al usuario un secreto.
    _secure_keyring_backend()
    try:
        password = getpass.getpass("Contraseña de aplicación de Gmail: ")
    except EOFError as error:
        raise EmailConfigurationError(
            "No se pudo solicitar la contraseña de aplicación."
        ) from error
    if not password:
        raise EmailConfigurationError("La contraseña de aplicación no puede estar vacía.")
    save_app_password(sender, password)
    return sender


def build_briefing_email(
    news_items: Sequence[NewsItem],
    pending_tasks: Sequence[Task],
    sender: str | None = None,
    recipient: str | None = None,
) -> EmailMessage:
    """Construye el correo de texto plano sin conectarse ni enviarlo.

    El cuerpo se obtiene de ``build_briefing`` para mantener el mismo boletín
    que presenta el comando ``briefing``.

    Los encabezados From y To se añaden cuando se proporcionan. El envío también
    recibe estas direcciones en ``send_email`` para definir el remitente y el
    destinatario SMTP.
    """
    message = EmailMessage()
    message["Subject"] = EMAIL_SUBJECT
    if sender is not None:
        message["From"] = sender
    if recipient is not None:
        message["To"] = recipient
    # Reutiliza el texto del boletín; EmailMessage se ocupa de codificarlo como
    # un mensaje MIME de texto plano.
    message.set_content(build_briefing(news_items, pending_tasks))
    return message


def format_email_preview(message: EmailMessage) -> str:
    """Devuelve una representación visible de un correo que no se va a enviar.

    No consulta credenciales, no modifica el mensaje y no abre la red. La
    advertencia evita confundir una vista previa con un envío realizado.
    """
    return (
        "Vista previa: no se ha enviado ningún correo\n"
        f"Asunto: {message['Subject']}\n\n"
        f"{message.get_content()}"
    )


def send_email(message: EmailMessage, settings: EmailSettings) -> None:
    """Envía un correo por Gmail SMTP una sola vez y con cifrado TLS.

    Las excepciones del servidor se convierten a errores genéricos para impedir
    que una respuesta SMTP revele la contraseña u otros datos sensibles. El
    éxito significa que el servidor aceptó el mensaje, no que haya llegado a la
    bandeja de entrada del destinatario.
    """
    try:
        # El bloque with cierra la sesión SMTP aunque el envío falle.
        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            # Negocia TLS antes de transmitir usuario, contraseña o mensaje.
            # Empieza en SMTP y negocia TLS usando los certificados de confianza
            # del sistema antes de enviar credenciales.
            smtp.starttls(context=ssl.create_default_context())

            # Gmail usa la dirección remitente como nombre de usuario.
            smtp.login(settings.sender, settings.password)

            # send_message serializa el EmailMessage y lo entrega al destinatario.
            # La lista permite ampliar destinatarios más adelante sin alterar
            # cómo se construye el contenido del boletín.
            smtp.send_message(
                message,
                from_addr=settings.sender,
                to_addrs=[settings.recipient],
            )
    except smtplib.SMTPAuthenticationError:
        # No mostramos la respuesta SMTP, que podría incluir información privada.
        raise EmailAuthenticationError(
            "Gmail rechazó la autenticación. Comprueba la cuenta y su contraseña "
            "de aplicación."
        ) from None
    except (smtplib.SMTPException, OSError, TimeoutError):
        # Un error de red/protocolo se comunica sin detalle técnico ni secretos.
        raise EmailConnectionError(
            "No se pudo completar el envío mediante Gmail SMTP. "
            "Comprueba la conexión y la configuración."
        ) from None
