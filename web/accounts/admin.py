"""Registro de usuarios y preferencias en el panel de administración."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Preferences, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Reutiliza los campos y herramientas de administración de AbstractUser."""


@admin.register(Preferences)
class PreferencesAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "newsletter_enabled",
        "newsletter_time",
        "timezone_name",
        "alerts_enabled",
        "daily_alert_limit",
    )
    search_fields = ("user__username",)
    list_filter = ("newsletter_enabled", "alerts_enabled", "timezone_name")
