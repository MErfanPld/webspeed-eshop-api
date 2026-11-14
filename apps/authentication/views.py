"""
Auth: login / refresh / logout / me.

Tokens are returned in the JSON body (for Bearer clients) AND set as
httpOnly cookies (for the browser frontend, `credentials: "include"`).
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core import ratelimit
from apps.core.authentication import enforce_origin
from apps.core.errors import ApiError
from apps.core.views import AdminView, body
from apps.stores.tenancy import resolve_admin

User = get_user_model()
_DUMMY_HASH = make_password("timing-equalizer-not-a-real-password")


def user_dict(u) -> dict:
    return {"id": str(u.id), "email": u.email, "name": u.get_full_name()}


def _cookie_kwargs():
    return {
        "httponly": True,
        "secure": settings.JWT_COOKIE_SECURE,
        "samesite": settings.JWT_COOKIE_SAMESITE,
        "domain": settings.JWT_COOKIE_DOMAIN,
        "path": "/",
    }


def set_auth_cookies(response, refresh: RefreshToken):
    jwt = settings.SIMPLE_JWT
    response.set_cookie(
        settings.JWT_COOKIE_ACCESS,
        str(refresh.access_token),
        max_age=int(jwt["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        **_cookie_kwargs(),
    )
    response.set_cookie(
        settings.JWT_COOKIE_REFRESH,
        str(refresh),
        max_age=int(jwt["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        **_cookie_kwargs(),
    )


def clear_auth_cookies(response):
    for name in (settings.JWT_COOKIE_ACCESS, settings.JWT_COOKIE_REFRESH, settings.STORE_COOKIE):
        response.delete_cookie(name, path="/", domain=settings.JWT_COOKIE_DOMAIN, samesite=settings.JWT_COOKIE_SAMESITE)


def token_payload(refresh: RefreshToken) -> dict:
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


LoginRequest = inline_serializer("LoginRequest", {"email": serializers.EmailField(), "password": serializers.CharField()})
TokenRequest = inline_serializer("RefreshRequest", {"refresh": serializers.CharField(required=False)})


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Login (email + password)",
        request=LoginRequest,
        responses={200: OpenApiResponse(description="{user, access, refresh} + httpOnly cookies"), 401: dict, 429: dict},
    )
    def post(self, request):
        data = body(request)
        email = data.get("email").strip().lower() if isinstance(data.get("email"), str) else ""
        password = data.get("password") if isinstance(data.get("password"), str) else ""
        if not email or not password:
            raise ApiError("ایمیل و رمز عبور را وارد کنید.", 400)
        ok, retry = ratelimit.hit(f"login:{ratelimit.client_ip(request)}:{email}", 8, 15 * 60)
        if not ok:
            raise ApiError(
                f"تلاش‌های ناموفق زیاد بود. {max(1, -(-retry // 60))} دقیقه دیگر دوباره امتحان کنید.",
                429,
                {"retryAfter": retry},
            )
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        # Always hash once so unknown emails take about as long as wrong passwords
        valid = user.check_password(password) if user else check_password(password, _DUMMY_HASH) and False
        if not user or not valid:
            raise ApiError("ایمیل یا رمز عبور اشتباه است.", 401)
        refresh = RefreshToken.for_user(user)
        response = Response({"user": user_dict(user), **token_payload(refresh)})
        set_auth_cookies(response, refresh)
        return response


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Rotate refresh token", request=TokenRequest, responses={200: dict, 401: dict})
    def post(self, request):
        raw = body(request).get("refresh")
        if not raw:
            raw = request.COOKIES.get(settings.JWT_COOKIE_REFRESH)
            if raw:
                enforce_origin(request)
        if not raw:
            raise ApiError("ابتدا وارد شوید", 401)
        try:
            old = RefreshToken(raw)
            user = User.objects.filter(id=old["user_id"], is_active=True).first()
            if not user:
                raise ApiError("ابتدا وارد شوید", 401)
            old.blacklist()
            refresh = RefreshToken.for_user(user)
        except TokenError:
            raise ApiError("نشست منقضی شده است؛ دوباره وارد شوید", 401) from None
        response = Response(token_payload(refresh))
        set_auth_cookies(response, refresh)
        return response


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Logout (blacklists the refresh token)", request=TokenRequest, responses={200: dict})
    def post(self, request):
        raw = body(request).get("refresh")
        if not raw:
            raw = request.COOKIES.get(settings.JWT_COOKIE_REFRESH)
            if raw:
                enforce_origin(request)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response({"ok": True})
        clear_auth_cookies(response)
        return response


class MeView(AdminView):
    @extend_schema(summary="Current user, active store and memberships", responses={200: dict})
    def get(self, request):
        ctx = resolve_admin(request)
        current = next(m for m in ctx.memberships if m.store_id == ctx.store.id)
        from apps.stores.tenancy import membership_dict

        return Response(
            {"user": user_dict(ctx.user), "store": membership_dict(current), "memberships": ctx.membership_payload()}
        )
