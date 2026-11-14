"""
JWT authentication from the Authorization header OR an httpOnly cookie.

Cookie-authenticated unsafe requests (POST/PUT/PATCH/DELETE) must carry an
Origin/Referer that is the API host itself or a configured frontend origin —
this is the CSRF defence for cookie auth (SameSite=Lax covers the rest).
Bearer-header requests are not CSRF-prone and skip the check.
"""
from urllib.parse import urlparse

from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication

from .errors import forbidden

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def origin_allowed(request) -> bool:
    origin = request.META.get("HTTP_ORIGIN") or request.META.get("HTTP_REFERER")
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    candidate = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.netloc == request.get_host():
        return True
    return candidate in set(settings.CSRF_TRUSTED_ORIGINS) | set(settings.CORS_ALLOWED_ORIGINS)


def enforce_origin(request):
    if request.method not in SAFE_METHODS and not origin_allowed(request):
        raise forbidden("درخواست از مبدأ نامعتبر")


class JWTHeaderOrCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)
        raw = request.COOKIES.get(settings.JWT_COOKIE_ACCESS)
        if not raw:
            return None
        try:
            validated = self.get_validated_token(raw.encode())
        except Exception:
            # Expired/invalid cookie: treat as anonymous (public endpoints keep
            # working; protected ones answer 401 and the client refreshes).
            return None
        enforce_origin(request)
        return self.get_user(validated), validated
