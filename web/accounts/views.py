"""Vistas de registro, sesión y preferencias del usuario autenticado."""

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .email_verification import load_verification_user, send_verification_email
from .forms import PreferencesForm, RegistrationForm
from .models import Preferences, User
from .newsletter_service import get_user_newsletter_preview


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
    """Muestra noticias filtradas para las preferencias de la sesión actual."""
    preview = get_user_newsletter_preview(request.user)
    return render(
        request,
        "accounts/newsletter_preview.html",
        {"preview": preview},
    )
