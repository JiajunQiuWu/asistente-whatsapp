"""Rutas principales del sitio web."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.api_urls")),
    path("", include("accounts.urls")),
]
