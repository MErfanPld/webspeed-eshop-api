"""
Auth: login / refresh / logout / me.

Tokens are returned in the JSON body (for Bearer clients) AND set as
httpOnly cookies (for the browser frontend, `credentials: "include"`).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core import ratelimit
from apps.core.authentication import enforce_origin
from apps.core.errors import ApiError
from apps.core.views import AdminView, body
from apps.stores.tenancy import resolve_admin

User = get_user_model()
_DUMMY_HASH = make_password("timing-equalizer-not-a-real-password")


def user_dict(u) -> dict:
    out = {"id": str(u.id), "email": u.email, "name": u.get_full_name()}
    if u.is_superuser:
        out["isPlatformAdmin"] = True
    return out


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


LoginRequest = inline_serializer(
    "LoginRequest", {"email": serializers.EmailField(), "password": serializers.CharField()}
)
TokenRequest = inline_serializer("RefreshRequest", {"refresh": serializers.CharField(required=False)})


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Login (email + password)",
        request=LoginRequest,
        responses={
            200: OpenApiResponse(description="{user, access, refresh} + httpOnly cookies"),
            401: dict,
            429: dict,
        },
    )
    def post(self, request):
        data = body(request)
        email = data.get("email").strip().lower() if isinstance(data.get("email"), str) else ""
        password = data.get("password") if isinstance(data.get("password"), str) else ""
        if not email or not password:
            raise ApiError("ایمیل و رمز عبور را وارد کنید.", 400)
        limit_key = f"login:{ratelimit.client_ip(request)}:{email}"
        ok, retry = ratelimit.hit(limit_key, 8, 15 * 60)
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
        # On a store's own host only that store's team can sign in
        from apps.stores.tenancy import request_host, store_for_host

        host_store = store_for_host(request_host(request))
        if host_store is not None and not user.memberships.filter(store=host_store).exists():
            raise ApiError("ایمیل یا رمز عبور اشتباه است.", 401)
        # Only failed attempts count towards the limit
        ratelimit.reset(limit_key)
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


PasswordRequest = inline_serializer(
    "PasswordChangeRequest", {"currentPassword": serializers.CharField(), "newPassword": serializers.CharField()}
)


class PasswordChangeView(AdminView):
    """Change own password; every other session (refresh token) is revoked."""

    @extend_schema(summary="Change password", request=PasswordRequest, responses={200: dict, 400: dict})
    def post(self, request):
        user = request.user
        d = body(request)
        current = d.get("currentPassword") if isinstance(d.get("currentPassword"), str) else ""
        new = d.get("newPassword") if isinstance(d.get("newPassword"), str) else ""
        ok, retry = ratelimit.hit(f"pwchange:{user.id}", 5, 15 * 60)
        if not ok:
            raise ApiError("تلاش‌های ناموفق زیاد بود؛ کمی بعد دوباره امتحان کنید.", 429, {"retryAfter": retry})
        if not user.check_password(current):
            raise ApiError("رمز عبور فعلی اشتباه است.", 400, {"currentPassword": "رمز عبور فعلی اشتباه است."})
        if current == new:
            raise ApiError("رمز جدید باید با رمز فعلی متفاوت باشد.", 400)
        try:
            validate_password(new, user)
        except ValidationError as e:
            raise ApiError("رمز عبور جدید ضعیف است", 400, {"newPassword": e.messages}) from None
        user.set_password(new)
        user.save(update_fields=["password"])
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        ratelimit.reset(f"pwchange:{user.id}")
        refresh = RefreshToken.for_user(user)
        response = Response({"ok": True, **token_payload(refresh)})
        set_auth_cookies(response, refresh)
        return response


# --- Forgot / reset password (email) -------------------------------------------
class PasswordForgotView(APIView):
    """Always answers 200 (no account enumeration); the email holds a 1-hour link."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Request a password reset email {email}", request=dict, responses={200: dict, 429: dict})
    def post(self, request):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        from apps.core import notify

        enforce_origin(request)
        email = body(request).get("email") or ""
        email = email.strip().lower()[:254] if isinstance(email, str) else ""
        ratelimit.enforce(
            f"pwforgot-ip:{ratelimit.client_ip(request)}",
            5,
            15 * 60,
            "درخواست زیاد بود؛ {minutes} دقیقه دیگر امتحان کنید.",
        )
        if email:
            ratelimit.enforce(f"pwforgot:{email}", 3, 60 * 60, "درخواست زیاد بود؛ {minutes} دقیقه دیگر امتحان کنید.")
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                # Multi-tenant: the central panel serves every user's stores
                base = (
                    f"https://{settings.PANEL_SUBDOMAIN}.{settings.PLATFORM_DOMAIN}"
                    if settings.PLATFORM_DOMAIN and not settings.DEBUG
                    else settings.FRONTEND_URL
                )
                link = f"{base}/admin/reset-password?uid={uid}&token={token}"
                try:
                    notify.send_email(
                        user.email,
                        "بازیابی رمز عبور WebSpeed",
                        f"برای تعیین رمز جدید روی لینک زیر بزنید (اعتبار: ۱ ساعت):\n\n{link}\n\n"
                        "اگر این درخواست را شما نداده‌اید، این ایمیل را نادیده بگیرید.",
                    )
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception("password reset email failed")
        return Response({"ok": True})


class PasswordResetView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Set a new password {uid, token, password}", request=dict, responses={200: dict, 400: dict})
    def post(self, request):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode

        enforce_origin(request)
        ratelimit.enforce(
            f"pwreset-ip:{ratelimit.client_ip(request)}",
            10,
            15 * 60,
            "تلاش زیاد بود؛ {minutes} دقیقه دیگر امتحان کنید.",
        )
        d = body(request)
        uid, token, new = (d.get(k) if isinstance(d.get(k), str) else "" for k in ("uid", "token", "password"))
        try:
            user = User.objects.filter(pk=force_str(urlsafe_base64_decode(uid)), is_active=True).first()
        except (ValueError, TypeError, OverflowError):
            user = None
        if not user or not default_token_generator.check_token(user, token):
            raise ApiError("لینک بازیابی نامعتبر یا منقضی شده است.", 400)
        try:
            validate_password(new, user)
        except ValidationError as e:
            raise ApiError("رمز عبور جدید ضعیف است", 400, {"password": e.messages}) from None
        user.set_password(new)
        user.save(update_fields=["password"])
        for t in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=t)
        return Response({"ok": True})


class AuditLogView(AdminView):
    min_role = "owner"

    @extend_schema(summary="Audit log of the current store (owner only, paginated)", responses={200: dict})
    def get(self, request):
        from apps.core.models import AuditLog
        from apps.core.pagination import paginate

        qs = AuditLog.objects.select_related("user").filter(store=request.admin.store)
        if request.query_params.get("action"):
            qs = qs.filter(action__startswith=request.query_params["action"][:60])
        items, meta = paginate(qs, request, default_size=50)
        return Response(
            {
                "logs": [
                    {
                        "id": e.id,
                        "action": e.action,
                        "target": e.target,
                        "meta": e.meta,
                        "user": e.user.email if e.user else None,
                        "createdAt": e.created_at.isoformat().replace("+00:00", "Z"),
                    }
                    for e in items
                ],
                "pagination": meta,
            }
        )
