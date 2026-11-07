"""Vistas de registro, sesión y preferencias del usuario autenticado."""

import smtplib
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.conf import settings
from django.core.mail import send_mail
from django.db import OperationalError, transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .email_verification import (
    send_verification_email,
    verify_email_token,
)
from .forms import PreferencesForm, RegistrationForm
from .models import NewsletterSendAttempt, Preferences, TOPIC_CHOICES, User
from .newsletter_service import (
    get_user_news_page,
    get_user_newsletter_preview,
)
from .registration import save_registered_user

NEWSLETTER_SEND_INTERVAL = timedelta(minutes=5)

MANUAL_NEWSLETTER_MESSAGES = {
    "email_unverified": "Verifica tu correo antes de solicitar un boletín.",
    "no_topics": "Elige al menos un tema antes de solicitar el envío del boletín.",
    "no_news": "No hay noticias disponibles para tus temas; no se ha enviado el boletín.",
    "throttled": (
        "Ya has solicitado un boletín recientemente. "
        "Espera cinco minutos antes de volver a intentarlo."
    ),
    "busy": (
        "Otra solicitud podría estar procesando tu envío. Comprueba el "
        "historial y espera cinco minutos antes de volver a intentarlo."
    ),
    "failed": "No se pudo completar el envío. No se ha programado un reintento.",
    "uncertain": (
        "No se pudo confirmar el resultado del envío. No se realizará un "
        "reintento automático; comprueba tu correo antes de volver a solicitarlo."
    ),
    NewsletterSendAttempt.Status.SIMULATED: (
        "Simulación completada por el backend de consola; no se envió un "
        "correo real."
    ),
    NewsletterSendAttempt.Status.ACCEPTED: (
        "El backend aceptó el boletín. Esto no garantiza su llegada a Recibidos."
    ),
}


def register(request):
    """Registra una cuenta y crea sus preferencias iniciales antes de redirigir."""
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = save_registered_user(form)
        if user is not None:
            email_status = send_verification_email(user)
            if email_status == "sent":
                messages.success(
                    request,
                    "Cuenta creada. El backend de correo aceptó el mensaje de "
                    "verificación; esto no garantiza su llegada a Recibidos.",
                )
            elif email_status == "simulated":
                messages.warning(
                    request,
                    "Cuenta creada, pero no se envió un correo real: el backend "
                    "de consola solo muestra el mensaje en la consola del servidor.",
                )
            else:
                messages.error(
                    request,
                    "La cuenta se creó, pero no se pudo enviar el correo de "
                    "verificación. Inicia sesión para volver a intentarlo.",
                )
            return redirect("login")
    return render(request, "accounts/register.html", {"form": form})


class UserLoginView(LoginView):
    """Utiliza el AuthenticationForm y la comprobación de contraseña de Django."""

    template_name = "accounts/login.html"


@login_required
@require_POST
def logout_view(request):
    """Cierra la sesión con POST, protegido por el middleware CSRF de Django."""
    logout(request)
    messages.success(request, "Has cerrado la sesión.")
    return redirect("login")


@login_required
def preferences(request):
    """Muestra o guarda solo las preferencias del usuario guardado en la sesión."""
    # El propietario siempre se toma de request.user, nunca de un ID enviado.
    preference, _created = Preferences.objects.get_or_create(user=request.user)
    form = PreferencesForm(request.POST or None, instance=preference)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tus preferencias se han guardado.")
        return redirect("preferences")
    return render(request, "accounts/preferences.html", {"form": form})


@login_required
@require_POST
def resend_verification_email(request):
    """Reenvía al usuario de la sesión el enlace de verificación pendiente."""
    status = send_verification_email(request.user)
    if status == "sent":
        messages.success(
            request,
            "El backend de correo aceptó el mensaje de verificación; esto no "
            "garantiza su llegada a Recibidos.",
        )
    elif status == "simulated":
        messages.warning(
            request,
            "No se envió un correo real: el backend de consola solo muestra el "
            "mensaje en la consola del servidor.",
        )
    elif status == "throttled":
        messages.error(
            request,
            "Debes esperar al menos 5 minutos entre envíos de verificación.",
        )
    elif status == "already_verified":
        messages.info(request, "Tu dirección de correo ya está verificada.")
    elif status == "missing_email":
        messages.error(request, "Tu cuenta no tiene una dirección de correo.")
    else:
        messages.error(
            request,
            "No se pudo enviar el correo de verificación. Inténtalo de nuevo.",
        )
    return redirect("preferences")


@require_http_methods(["GET", "POST"])
def verify_email(request):
    """Confirma el correo solo mediante POST y un token vigente y ligado al usuario."""
    token = (
        request.GET.get("token", "")
        if request.method == "GET"
        else request.POST.get("token", "")
    )
    user, state = verify_email_token(
        token,
        confirm=request.method == "POST",
    )
    if state == "invalid" or user is None:
        return render(
            request,
            "accounts/verify_email.html",
            {"state": "invalid", "user": None},
            status=400,
        )

    return render(
        request,
        "accounts/verify_email.html",
        {
            "state": state,
            "token": token if state == "confirm" else "",
            "user": user,
        },
        status=400 if state == "invalid" else 200,
    )


@login_required
def news(request):
    """Muestra las noticias de los temas elegidos por el usuario actual."""
    preview = get_user_newsletter_preview(request.user)
    page = get_user_news_page(
        request.user,
        request.GET.get("tema", ""),
        preview,
    )
    preference = Preferences.objects.filter(user=request.user).first()
    return render(
        request,
        "accounts/news.html",
        {
            "preview": page.preview,
            "articles": page.articles,
            "topic_filters": page.topic_filters,
            "active_topic": page.active_topic,
            "selected_topic_label": page.selected_topic_label,
            "newsletter_time": preference.newsletter_time if preference else None,
            "email_verified": request.user.email_verified_at is not None,
        },
    )


@login_required
def newsletter_preview(request):
    """Muestra noticias personalizadas y el historial del usuario actual."""
    preview = get_user_newsletter_preview(request.user)
    attempts = NewsletterSendAttempt.objects.filter(user=request.user)[:10]
    return render(
        request,
        "accounts/newsletter_preview.html",
        {
            "preview": preview,
            "attempts": attempts,
            "email_verified": request.user.email_verified_at is not None,
        },
    )


def request_manual_newsletter(user):
    """Reserve and synchronously send a personalized newsletter to its owner."""
    if user.email_verified_at is None:
        return "email_unverified", None

    preview = get_user_newsletter_preview(user)
    if not preview.has_selected_topics:
        return "no_topics", None
    if not preview.articles:
        return "no_news", None

    now = timezone.now()
    try:
        with transaction.atomic():
            reserved = (
                User.objects.filter(
                    pk=user.pk,
                    email=user.email,
                    email_verified_at__isnull=False,
                )
                .exclude(email="")
                .filter(
                    Q(manual_newsletter_last_attempt_at__isnull=True)
                    | Q(
                        manual_newsletter_last_attempt_at__lte=(
                            now - NEWSLETTER_SEND_INTERVAL
                        )
                    )
                )
                .update(manual_newsletter_last_attempt_at=now)
            )
            if not reserved:
                return "throttled", None

            attempt = NewsletterSendAttempt.objects.create(
                user=user,
                recipient=user.email,
            )
    except OperationalError as error:
        if "locked" not in str(error).lower():
            raise
        return "busy", None

    topic_labels = dict(TOPIC_CHOICES)
    selected_topics = ", ".join(
        topic_labels.get(topic, topic) for topic in preview.selected_topics
    )
    lines = [
        f"Tu boletín personal ({preview.generated_at:%d/%m/%Y %H:%M} "
        f"{preview.timezone_name})",
        f"Temas: {selected_topics}",
        "",
    ]
    for article in preview.articles:
        lines.extend(
            [
                article.title,
                article.source,
                f"Publicado: {article.published}" if article.published else "",
                article.link,
                "",
            ]
        )

    try:
        sent_count = send_mail(
            subject="Tu boletín personal",
            message="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[attempt.recipient],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException, ValueError):
        status = NewsletterSendAttempt.Status.UNCERTAIN
    else:
        if sent_count != 1:
            status = NewsletterSendAttempt.Status.FAILED
        elif settings.EMAIL_BACKEND == (
            "django.core.mail.backends.console.EmailBackend"
        ):
            status = NewsletterSendAttempt.Status.SIMULATED
        else:
            status = NewsletterSendAttempt.Status.ACCEPTED

    attempt.status = status
    attempt.save(update_fields={"status"})
    return status, attempt


@login_required
@require_POST
def send_manual_newsletter(request):
    """Reserva y envía un boletín personalizado solo al correo verificado."""
    status, _attempt = request_manual_newsletter(request.user)
    message = MANUAL_NEWSLETTER_MESSAGES[status]
    if status == "email_unverified":
        messages.error(request, message)
    elif status in {"no_topics", "no_news"}:
        messages.warning(request, message)
    elif status in {"throttled", "busy", NewsletterSendAttempt.Status.UNCERTAIN}:
        messages.warning(request, message)
    elif status == NewsletterSendAttempt.Status.FAILED:
        messages.error(request, message)
    else:
        messages.success(request, message)
    return redirect("newsletter_preview")
