"""Vistas de registro, sesión y preferencias del usuario autenticado."""

import smtplib
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .email_verification import load_verification_user, send_verification_email
from .forms import PreferencesForm, RegistrationForm
from .models import NewsletterSendAttempt, Preferences, TOPIC_CHOICES, User
from .newsletter_service import get_user_newsletter_preview

NEWSLETTER_SEND_INTERVAL = timedelta(minutes=5)


def register(request):
    """Registra una cuenta y crea sus preferencias iniciales antes de redirigir."""
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                Preferences.objects.create(user=user)
        except IntegrityError:
            if User.objects.filter(username=form.cleaned_data["username"]).exists():
                form.add_error("username", "Este nombre de usuario ya está registrado.")
            else:
                form.add_error(
                    "email",
                    "Esta dirección de correo ya está registrada.",
                )
        else:
            email_status = send_verification_email(user)
            if email_status == "sent":
                messages.success(
                    request,
                    "Cuenta creada. Falta verificar el correo antes de confirmarlo.",
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
        messages.success(request, "Te hemos enviado un nuevo enlace de verificación.")
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
    user = load_verification_user(token)
    if user is None:
        return render(
            request,
            "accounts/verify_email.html",
            {"state": "invalid", "user": None},
            status=400,
        )

    if request.method == "POST" and user.email_verified_at is None:
        verified = User.objects.filter(
            pk=user.pk,
            email=user.email,
            email_verified_at__isnull=True,
        ).update(email_verified_at=timezone.now())
        if verified:
            state = "verified"
        else:
            user.refresh_from_db(fields=["email_verified_at"])
            state = "already_verified" if user.email_verified_at else "invalid"
    elif user.email_verified_at is not None:
        state = "already_verified"
    else:
        state = "confirm"

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


@login_required
@require_POST
def send_manual_newsletter(request):
    """Reserva y envía un boletín personalizado solo al correo verificado."""
    if request.user.email_verified_at is None:
        messages.error(request, "Verifica tu correo antes de solicitar un boletín.")
        return redirect("newsletter_preview")

    preview = get_user_newsletter_preview(request.user)
    if not preview.has_selected_topics:
        messages.warning(
            request,
            "Elige al menos un tema antes de solicitar el envío del boletín.",
        )
        return redirect("newsletter_preview")
    if not preview.articles:
        messages.warning(
            request,
            "No hay noticias disponibles para tus temas; no se ha enviado el boletín.",
        )
        return redirect("newsletter_preview")

    now = timezone.now()
    with transaction.atomic():
        current_user = User.objects.filter(
            pk=request.user.pk,
            email_verified_at__isnull=False,
        ).exclude(email="").first()
        if current_user is None:
            messages.error(
                request,
                "Tu cuenta no tiene un correo verificado válido para enviar el boletín.",
            )
            return redirect("newsletter_preview")

        reserved = (
            User.objects.filter(
                pk=current_user.pk,
                email=current_user.email,
                email_verified_at__isnull=False,
            )
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
            messages.warning(
                request,
                "Ya has solicitado un boletín recientemente. "
                "Espera cinco minutos antes de volver a intentarlo.",
            )
            return redirect("newsletter_preview")

        attempt = NewsletterSendAttempt.objects.create(
            user=current_user,
            recipient=current_user.email,
        )

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
        accepted = (
            send_mail(
                subject="Tu boletín personal",
                message="\n".join(lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[attempt.recipient],
                fail_silently=False,
            )
            == 1
        )
    except (OSError, smtplib.SMTPException, ValueError):
        accepted = False

    attempt.status = (
        NewsletterSendAttempt.Status.ACCEPTED
        if accepted
        else NewsletterSendAttempt.Status.FAILED
    )
    attempt.save(update_fields={"status"})

    if not accepted:
        messages.error(
            request,
            "No se pudo completar el envío. No se ha programado un reintento.",
        )
    elif settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        messages.success(
            request,
            "Simulación completada: el backend de consola aceptó el boletín. "
            "Esto no garantiza la llegada a Recibidos.",
        )
    else:
        messages.success(
            request,
            "El backend aceptó el boletín. Esto no garantiza su llegada a Recibidos.",
        )
    return redirect("newsletter_preview")
