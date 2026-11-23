"""
Platform owner panel (superusers): overview numbers, plan pricing and the
landing-site content, so nothing needs django-admin day to day.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.core.errors import bad_request, not_found
from apps.core.views import body
from apps.stores.models import Store

from . import services as s
from .models import Article, FaqItem, LandingFeature, LandingSettings, Plan, RoadmapStep, Subscription, Testimonial
from .views import PlatformAdminView


def _text(d, key, n, required=False, label=""):
    v = d.get(key)
    v = v.strip()[:n] if isinstance(v, str) else ""
    if required and not v:
        raise bad_request(f"{label or key} الزامی است", {key: "الزامی است"})
    return v


class OverviewView(PlatformAdminView):
    @extend_schema(summary="Platform owner dashboard numbers", responses={200: dict})
    def get(self, request):
        from apps.orders.models import Order

        now = timezone.now()
        since = now - timedelta(days=30)
        subs = list(Subscription.objects.select_related("plan", "store"))
        active_paid = [x for x in subs if x.status == "active" and x.is_active]
        trial = [x for x in subs if x.status == "trial" and x.is_active]
        expired = [x for x in subs if not x.is_active]
        expiring = sorted(
            (x for x in subs if x.is_active and x.ends_at and x.ends_at <= now + timedelta(days=7)),
            key=lambda x: x.ends_at,
        )
        orders = Order.objects.exclude(status="cancelled")
        recent_orders = orders.filter(created_at__gte=since)
        signups = (
            Store.objects.filter(created_at__gte=since)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(n=Count("id"))
            .order_by("day")
        )
        by_plan = Plan.objects.annotate(
            n=Count("subscriptions", filter=Q(subscriptions__status__in=["trial", "active"]))
        ).order_by("sort")
        top = (
            Store.objects.annotate(
                gmv=Sum("orders__total", filter=Q(orders__created_at__gte=since) & ~Q(orders__status="cancelled")),
                n=Count("orders", filter=Q(orders__created_at__gte=since)),
            )
            .filter(n__gt=0)
            .order_by("-gmv")[:5]
        )
        return Response(
            {
                "stores": {
                    "total": Store.objects.count(),
                    "new30": Store.objects.filter(created_at__gte=since).count(),
                    "paid": len(active_paid),
                    "trial": len(trial),
                    "expired": len(expired),
                    "noPlan": Store.objects.filter(subscription__isnull=True).count(),
                },
                # Monthly recurring revenue from paid subscriptions (list price)
                "mrr": sum(x.plan.price_monthly for x in active_paid),
                "orders": {
                    "count30": recent_orders.count(),
                    "gmv30": recent_orders.aggregate(t=Sum("total"))["t"] or 0,
                    "countAll": orders.count(),
                },
                "signups": [{"day": r["day"].isoformat(), "n": r["n"]} for r in signups],
                "byPlan": [{"slug": p.slug, "name": p.name, "n": p.n} for p in by_plan],
                "expiringSoon": [
                    {"id": str(x.store_id), "name": x.store.name, "slug": x.store.slug, "endsAt": s._iso(x.ends_at), "status": x.status}
                    for x in expiring[:10]
                ],
                "topStores": [{"id": str(t.id), "name": t.name, "slug": t.slug, "gmv": t.gmv or 0, "orders": t.n} for t in top],
                "content": {
                    "articles": Article.objects.filter(status="published").count(),
                    "drafts": Article.objects.filter(status="draft").count(),
                    "testimonials": Testimonial.objects.filter(active=True).count(),
                },
            }
        )


# --- Plans --------------------------------------------------------------------
class PlanAdminView(PlatformAdminView):
    @extend_schema(summary="Edit a plan (prices, limits, features, highlight, active)", request=dict, responses={200: dict})
    def patch(self, request, slug):
        p = Plan.objects.filter(slug=slug).first()
        if not p:
            raise not_found("پلن یافت نشد")
        d = body(request)
        if "name" in d:
            p.name = _text(d, "name", 60, True, "نام پلن")
        if "tagline" in d:
            p.tagline = _text(d, "tagline", 160)
        for key, attr in (("priceMonthly", "price_monthly"), ("priceYearly", "price_yearly")):
            if key in d:
                try:
                    v = int(d[key])
                except (TypeError, ValueError):
                    raise bad_request("قیمت نامعتبر است", {key: "عدد وارد کنید"}) from None
                if v < 0:
                    raise bad_request("قیمت نامعتبر است", {key: "منفی نباشد"})
                setattr(p, attr, v)
        for key, attr in (("maxProducts", "max_products"), ("maxMembers", "max_members")):
            if key in d:
                v = d[key]
                if v in (None, ""):
                    setattr(p, attr, None)
                else:
                    try:
                        setattr(p, attr, max(1, int(v)))
                    except (TypeError, ValueError):
                        raise bad_request("عدد نامعتبر است", {key: "عدد وارد کنید"}) from None
        if "features" in d:
            if not isinstance(d["features"], list):
                raise bad_request("امکانات باید لیست باشد")
            p.features = [str(f).strip()[:120] for f in d["features"] if str(f).strip()][:20]
        for key, attr in (("customDomain", "custom_domain"), ("highlighted", "highlighted"), ("active", "active")):
            if key in d:
                setattr(p, attr, bool(d[key]))
        p.save()
        if p.highlighted:
            Plan.objects.exclude(pk=p.pk).filter(highlighted=True).update(highlighted=False)
        return Response({"plan": s.serialize_plan(p) | {"active": p.active}})

    @extend_schema(exclude=True)
    def get(self, request, slug):
        p = Plan.objects.filter(slug=slug).first()
        if not p:
            raise not_found("پلن یافت نشد")
        return Response({"plan": s.serialize_plan(p) | {"active": p.active}})


class PlanAdminListView(PlatformAdminView):
    @extend_schema(summary="All plans incl. inactive", responses={200: dict})
    def get(self, request):
        return Response({"plans": [s.serialize_plan(p) | {"active": p.active} for p in Plan.objects.all()]})


# --- Landing settings -------------------------------------------------------------
SETTINGS_FIELDS = {
    "heroBadge": ("hero_badge", 120), "heroTitle": ("hero_title", 160), "heroHighlight": ("hero_highlight", 80),
    "heroTitleEnd": ("hero_title_end", 80), "heroSubtitle": ("hero_subtitle", 600), "ctaPrimary": ("cta_primary", 60),
    "ctaSecondary": ("cta_secondary", 60), "videoTitle": ("video_title", 120), "videoText": ("video_text", 600),
    "videoUrl": ("video_url", 300), "supportPhone": ("support_phone", 40), "supportEmail": ("support_email", 254),
    "supportHours": ("support_hours", 80), "instagram": ("instagram", 60), "telegram": ("telegram", 60),
    "enamadHtml": ("enamad_html", 4000),
}


class LandingSettingsAdminView(PlatformAdminView):
    @extend_schema(summary="Landing settings (editable)", responses={200: dict})
    def get(self, request):
        st = LandingSettings.load()
        return Response({"settings": {k: getattr(st, a) for k, (a, _) in SETTINGS_FIELDS.items()} | {"showStats": st.show_stats}})

    @extend_schema(summary="Update landing settings", request=dict, responses={200: dict})
    def patch(self, request):
        st = LandingSettings.load()
        d = body(request)
        for key, (attr, n) in SETTINGS_FIELDS.items():
            if key in d:
                v = d[key]
                setattr(st, attr, v.strip()[:n] if isinstance(v, str) else "")
        if st.video_url and not st.video_url.startswith(("https://", "http://")):
            raise bad_request("لینک ویدیو باید با https شروع شود", {"videoUrl": "نامعتبر"})
        if "showStats" in d:
            st.show_stats = bool(d["showStats"])
        st.save()
        return self.get(request)


# --- Lists: features / roadmap / faq / testimonials (saved as a whole) ---------------
LISTS = {
    "features": (LandingFeature, {"icon": 40, "title": 80, "text": 300}),
    "roadmap": (RoadmapStep, {"icon": 40, "when": 40, "title": 80, "text": 300}),
    "faq": (FaqItem, {"question": 200, "answer": 2000}),
    "testimonials": (Testimonial, {"name": 80, "role": 120, "text": 1000, "store_url": 300}),
}


def _row(obj, fields) -> dict:
    out = {"id": obj.id, "active": obj.active}
    out.update({f: getattr(obj, f) for f in fields})
    if isinstance(obj, Testimonial):
        out["rating"] = obj.rating
    return out


class ContentListView(PlatformAdminView):
    @extend_schema(summary="A landing list (features | roadmap | faq | testimonials)", responses={200: dict})
    def get(self, request, kind):
        if kind not in LISTS:
            raise not_found("بخش یافت نشد")
        model, fields = LISTS[kind]
        return Response({"items": [_row(o, fields) for o in model.objects.all()]})

    @extend_schema(summary="Replace a landing list (order = array order)", request=dict, responses={200: dict})
    def put(self, request, kind):
        if kind not in LISTS:
            raise not_found("بخش یافت نشد")
        model, fields = LISTS[kind]
        items = body(request).get("items")
        if not isinstance(items, list) or len(items) > 50:
            raise bad_request("لیست نامعتبر است")
        required = {"faq": "question", "testimonials": "name"}.get(kind, "title")
        with transaction.atomic():
            keep = []
            for i, it in enumerate(items):
                it = it if isinstance(it, dict) else {}
                row = {f: (it.get(f).strip()[:n] if isinstance(it.get(f), str) else "") for f, n in fields.items()}
                if not row[required]:
                    raise bad_request(f"ردیف {i + 1}: خالی است", {"row": i})
                if "icon" in row and not row["icon"]:
                    row["icon"] = "Sparkles"
                row["active"] = it.get("active", True) is not False
                row["sort"] = i
                if kind == "testimonials":
                    try:
                        row["rating"] = min(5, max(1, int(it.get("rating") or 5)))
                    except (TypeError, ValueError):
                        row["rating"] = 5
                obj = model.objects.filter(pk=it["id"]).first() if isinstance(it.get("id"), int) else None
                obj = obj or model()
                for k, v in row.items():
                    setattr(obj, k, v)
                obj.save()
                keep.append(obj.pk)
            model.objects.exclude(pk__in=keep).delete()
        s_clear()
        return self.get(request, kind)


def s_clear():
    from django.core.cache import cache

    cache.delete(s.LANDING_CACHE_KEY)


# --- Articles --------------------------------------------------------------------
def _article_admin(a: Article) -> dict:
    return s.serialize_article(a, full=True) | {"id": a.id, "status": a.status}


def _save_article(a: Article, d: dict) -> Article:
    import re

    a.title = _text(d, "title", 160, True, "عنوان")
    slug = _text(d, "slug", 120, True, "آدرس").lower()
    if not re.match(r"^[\w-]+$", slug):
        raise bad_request("آدرس فقط حروف، عدد و خط تیره", {"slug": "نامعتبر"})
    if Article.objects.filter(slug=slug).exclude(pk=a.pk).exists():
        raise bad_request("این آدرس قبلاً استفاده شده", {"slug": "تکراری"})
    a.slug = slug
    a.excerpt = _text(d, "excerpt", 300, True, "خلاصه")
    a.body = _text(d, "body", 60000, True, "متن")
    a.category = _text(d, "category", 60)
    a.author = _text(d, "author", 80) or "تیم وب‌اسپید"
    a.status = "published" if d.get("status") == "published" else "draft"
    if d.get("publishedAt"):
        dt = parse_datetime(d["publishedAt"]) if isinstance(d["publishedAt"], str) else None
        if dt:
            a.published_at = dt if timezone.is_aware(dt) else timezone.make_aware(dt)
    a.save()
    return a


class ArticleAdminListView(PlatformAdminView):
    @extend_schema(summary="All articles incl. drafts", responses={200: dict})
    def get(self, request):
        return Response({"articles": [_article_admin(a) for a in Article.objects.all()]})

    @extend_schema(summary="Create article", request=dict, responses={201: dict})
    def post(self, request):
        return Response({"article": _article_admin(_save_article(Article(), body(request)))}, status=201)


class ArticleAdminDetailView(PlatformAdminView):
    def _get(self, pk):
        a = Article.objects.filter(pk=pk).first()
        if not a:
            raise not_found("مقاله یافت نشد")
        return a

    @extend_schema(summary="Article", responses={200: dict})
    def get(self, request, pk):
        return Response({"article": _article_admin(self._get(pk))})

    @extend_schema(summary="Update article", request=dict, responses={200: dict})
    def put(self, request, pk):
        return Response({"article": _article_admin(_save_article(self._get(pk), body(request)))})

    @extend_schema(summary="Delete article", responses={200: dict})
    def delete(self, request, pk):
        self._get(pk).delete()
        return Response({"ok": True})
