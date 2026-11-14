"""Persian API errors: raise these anywhere; the handler renders {error, details}."""
from rest_framework import exceptions, status


class ApiError(exceptions.APIException):
    """Raise with a Persian message, an HTTP status and optional details."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "درخواست نامعتبر است"

    def __init__(self, message: str | None = None, status_code: int | None = None, details=None):
        super().__init__(message or self.default_detail)
        if status_code:
            self.status_code = status_code
        self.details = details


def bad_request(msg: str, details=None) -> ApiError:
    return ApiError(msg, 400, details)


def not_found(msg: str = "یافت نشد") -> ApiError:
    return ApiError(msg, 404)


def forbidden(msg: str = "دسترسی مجاز نیست") -> ApiError:
    return ApiError(msg, 403)


def conflict(msg: str) -> ApiError:
    return ApiError(msg, 409)
