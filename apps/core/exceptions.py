"""
Uniform error responses: {"error": "<Persian message>", "details": ...}
Matches the shape used by the existing frontend API.
"""
import logging

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .errors import ApiError, bad_request, conflict, forbidden, not_found  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)


DEFAULT_MESSAGES = {
    400: "درخواست نامعتبر است",
    401: "ابتدا وارد شوید",
    403: "دسترسی مجاز نیست",
    404: "یافت نشد",
    405: "این عملیات مجاز نیست",
    413: "حجم درخواست بیش از حد مجاز است",
    415: "نوع محتوای درخواست پشتیبانی نمی‌شود",
    429: "تعداد درخواست‌ها زیاد است؛ کمی بعد دوباره تلاش کنید.",
}


def _first_message(data) -> str | None:
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return _first_message(data[0])
    if isinstance(data, dict):
        for v in data.values():
            m = _first_message(v)
            if m:
                return m
    return None


def api_exception_handler(exc, context):
    if isinstance(exc, ApiError):
        return Response({"error": str(exc.detail), "details": exc.details}, status=exc.status_code)
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.messages)
    if isinstance(exc, Http404):
        exc = exceptions.NotFound(DEFAULT_MESSAGES[404])
    if isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied(DEFAULT_MESSAGES[403])

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return Response({"error": "خطای داخلی سرور", "details": None}, status=500)

    code = response.status_code
    if isinstance(exc, exceptions.ValidationError):
        details = response.data
        message = _first_message(details) if isinstance(details, list) else "اطلاعات ارسالی را بررسی کنید"
        response.data = {"error": message or DEFAULT_MESSAGES[400], "details": details}
    else:
        # Built-in DRF messages are English; use Persian equivalents.
        response.data = {"error": DEFAULT_MESSAGES.get(code, "خطا"), "details": None}
        if isinstance(exc, exceptions.Throttled) and exc.wait:
            response.data["details"] = {"retryAfter": int(exc.wait)}
    if code == status.HTTP_401_UNAUTHORIZED:
        response.data["error"] = DEFAULT_MESSAGES[401]
    return response
