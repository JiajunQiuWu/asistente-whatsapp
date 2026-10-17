"""Formularios Django para registro y preferencias."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Preferences, TOPIC_CHOICES, User


class RegistrationForm(UserCreationForm):
    """Registro basado en el formulario estándar, con validación de contraseña Django."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)


class PreferencesForm(forms.ModelForm):
    """Presenta las listas JSON de temas como casillas de selección."""

    daily_alert_limit = forms.IntegerField(
        label="Máximo de alertas diarias (1–10)",
        min_value=1,
        max_value=10,
    )
    newsletter_topics = forms.MultipleChoiceField(
        label="Temas del boletín",
        choices=TOPIC_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    alert_topics = forms.MultipleChoiceField(
        label="Temas de alertas",
        choices=TOPIC_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Preferences
        fields = (
            "newsletter_topics",
            "newsletter_enabled",
            "newsletter_time",
            "timezone_name",
            "alerts_enabled",
            "alert_topics",
            "daily_alert_limit",
        )
        labels = {
            "newsletter_enabled": "Activar boletín",
            "newsletter_time": "Hora del boletín",
            "timezone_name": "Zona horaria (por ejemplo, Europe/Madrid)",
            "alerts_enabled": "Activar alertas",
            "daily_alert_limit": "Máximo de alertas diarias (1–10)",
        }
        widgets = {
            "newsletter_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean_timezone_name(self) -> str:
        """Valida de nuevo el nombre de zona para dar el error en el formulario."""
        value = self.cleaned_data["timezone_name"]
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValidationError("Introduce una zona horaria válida.") from error
        return value
