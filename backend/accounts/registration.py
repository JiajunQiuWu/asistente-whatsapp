"""Shared account creation logic for Django forms and the JSON API."""

from django.db import IntegrityError, transaction

from .forms import RegistrationForm
from .models import Preferences, User


def save_registered_user(form: RegistrationForm) -> User | None:
    """Create the account and its default preferences as one transaction."""
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
        return None
    return user
