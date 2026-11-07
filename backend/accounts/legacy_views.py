"""Compatibility responses for routes formerly used by Django-rendered pages."""

from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.http import require_GET


@require_GET
def redirect_to_frontend(request, frontend_path):
    """Temporarily redirect a legacy page URL to its Angular route."""
    frontend_base_url = settings.ANGULAR_FRONTEND_BASE_URL
    if not frontend_base_url:
        raise ImproperlyConfigured(
            "Configura ANGULAR_FRONTEND_BASE_URL para redirigir las rutas "
            "antiguas a Angular."
        )

    target = urljoin(
        f"{frontend_base_url.rstrip('/')}/",
        frontend_path.lstrip("/"),
    )
    query = request.GET.urlencode()
    if query:
        target = f"{target}?{query}"
    return HttpResponseRedirect(target)


def retired_legacy_action(_request):
    """Reject actions that are no longer part of the Django web interface."""
    return HttpResponse("Esta acción ya no está disponible.", status=410)
