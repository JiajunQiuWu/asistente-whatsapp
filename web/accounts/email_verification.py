"""Creación y validación de enlaces de verificación de correo."""

import smtplib
from datetime import timedelta
from urllib.parse import urlencode, urljoin

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import User

TOKEN_MAX_AGE = 24 * 60 * 60
RESEND_INTERVAL = timedelta(minutes=5)
TOKEN_SALT = "accounts.email-verification"


def build_verification_url(user: User) -> str:
    """Devuelve un enlace firmado para la dirección actual del usuario."""
    token = signing.TimestampSigner(salt=TOKEN_SALT).sign_object(
        {"user_id": user.pk, "email": user.email}
    )
    base_url = f"{settings.EMAIL_VERIFICATION_BASE_URL.rstrip('/')}/"
    endpoint = urljoin(base_url, reverse("verify_email").lstrip("/"))
    return f"{endpoint}?{urlencode({'token': token})}"


def load_verification_user(token: str) -> User | None:
    """Resuelve un token vigente solo si aún corresponde a la dirección actual."""
    try:
        payload = signing.TimestampSigner(salt=TOKEN_SALT).unsign_object(
            token,
            max_age=TOKEN_MAX_AGE,
        )
    except signing.BadSignature:
        return None

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("user_id"), int)
        or isinstance(payload.get("user_id"), bool)
        or not isinstance(payload.get("email"), str)
    ):
        return None

    try:
        return User.objects.get(
            pk=payload["user_id"],
            email=payload["email"],
        )
    except User.DoesNotExist:
        return None


def send_verification_email(user: User) -> str:
    """Envía un enlace si han pasado cinco minutos desde el envío anterior."""
    current_user = User.objects.get(pk=user.pk)
    if not current_user.email:
        return "missing_email"
    if current_user.email_verified_at is not None:
        return "already_verified"

    now = timezone.now()
    claimed = (
        User.objects.filter(
            pk=current_user.pk,
            email=current_user.email,
            email_verified_at__isnull=True,
        )
        .filter(
            Q(verification_email_sent_at__isnull=True)
            | Q(verification_email_sent_at__lte=now - RESEND_INTERVAL)
        )
        .update(verification_email_sent_at=now)
    )
    if not claimed:
        return "throttled"

    verification_url = build_verification_url(current_user)
    sent = False
    try:
        sent = (
            send_mail(
                subject="Verifica tu dirección de correo",
                message=(
                    "Para verificar tu dirección de correo, abre este enlace "
                    "en las próximas 24 horas:\n\n"
                    f"{verification_url}\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[current_user.email],
                fail_silently=False,
            )
            == 1
        )
    except (OSError, smtplib.SMTPException, ValueError):
        sent = False
    finally:
        if not sent:
            User.objects.filter(
                pk=current_user.pk,
                verification_email_sent_at=now,
            ).update(verification_email_sent_at=None)

    if not sent:
        return "failed"
    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        return "simulated"
    return "sent"
