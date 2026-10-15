"""Construcción de correos y envío seguro mediante Gmail SMTP."""

import getpass
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Mapping, Sequence

from app.briefing import build_briefing
from app.news import NewsItem
from app.tasks import Task

EMAIL_SUBJECT = "Boletín personal"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 20


class EmailConfigurationError(ValueError):
    """Falta o no es válida la configuración de correo."""


class EmailAuthenticationError(RuntimeError):
    """Gmail rechazó las credenciales de autenticación."""


class EmailConnectionError(RuntimeError):
    """No se pudo establecer o completar la conexión SMTP."""


@dataclass(frozen=True)
class EmailSettings:
    sender: str
    recipient: str
    password: str = field(repr=False)


def _validated_address(value: str | None, variable_name: str) -> str:
    if not value or value != value.strip() or any(char.isspace() for char in value):
        raise EmailConfigurationError(
            f"Configura {variable_name} con una dirección de correo válida."
        )

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
) -> EmailSettings:
    """Valida las direcciones y obtiene la contraseña sin mostrarla."""
    environment = os.environ if environ is None else environ
    sender = _validated_address(environment.get("GMAIL_ADDRESS"), "GMAIL_ADDRESS")
    recipient = _validated_address(environment.get("EMAIL_TO"), "EMAIL_TO")
    password = environment.get("GMAIL_APP_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Contraseña de aplicación de Gmail: ")
        except EOFError as error:
            raise EmailConfigurationError(
                "No se pudo solicitar la contraseña de aplicación."
            ) from error
    if not password:
        raise EmailConfigurationError("La contraseña de aplicación no puede estar vacía.")

    return EmailSettings(sender=sender, recipient=recipient, password=password)


def build_briefing_email(
    news_items: Sequence[NewsItem],
    pending_tasks: Sequence[Task],
    sender: str | None = None,
    recipient: str | None = None,
) -> EmailMessage:
    """Construye un correo de texto plano usando el boletín existente."""
    message = EmailMessage()
    message["Subject"] = EMAIL_SUBJECT
    if sender is not None:
        message["From"] = sender
    if recipient is not None:
        message["To"] = recipient
    message.set_content(build_briefing(news_items, pending_tasks))
    return message


def format_email_preview(message: EmailMessage) -> str:
    """Devuelve el asunto y el cuerpo del correo con una advertencia de vista previa."""
    return (
        "Vista previa: no se ha enviado ningún correo\n"
        f"Asunto: {message['Subject']}\n\n"
        f"{message.get_content()}"
    )


def send_email(message: EmailMessage, settings: EmailSettings) -> None:
    """Envía un correo por Gmail SMTP sin reintentos ni mensajes con secretos."""
    try:
        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(settings.sender, settings.password)
            smtp.send_message(
                message,
                from_addr=settings.sender,
                to_addrs=[settings.recipient],
            )
    except smtplib.SMTPAuthenticationError:
        raise EmailAuthenticationError(
            "Gmail rechazó la autenticación. Comprueba la cuenta y su contraseña "
            "de aplicación."
        ) from None
    except (smtplib.SMTPException, OSError, TimeoutError):
        raise EmailConnectionError(
            "No se pudo completar el envío mediante Gmail SMTP. "
            "Comprueba la conexión y la configuración."
        ) from None
