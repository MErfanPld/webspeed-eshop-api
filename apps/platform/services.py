"""Plans, sign-up of new stores and subscription state."""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.errors import ApiError, bad_request, conflict
from apps.stores.models import Store

from .models import Plan, Subscription

User = get_user_model()
SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def store_urls(store: Store) -> dict:
    pd = settings.PLATFORM_DOMAIN
    scheme = "https" if not settings.DEBUG else "http"
    host = store.domain or (f"{store.slug}.{pd}" if pd else None)
    if not host:
        return {"url": None, "adminUrl": None}
    return {"url": f"{scheme}://{host}", "adminUrl": f"{scheme}://{host}/admin"}


def serialize_plan(p: Plan) -> dict:
    return {
        "slug": p.slug,
        "name": p.name,
        "tagline": p.tagline,
        "priceMonthly": p.price_monthly,
        "priceYearly": p.price_yearly,
        "features": p.features,
        "maxProducts": p.max_products,
        "maxMembers": p.max_members,
        "customDomain": p.custom_domain,
        "highlighted": p.highlighted,
    }


def serialize_subscription(sub: Subscription | None) -> dict | None:
    if sub is None:
        return None
    end = sub.ends_at
    days_left = max(0, (end - timezone.now()).days) if end else None
    return {
        "plan": serialize_plan(sub.plan),
        "status": sub.status,
        "active": sub.is_active,
        "trialEndsAt": _iso(sub.trial_ends_at),
        "paidUntil": _iso(sub.paid_until),
        "endsAt": _iso(end),
        "daysLeft": days_left,
    }


def check_subdomain(name) -> str | None:
    """Returns a Persian reason why the subdomain can't be used, or None."""
    name = (name or "").strip().lower() if isinstance(name, str) else ""
    if not SUBDOMAIN_RE.match(name):
        return "فقط حروف انگلیسی کوچک، عدد و خط تیره؛ ۳ تا ۴۰ کاراکتر"
    if name in settings.RESERVED_SUBDOMAINS:
        return "این نام رزرو شده است"
    if Store.objects.filter(slug=name).exists():
        return "این آدرس قبلاً گرفته شده"
    return None


@transaction.atomic
def signup(data: dict) -> tuple[Store, User]:
    from apps.stores.services import create_store

    def text(k, n=120):
        v = data.get(k)
        return v.strip()[:n] if isinstance(v, str) else ""

    store_name, sub, name, email = text("storeName"), text("subdomain", 40).lower(), text("name"), text("email", 254).lower()
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    errors = {}
    if not store_name:
        errors["storeName"] = "نام فروشگاه الزامی است"
    reason = check_subdomain(sub)
    if reason:
        errors["subdomain"] = reason
    if not name:
        errors["name"] = "نام شما الزامی است"
    if not EMAIL_RE.match(email):
        errors["email"] = "ایمیل معتبر نیست"
    plan = Plan.objects.filter(slug=text("plan", 40), active=True).first()
    if not plan:
        errors["plan"] = "پلن را انتخاب کنید"
    if not errors.get("email") and User.objects.filter(email__iexact=email).exists():
        errors["email"] = "با این ایمیل قبلاً ثبت‌نام شده؛ از پنل مرکزی وارد شوید"
    if not errors:
        try:
            validate_password(password)
        except ValidationError as e:
            errors["password"] = " ".join(e.messages)
    if errors:
        raise bad_request("اطلاعات ثبت‌نام را بررسی کنید", errors)

    user = User.objects.create_user(email=email, password=password, name=name)
    try:
        store = create_store(user, store_name, sub)
    except ApiError as e:
        if e.status_code == 409:
            raise conflict("این آدرس همین الان گرفته شد؛ آدرس دیگری انتخاب کنید", {"subdomain": "گرفته شده"}) from None
        raise
    store.settings = {**store.settings, "email": email}
    store.save(update_fields=["settings"])
    Subscription.objects.create(
        store=store, plan=plan, status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=settings.TRIAL_DAYS),
    )
    return store, user


def plan_of(store: Store) -> Plan | None:
    sub = Subscription.objects.select_related("plan").filter(store=store).first()
    return sub.plan if sub else None


def enforce_product_limit(store: Store) -> None:
    from apps.catalog.models import Product

    plan = plan_of(store)
    if plan and plan.max_products is not None and Product.objects.filter(store=store).count() >= plan.max_products:
        raise ApiError(
            f"سقف محصولات پلن «{plan.name}» ({plan.max_products}) پر شده؛ برای افزودن بیشتر پلن را ارتقا دهید", 403,
            {"reason": "plan_limit"},
        )


def enforce_member_limit(store: Store) -> None:
    plan = plan_of(store)
    if plan and plan.max_members is not None and store.members.count() >= plan.max_members:
        raise ApiError(
            f"سقف اعضای تیم پلن «{plan.name}» ({plan.max_members}) پر شده؛ پلن را ارتقا دهید", 403,
            {"reason": "plan_limit"},
        )
