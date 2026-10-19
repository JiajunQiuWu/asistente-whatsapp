"""Modelos de usuario y preferencias para la aplicación web local."""

from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

TOPIC_CHOICES = (
    ("ai", "IA"),
    ("technology", "Tecnología"),
    ("economy", "Economía"),
    ("science", "Ciencia"),
    ("international", "Actualidad internacional"),
)
VALID_TOPIC_CODES = {code for code, _label in TOPIC_CHOICES}


def validate_topics(value: object) -> None:
    """Acepta solo una lista de códigos de tema conocidos, sin duplicados."""
    if (
        not isinstance(value, list)
        or any(not isinstance(topic, str) for topic in value)
        or any(topic not in VALID_TOPIC_CODES for topic in value)
        or len(value) != len(set(value))
    ):
        raise ValidationError("Selecciona únicamente temas disponibles.")


def validate_timezone(value: str) -> None:
    """Comprueba el nombre IANA con la base de zonas de Python."""
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValidationError("Introduce una zona horaria válida.") from error


class User(AbstractUser):
    """Usuario propio del proyecto; conserva el sistema de autenticación Django."""

    email_verified_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="correo verificado el",
    )
    verification_email_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="último correo de verificación enviado",
    )

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_email_ci_unique",
            )
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        saves_email = update_fields is None or "email" in update_fields
        if self.pk and saves_email:
            previous_email = (
                type(self).objects.filter(pk=self.pk)
                .values_list("email", flat=True)
                .first()
            )
            if previous_email is not None and previous_email != self.email:
                self.email_verified_at = None
                self.verification_email_sent_at = None
                if update_fields is not None:
                    kwargs["update_fields"] = set(update_fields) | {
                        "email_verified_at",
                        "verification_email_sent_at",
                    }
        super().save(*args, **kwargs)


class Preferences(models.Model):
    """Preferencias privadas del boletín y de futuras alertas de cada usuario."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    newsletter_topics = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_topics],
        verbose_name="Temas del boletín",
    )
    newsletter_enabled = models.BooleanField(
        default=False,
        verbose_name="Boletín activado",
    )
    newsletter_time = models.TimeField(
        default=time(9, 0),
        verbose_name="Hora del boletín",
    )
    timezone_name = models.CharField(
        max_length=64,
        default="Europe/Madrid",
        validators=[validate_timezone],
        verbose_name="Zona horaria",
    )
    alerts_enabled = models.BooleanField(
        default=False,
        verbose_name="Alertas activadas",
    )
    alert_topics = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_topics],
        verbose_name="Temas de alertas",
    )
    daily_alert_limit = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name="Máximo de alertas diarias",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(daily_alert_limit__gte=1, daily_alert_limit__lte=10),
                name="preferences_daily_alert_limit_1_10",
            )
        ]
        verbose_name = "preferencia"
        verbose_name_plural = "preferencias"

    def __str__(self) -> str:
        return f"Preferencias de {self.user.username}"
