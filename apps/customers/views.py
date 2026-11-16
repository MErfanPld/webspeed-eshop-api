from django.conf import settings
from django.db.models import Count, Max, Q, Sum
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.core.authentication import enforce_origin
from apps.core.errors import ApiError, bad_request
from apps.core.views import AdminView, PublicView, body
from apps.orders.services import PHONE_RE, normalize_phone
from apps.orders.services import serialize as serialize_order
from apps.stores.tenancy import resolve_public_store

from . import otp
from .models import Address, Customer


class CustomerListView(AdminView):
    @extend_schema(summary="Customers of the current store with order totals", responses={200: dict})
    def get(self, request):
        qs = (
            Customer.objects.filter(store=request.admin.store)
            .annotate(
                order_count=Count("orders"),
                total_spent=Sum("orders__total", filter=~Q(orders__status="cancelled")),
                last_order=Max("orders__created_at"),
            )
            .order_by("-last_order")
        )
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q[:60]) | Q(phone__icontains=q[:20]))
        from apps.core.pagination import paginate_optional

        items, meta = paginate_optional(qs, request, 5000)
        out = {"pagination": meta} if meta else {}
        return Response(
            {
                **out,
                "customers": [
                    {
                        "phone": c.phone,
                        "name": c.name,
                        "email": c.email or None,
                        "orders": c.order_count,
                        "totalSpent": c.total_spent or 0,
                        "firstOrder": c.created_at.isoformat().replace("+00:00", "Z"),
                        "lastOrder": c.last_order.isoformat().replace("+00:00", "Z") if c.last_order else None,
                    }
                    for c in items
                ],
            }
        )


# --- Customer self-service (OTP login) ----------------------------------------
def _customer_dict(c: Customer) -> dict:
    return {"phone": c.phone, "name": c.name, "email": c.email or ""}


def _phone(d) -> str:
    phone = normalize_phone(d.get("phone") if isinstance(d.get("phone"), str) else "")
    if not PHONE_RE.match(phone):
        raise bad_request("شماره موبایل معتبر وارد کنید (مثال: ۰۹۱۲۱۲۳۴۵۶۷)")
    return phone


def current_customer(request) -> Customer:
    store = resolve_public_store(request)
    data = otp.read_session(request)
    if not data or data.get("s") != str(store.id):
        raise ApiError("ابتدا وارد حساب کاربری شوید", 401)
    customer = Customer.objects.filter(store=store, id=data.get("c")).first()
    if not customer:
        raise ApiError("ابتدا وارد حساب کاربری شوید", 401)
    return customer


class OtpRequestView(PublicView):
    @extend_schema(
        summary="Send a login code to a mobile number {phone}", request=dict, responses={200: dict, 429: dict}
    )
    def post(self, request):
        enforce_origin(request)
        store = resolve_public_store(request)
        phone = _phone(body(request))
        code = otp.request_code(request, store, phone)
        payload = {
            "ok": True,
            "expiresIn": otp.CODE_TTL,
            "isNew": not Customer.objects.filter(store=store, phone=phone).exists(),
        }
        if settings.OTP_DEV_RETURN_CODE:
            payload["devCode"] = code  # development/testing only
        return Response(payload)


class OtpVerifyView(PublicView):
    @extend_schema(
        summary="Verify the code {phone, code} → customer session cookie", request=dict, responses={200: dict}
    )
    def post(self, request):
        enforce_origin(request)
        store = resolve_public_store(request)
        d = body(request)
        phone = _phone(d)
        code = normalize_phone(d.get("code") if isinstance(d.get("code"), str) else "")
        if len(code) != 6 or not code.isdigit():
            raise bad_request("کد ۶ رقمی را کامل وارد کنید")
        otp.verify_code(store, phone, code)
        customer, created = Customer.objects.get_or_create(store=store, phone=phone, defaults={"name": ""})
        response = Response({"customer": _customer_dict(customer), "isNew": created})
        otp.set_session_cookie(response, otp.make_session(customer))
        return response


class CustomerMeView(PublicView):
    @extend_schema(summary="Signed-in customer profile and orders", responses={200: dict, 401: dict})
    def get(self, request):
        c = current_customer(request)
        orders = c.orders.filter(store=c.store).order_by("-created_at")[:100]
        return Response({"customer": _customer_dict(c), "orders": [serialize_order(o) for o in orders]})

    @extend_schema(summary="Update profile {name?, email?}", request=dict, responses={200: dict})
    def patch(self, request):
        enforce_origin(request)
        c = current_customer(request)
        d = body(request)
        if "name" in d:
            name = d["name"].strip()[:120] if isinstance(d["name"], str) else ""
            if not name:
                raise bad_request("نام الزامی است")
            c.name = name
        if "email" in d:
            email = d["email"].strip()[:200] if isinstance(d["email"], str) else ""
            if email and ("@" not in email or "." not in email.split("@")[-1]):
                raise bad_request("ایمیل معتبر نیست")
            c.email = email
        c.save()
        return Response({"customer": _customer_dict(c)})


class CustomerLogoutView(PublicView):
    @extend_schema(summary="Customer logout", request=None, responses={200: dict})
    def post(self, request):
        enforce_origin(request)
        response = Response({"ok": True})
        otp.clear_session_cookie(response)
        return response


# --- Addresses -------------------------------------------------------------------
def _address(a: Address) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "fullName": a.full_name,
        "phone": a.phone,
        "province": a.province,
        "city": a.city,
        "address": a.address,
        "postalCode": a.postal_code,
        "isDefault": a.is_default,
    }


def _address_values(d) -> dict:
    from apps.orders.services import validate_customer

    c = validate_customer(d)
    title = d.get("title").strip()[:60] if isinstance(d.get("title"), str) else ""
    return {
        "title": title,
        "full_name": c["fullName"],
        "phone": c["phone"],
        "province": c["province"],
        "city": c["city"],
        "address": c["address"],
        "postal_code": c["postalCode"],
    }


def _set_default(customer, a: Address):
    Address.objects.filter(customer=customer).exclude(pk=a.pk).update(is_default=False)
    if not a.is_default:
        a.is_default = True
        a.save(update_fields=["is_default"])


class AddressListView(PublicView):
    @extend_schema(summary="Saved addresses of the signed-in customer", responses={200: dict, 401: dict})
    def get(self, request):
        c = current_customer(request)
        return Response({"addresses": [_address(a) for a in c.addresses.all()]})

    @extend_schema(summary="Add address", request=dict, responses={201: dict})
    def post(self, request):
        enforce_origin(request)
        c = current_customer(request)
        if c.addresses.count() >= 10:
            raise bad_request("حداکثر ۱۰ آدرس می‌توانید ذخیره کنید")
        d = body(request)
        a = Address.objects.create(customer=c, **_address_values(d))
        if d.get("isDefault") or c.addresses.count() == 1:
            _set_default(c, a)
        return Response({"address": _address(a)}, status=201)


class AddressDetailView(PublicView):
    def _get(self, request, address_id):
        c = current_customer(request)
        a = c.addresses.filter(id=address_id).first()
        if not a:
            from apps.core.errors import not_found

            raise not_found("آدرس یافت نشد")
        return c, a

    @extend_schema(summary="Update address", request=dict, responses={200: dict})
    def put(self, request, address_id):
        enforce_origin(request)
        c, a = self._get(request, address_id)
        d = body(request)
        for k, v in _address_values(d).items():
            setattr(a, k, v)
        a.save()
        if d.get("isDefault"):
            _set_default(c, a)
        return Response({"address": _address(a)})

    @extend_schema(summary="Delete address", responses={200: dict})
    def delete(self, request, address_id):
        enforce_origin(request)
        c, a = self._get(request, address_id)
        was_default = a.is_default
        a.delete()
        nxt = c.addresses.first()
        if was_default and nxt:
            _set_default(c, nxt)
        return Response({"ok": True})
