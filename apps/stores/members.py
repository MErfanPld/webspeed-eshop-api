"""
Team management for the current store.
List: any member. Add / change role / remove: owner only.
A store always keeps at least one owner.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.core.errors import bad_request, conflict, forbidden, not_found
from apps.core.views import AdminView, body

from .models import StoreMember

User = get_user_model()
ROLES = {c.value for c in StoreMember.Role}


def _serialize(m: StoreMember, me) -> dict:
    return {
        "userId": str(m.user_id),
        "email": m.user.email,
        "name": m.user.get_full_name(),
        "role": m.role,
        "isYou": m.user_id == me.id,
        "createdAt": m.created_at.isoformat().replace("+00:00", "Z"),
    }


def _require_owner(admin):
    if admin.role != StoreMember.Role.OWNER:
        raise forbidden("فقط مالک فروشگاه می‌تواند اعضا را مدیریت کند")


def _owner_count(store) -> int:
    return StoreMember.objects.filter(store=store, role=StoreMember.Role.OWNER).count()


class MemberListView(AdminView):
    @extend_schema(summary="Members of the current store", responses={200: dict})
    def get(self, request):
        a = request.admin
        qs = StoreMember.objects.filter(store=a.store).select_related("user").order_by("created_at")
        return Response({"members": [_serialize(m, a.user) for m in qs], "canManage": a.role == "owner"})

    @extend_schema(
        summary="Add a member {email, role, name?, password?} (owner). New users need a password.",
        request=dict,
        responses={201: dict},
    )
    @transaction.atomic
    def post(self, request):
        a = request.admin
        _require_owner(a)
        d = body(request)
        email = d.get("email").strip().lower() if isinstance(d.get("email"), str) else ""
        role = d.get("role")
        if not email or "@" not in email:
            raise bad_request("ایمیل معتبر وارد کنید")
        if role not in ROLES:
            raise bad_request("نقش نامعتبر است")
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            password = d.get("password") if isinstance(d.get("password"), str) else ""
            if not password:
                raise bad_request("برای کاربر جدید، رمز عبور اولیه لازم است")
            name = d.get("name").strip()[:150] if isinstance(d.get("name"), str) else ""
            candidate = User(email=email, name=name)
            try:
                validate_password(password, candidate)
            except ValidationError as e:
                raise bad_request("رمز عبور ضعیف است", {"password": e.messages}) from None
            user = User.objects.create_user(email=email, password=password, name=name)
        if StoreMember.objects.filter(store=a.store, user=user).exists():
            raise conflict("این کاربر قبلاً عضو فروشگاه است")
        m = StoreMember.objects.create(store=a.store, user=user, role=role)
        return Response({"member": _serialize(m, a.user)}, status=201)


class MemberDetailView(AdminView):
    def _get(self, request, user_id) -> StoreMember:
        m = StoreMember.objects.select_related("user").filter(store=request.admin.store, user_id=user_id).first()
        if not m:
            raise not_found("عضو یافت نشد")
        return m

    @extend_schema(summary="Change a member's role {role} (owner)", request=dict, responses={200: dict})
    @transaction.atomic
    def patch(self, request, user_id):
        a = request.admin
        _require_owner(a)
        role = body(request).get("role")
        if role not in ROLES:
            raise bad_request("نقش نامعتبر است")
        m = self._get(request, user_id)
        if m.role == "owner" and role != "owner" and _owner_count(a.store) <= 1:
            raise bad_request("فروشگاه باید حداقل یک مالک داشته باشد")
        m.role = role
        m.save(update_fields=["role"])
        return Response({"member": _serialize(m, a.user)})

    @extend_schema(summary="Remove a member (owner)", responses={200: dict})
    @transaction.atomic
    def delete(self, request, user_id):
        a = request.admin
        _require_owner(a)
        m = self._get(request, user_id)
        if m.role == "owner" and _owner_count(a.store) <= 1:
            raise bad_request("فروشگاه باید حداقل یک مالک داشته باشد")
        m.delete()
        return Response({"ok": True})
