"""Vistas de registro, sesión y preferencias del usuario autenticado."""

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import PreferencesForm, RegistrationForm
from .models import Preferences
from .newsletter_service import get_user_newsletter_preview


def register(request):
    """Registra una cuenta y crea sus preferencias iniciales antes de redirigir."""
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            Preferences.objects.create(user=user)
        messages.success(
            request,
            "Cuenta creada correctamente. Ya puedes iniciar sesión",
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
def newsletter_preview(request):
    """Muestra noticias filtradas para las preferencias de la sesión actual."""
    preview = get_user_newsletter_preview(request.user)
    return render(
        request,
        "accounts/newsletter_preview.html",
        {"preview": preview},
    )
