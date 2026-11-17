from datetime import datetime, time

from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import ratelimit
from apps.core.authentication import enforce_origin
from apps.core.errors import ApiError, bad_request, not_found
from apps.core.models import audit
from apps.core.views import AdminView, PublicView, body
from apps.stores.models import Store

from . import services as s
from .models import Plan, Subscription


class PlanListView(PublicView):
    @extend_schema(summary="Plans for the landing page", responses={200: dict})
    def get(self, request):
        return Response({"plans": [s.serialize_plan(p) for p in Plan.objects.filter(active=True)]})


class SubdomainCheckView(PublicView):
    @extend_schema(summary="Is a store subdomain available? ?name=", parameters=[OpenApiParameter("name", str)], responses={200: dict})
    def get(self, request):
        ratelimit.enforce(f"subcheck:{ratelimit.client_ip(request)}", 60, 60, "درخواست زیاد بود؛ کمی صبر کنید.")
        reason = s.check_subdomain(request.query_params.get("name"))
        return Response({"available": reason is None, "reason": reason})


class SignupView(PublicView):
    @extend_schema(
        summary="Create a store with its owner {storeName, subdomain, name, email, password, plan} (trial)",
        request=dict,
        responses={201: dict, 400: dict, 429: dict},
    )
    def post(self, request):
        enforce_origin(request)
        ratelimit.enforce(f"signup:{ratelimit.client_ip(request)}", 5, 3600, "تعداد ثبت‌نام زیاد بود؛ {minutes} دقیقه دیگر امتحان کنید.")
        store, user = s.signup(body(request))
        return Response(
            {
                "store": {"id": str(store.id), "name": store.name, "slug": store.slug, **s.store_urls(store)},
                "subscription": s.serialize_subscription(store.subscription),
            },
            status=201,
        )


class StoreSubscriptionView(AdminView):
    @extend_schema(summary="Plan and subscription of the current store", responses={200: dict})
    def get(self, request):
        store = request.admin.store
        sub = Subscription.objects.select_related("plan").filter(store=store).first()
        return Response(
            {
                "subscription": s.serialize_subscription(sub),
                "plans": [s.serialize_plan(p) for p in Plan.objects.filter(active=True)],
                **s.store_urls(store),
            }
        )


# --- Platform admin (superusers, central panel) -----------------------------------------
class PlatformAdminView(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not request.user or not request.user.is_authenticated:
            raise ApiError("ابتدا وارد شوید", 401)
        if not request.user.is_superuser:
            raise ApiError("فقط مدیر پلتفرم دسترسی دارد", 403)


def _store_row(st: Store) -> dict:
    sub = getattr(st, "subscription", None)
    return {
        "id": str(st.id),
        "name": st.name,
        "slug": st.slug,
        "domain": st.domain,
        "createdAt": st.created_at.isoformat().replace("+00:00", "Z"),
        "orders": st.n_orders,
        "products": st.n_products,
        "subscription": s.serialize_subscription(sub),
        **s.store_urls(st),
    }


class PlatformStoresView(PlatformAdminView):
    @extend_schema(summary="All stores with plan and usage (platform admin)", responses={200: dict})
    def get(self, request):
        qs = (
            Store.objects.select_related("subscription__plan")
            .annotate(n_orders=Count("orders", distinct=True), n_products=Count("products", distinct=True))
            .order_by("-created_at")
        )
        rows = [_store_row(st) for st in qs]
        active = sum(1 for r in rows if not r["subscription"] or r["subscription"]["active"])
        return Response(
            {
                "stores": rows,
                "stats": {"stores": len(rows), "active": active, "inactive": len(rows) - active},
                "plans": [s.serialize_plan(p) for p in Plan.objects.all()],
            }
        )


class PlatformStoreDetailView(PlatformAdminView):
    @extend_schema(summary="Change a store's plan/status/paid-until {plan?, status?, paidUntil?: YYYY-MM-DD}", request=dict, responses={200: dict})
    def patch(self, request, store_id):
        enforce_origin(request)
        st = Store.objects.filter(id=store_id).first()
        if not st:
            raise not_found("فروشگاه یافت نشد")
        d = body(request)
        sub = Subscription.objects.filter(store=st).first()
        plan = Plan.objects.filter(slug=d.get("plan")).first() if d.get("plan") else (sub.plan if sub else None)
        if plan is None:
            raise bad_request("پلن نامعتبر است")
        if sub is None:
            sub = Subscription(store=st, plan=plan)
        sub.plan = plan
        if d.get("status") in Subscription.Status.values:
            sub.status = d["status"]
        if "paidUntil" in d:
            day = parse_date(d["paidUntil"]) if isinstance(d["paidUntil"], str) else None
            if d["paidUntil"] and not day:
                raise bad_request("تاریخ نامعتبر است")
            sub.paid_until = timezone.make_aware(datetime.combine(day, time(23, 59, 59))) if day else None
        sub.save()
        from apps.stores.models import StoreMember

        owner = StoreMember.objects.filter(store=st, role="owner").first()
        if owner:
            class _A:  # audit in the store's own log
                store, user = st, request.user

            audit(_A, "platform.subscription", st.slug, plan=plan.slug, status=sub.status)
        st = (
            Store.objects.select_related("subscription__plan")
            .annotate(n_orders=Count("orders", distinct=True), n_products=Count("products", distinct=True))
            .get(id=st.id)
        )
        return Response({"store": _store_row(st)})
