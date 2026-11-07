"""JSON endpoints used by the Angular application."""

import json
from html import unescape
from json import JSONDecodeError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .email_verification import send_verification_email, verify_email_token
from .forms import PreferencesForm, RegistrationForm
from .models import NewsletterSendAttempt, Preferences, TOPIC_CHOICES
from .newsletter_service import (
    get_user_news_page,
    get_user_newsletter_preview,
)
from .registration import save_registered_user
from .views import (
    MANUAL_NEWSLETTER_MESSAGES,
    request_manual_newsletter,
)


@require_GET
@ensure_csrf_cookie
def csrf_cookie(request):
    """Set Django's CSRF cookie before the SPA submits a form."""
    return JsonResponse({"detail": "CSRF cookie set"})


@require_GET
def current_session(request):
    user = request.user
    return JsonResponse(
        {
            "authenticated": user.is_authenticated,
            "user": (
                {"username": user.get_username()}
                if user.is_authenticated
                else None
            ),
        }
    )


@require_POST
def api_login(request):
    payload, error = _json_payload(request)
    if error is not None:
        return error
    if (
        not isinstance(payload.get("username"), str)
        or not isinstance(payload.get("password"), str)
    ):
        return JsonResponse(
            {"detail": "Indica el nombre de usuario y la contraseña."},
            status=400,
        )

    form = AuthenticationForm(request, data=payload)
    if not form.is_valid():
        return JsonResponse(
            {"detail": "Nombre de usuario o contraseña incorrectos."},
            status=401,
        )

    login(request, form.get_user())
    return JsonResponse(
        {
            "authenticated": True,
            "user": {"username": form.get_user().get_username()},
        }
    )


@require_POST
def api_logout(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Inicia sesión primero."}, status=401)

    logout(request)
    return JsonResponse({"authenticated": False, "user": None})


@require_GET
def api_news(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Inicia sesión para ver las noticias."},
            status=401,
        )

    page = get_user_news_page(request.user, request.GET.get("tema", ""))
    preview = page.preview
    preference = Preferences.objects.filter(user=request.user).first()
    return JsonResponse(
        {
            "generated_at": preview.generated_at.strftime("%d/%m/%Y %H:%M"),
            "timezone_name": preview.timezone_name,
            "selected_topics": list(preview.selected_topics),
            "has_selected_topics": preview.has_selected_topics,
            "matched_source_count": preview.matched_source_count,
            "warnings": list(preview.warnings),
            "topic_filters": list(page.topic_filters),
            "active_topic": page.active_topic,
            "selected_topic_label": page.selected_topic_label,
            "newsletter_enabled": preview.newsletter_enabled,
            "newsletter_time": (
                preference.newsletter_time.strftime("%H:%M")
                if preference is not None
                else None
            ),
            "email_verified": request.user.email_verified_at is not None,
            "articles": [_article_response(article) for article in page.articles],
        }
    )


def _article_response(article):
    return {
        "title": article.title,
        "source": article.source,
        "published": article.published,
        "link": article.link,
        "topic": article.topic,
        "topic_code": article.topic_code,
        "summary": (
            Truncator(unescape(strip_tags(article.summary))).words(45)
            if article.summary is not None
            else None
        ),
        "image_url": article.image_url,
    }


def _authenticated_api_error(request, action):
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"detail": f"Inicia sesión para {action}."},
        status=401,
    )


@require_GET
def api_newsletter_preview(request):
    error = _authenticated_api_error(request, "consultar el boletín")
    if error is not None:
        return error

    preview = get_user_newsletter_preview(request.user)
    return JsonResponse(
        {
            "generated_at": preview.generated_at.isoformat(),
            "timezone_name": preview.timezone_name,
            "newsletter_enabled": preview.newsletter_enabled,
            "selected_topics": list(preview.selected_topics),
            "has_selected_topics": preview.has_selected_topics,
            "matched_source_count": preview.matched_source_count,
            "warnings": list(preview.warnings),
            "email_verified": request.user.email_verified_at is not None,
            "articles": [_article_response(article) for article in preview.articles],
        }
    )


@require_POST
def api_send_manual_newsletter(request):
    error = _authenticated_api_error(request, "solicitar un boletín")
    if error is not None:
        return error
    _payload, error = _json_payload(request)
    if error is not None:
        return error

    status, attempt = request_manual_newsletter(request.user)
    response_status = {
        "email_unverified": 403,
        "no_topics": 409,
        "no_news": 409,
        "throttled": 429,
        "busy": 409,
        NewsletterSendAttempt.Status.FAILED: 502,
        NewsletterSendAttempt.Status.UNCERTAIN: 502,
        NewsletterSendAttempt.Status.ACCEPTED: 200,
        NewsletterSendAttempt.Status.SIMULATED: 200,
    }[status]
    body = {
        "status": status,
        "detail": MANUAL_NEWSLETTER_MESSAGES[status],
    }
    if attempt is not None:
        body["attempt"] = {
            "id": attempt.pk,
            "status": attempt.status,
            "status_label": attempt.get_status_display(),
            "recipient": attempt.recipient,
            "created_at": attempt.created_at.isoformat(),
        }
    return JsonResponse(body, status=response_status)


@require_GET
def api_newsletter_history(request):
    error = _authenticated_api_error(request, "consultar el historial del boletín")
    if error is not None:
        return error

    preference = Preferences.objects.filter(user=request.user).first()
    timezone_name = (
        preference.timezone_name if preference is not None else settings.TIME_ZONE
    )
    try:
        ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError):
        timezone_name = settings.TIME_ZONE

    attempts = NewsletterSendAttempt.objects.filter(user=request.user)[:10]
    return JsonResponse(
        {
            "timezone_name": timezone_name,
            "attempts": [
                {
                    "id": attempt.pk,
                    "created_at": attempt.created_at.isoformat(),
                    "recipient": attempt.recipient,
                    "status": attempt.status,
                    "status_label": attempt.get_status_display(),
                }
                for attempt in attempts
            ],
        }
    )


def _json_payload(request):
    if request.content_type != "application/json":
        return None, JsonResponse(
            {"detail": "Se requiere una solicitud JSON."},
            status=415,
        )
    try:
        payload = json.loads(request.body)
    except (JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"detail": "El JSON no es válido."}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse(
            {"detail": "El cuerpo JSON debe ser un objeto."},
            status=400,
        )
    return payload, None


def _form_errors(form):
    return JsonResponse(
        {
            "detail": "Revisa los datos indicados.",
            "field_errors": {
                field: [str(error) for error in errors]
                for field, errors in form.errors.items()
                if field != "__all__"
            },
            "non_field_errors": [
                str(error) for error in form.non_field_errors()
            ],
        },
        status=400,
    )


def _verification_message(status):
    messages = {
        "sent": (
            "El backend de correo aceptó el mensaje de verificación; "
            "esto no garantiza su llegada a Recibidos."
        ),
        "simulated": (
            "No se envió un correo real: el backend de consola muestra el "
            "mensaje en la consola del servidor."
        ),
        "throttled": "Debes esperar al menos 5 minutos entre envíos de verificación.",
        "already_verified": "Tu dirección de correo ya está verificada.",
        "missing_email": "Tu cuenta no tiene una dirección de correo.",
        "failed": "No se pudo enviar el correo de verificación. Inténtalo de nuevo.",
    }
    return messages[status]


@require_POST
def api_register(request):
    payload, error = _json_payload(request)
    if error is not None:
        return error

    form = RegistrationForm(payload)
    if not form.is_valid():
        return _form_errors(form)

    user = save_registered_user(form)
    if user is None:
        return _form_errors(form)

    email_status = send_verification_email(
        user,
        frontend_base_url=settings.ANGULAR_FRONTEND_BASE_URL,
    )
    status_code = 201 if email_status in {"sent", "simulated"} else 202
    return JsonResponse(
        {
            "created": True,
            "email_status": email_status,
            "message": f"Cuenta creada. {_verification_message(email_status)}",
        },
        status=status_code,
    )


def _preferences_response(user):
    preference, _created = Preferences.objects.get_or_create(user=user)
    form = PreferencesForm(instance=preference)
    return JsonResponse(
        {
            "email": user.email,
            "email_verified_at": (
                user.email_verified_at.isoformat()
                if user.email_verified_at is not None
                else None
            ),
            "preferences": {
                "newsletter_topics": preference.newsletter_topics,
                "newsletter_enabled": preference.newsletter_enabled,
                "newsletter_time": preference.newsletter_time.strftime("%H:%M"),
                "timezone_name": preference.timezone_name,
                "alerts_enabled": preference.alerts_enabled,
                "alert_topics": preference.alert_topics,
                "daily_alert_limit": preference.daily_alert_limit,
            },
            "topic_choices": [
                {"code": code, "label": label}
                for code, label in TOPIC_CHOICES
            ],
            "field_labels": {
                name: field.label for name, field in form.fields.items()
            },
        }
    )


@require_GET
def api_preferences(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Inicia sesión para consultar tus preferencias."},
            status=401,
        )
    return _preferences_response(request.user)


@require_POST
def api_save_preferences(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Inicia sesión para modificar tus preferencias."},
            status=401,
        )
    payload, error = _json_payload(request)
    if error is not None:
        return error

    preference = Preferences.objects.filter(user=request.user).first()
    if preference is None:
        preference = Preferences(user=request.user)
    form = PreferencesForm(payload, instance=preference)
    if not form.is_valid():
        return _form_errors(form)
    form.save()
    return _preferences_response(request.user)


@require_POST
def api_resend_verification(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Inicia sesión para reenviar la verificación."},
            status=401,
        )
    status = send_verification_email(
        request.user,
        frontend_base_url=settings.ANGULAR_FRONTEND_BASE_URL,
    )
    return JsonResponse(
        {"status": status, "message": _verification_message(status)},
        status=(
            429
            if status == "throttled"
            else 200 if status in {"sent", "simulated"} else 400
        ),
    )


@require_GET
def api_verify_email(request):
    user, state = verify_email_token(request.GET.get("token", ""), False)
    return JsonResponse(
        {
            "state": state,
            "email": user.email if user is not None else None,
            "message": (
                "El enlace ha caducado, no es válido o ya no corresponde a "
                "la dirección actual."
                if state == "invalid"
                else None
            ),
        },
        status=400 if state == "invalid" else 200,
    )


@require_POST
def api_confirm_email(request):
    payload, error = _json_payload(request)
    if error is not None:
        return error
    token = payload.get("token")
    if not isinstance(token, str):
        token = ""
    user, state = verify_email_token(token, True)
    return JsonResponse(
        {
            "state": state,
            "email": user.email if user is not None else None,
            "message": (
                "El enlace ha caducado, no es válido o ya no corresponde a "
                "la dirección actual."
                if state == "invalid"
                else (
                    "Tu dirección de correo se ha verificado."
                    if state == "verified"
                    else "Esta dirección de correo ya está verificada."
                )
            ),
        },
        status=400 if state == "invalid" else 200,
    )
