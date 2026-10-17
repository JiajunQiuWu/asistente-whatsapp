"""Rutas web para registro, autenticación y preferencias."""

from django.urls import path

from .views import UserLoginView, logout_view, preferences, register

urlpatterns = [
    path("", preferences, name="home"),
    path("registro/", register, name="register"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
    path("preferencias/", preferences, name="preferences"),
]
