"""
Seed data (ported from frontend src/server/seed.ts).
`data/seed.json` is exported from the frontend sources (home page config,
sample catalog, store info, default header/footer blocks).
"""
import copy
import json
import logging
import secrets
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
SEED_FILE = Path(__file__).parent / "data" / "seed.json"


@lru_cache(maxsize=1)
def seed_data() -> dict:
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))


def _fresh_ids(value):
    """Deep copy with a new id for every object that has one (blocks, items)."""
    if isinstance(value, list):
        return [_fresh_ids(v) for v in value]
    if isinstance(value, dict):
        out = {k: _fresh_ids(v) for k, v in value.items()}
        if isinstance(out.get("id"), str):
            out["id"] = f"{out.get('type') or 'item'}-{secrets.token_hex(5)}"
        return out
    return value


def _doc(name, blocks=None, description="") -> dict:
    return {"schemaVersion": 1, "name": name, "description": description, "seo": None, "blocks": blocks or []}


def seed_store_content(store, with_sample_catalog: bool) -> None:
    """Default pages for a store (and optionally the 8 categories + 20 products)."""
    from apps.catalog.models import Category, Product
    from apps.pages.models import Page
    from apps.pages.services import LAYOUT_SLUGS, SITE_FOOTER_ID, SITE_HEADER_ID

    data = seed_data()
    d = data["defaults"]
    home_blocks = _fresh_ids(copy.deepcopy(data["home"]["blocks"]))
    now = timezone.now()
    pages = [
        Page(store=store, key="home", slug="/", type="home", status="published",
             doc=_doc("خانه", home_blocks, data["home"].get("description", "")),
             published_blocks=copy.deepcopy(home_blocks), published_at=now),
        Page(store=store, key=SITE_HEADER_ID, slug=LAYOUT_SLUGS["header"], type="header",
             doc=_doc("هدر سراسری", _fresh_ids([d["announcement-bar"], d["header"]]),
                      "تا زمان انتشار، هدر پیش‌فرض فروشگاه نمایش داده می‌شود.")),
        Page(store=store, key=SITE_FOOTER_ID, slug=LAYOUT_SLUGS["footer"], type="footer",
             doc=_doc("فوتر سراسری", _fresh_ids([d["footer"]]),
                      "تا زمان انتشار، فوتر پیش‌فرض فروشگاه نمایش داده می‌شود.")),
        Page(store=store, key="about", slug="/about", type="content",
             doc=_doc("درباره ما", [], "تا زمان انتشار، صفحه پیش‌فرض «درباره ما» نمایش داده می‌شود.")),
        Page(store=store, key="contact", slug="/contact", type="content",
             doc=_doc("تماس با ما", _fresh_ids([d["contact-form"]]),
                      "تا زمان انتشار، صفحه پیش‌فرض «تماس با ما» نمایش داده می‌شود.")),
    ]
    existing = set(Page.objects.filter(store=store).values_list("key", flat=True))
    Page.objects.bulk_create([p for p in pages if p.key not in existing])

    if not with_sample_catalog:
        return

    cats = {}
    for i, c in enumerate(data["categories"]):
        cat, _ = Category.objects.get_or_create(
            store=store, key=c["id"], defaults={"slug": c["slug"], "name": c["name"], "image": c.get("image", ""), "sort": i}
        )
        cats[cat.slug] = cat

    for p in data["products"]:
        if Product.objects.filter(store=store, key=p["id"]).exists():
            continue
        Product.objects.create(
            store=store,
            key=p["id"],
            slug=p["slug"],
            status="active",
            name=p["name"],
            description=p.get("description", ""),
            price=p["price"],
            compare_at_price=p.get("compareAtPrice"),
            stock=p.get("stock", 0),
            category=cats.get(p.get("category")),
            gender=p.get("gender", "unisex"),
            brand=p.get("brand", ""),
            images=p.get("images", []),
            variants={"sizes": p.get("sizes", []), "colors": p.get("colors", [])},
            featured=p.get("featured", False),
            new_arrival=p.get("newArrival", False),
            free_shipping=p.get("freeShipping", False),
            tags=p.get("tags", []),
            specs=p.get("specs"),
            rating=p.get("rating"),
            review_count=p.get("reviewCount"),
            reviews=p.get("reviews"),
        )


@transaction.atomic
def ensure_seeded() -> tuple[bool, str | None]:
    """
    First run: default store + owner + sample content. Idempotent.
    Returns (created, generated_password_or_None).
    """
    from apps.stores.models import Store, StoreMember

    if Store.objects.exists():
        return False, None
    info = seed_data()["store"]
    store = Store.objects.create(
        name=info["name"],
        slug="default",
        settings={
            "tagline": info.get("tagline", ""),
            "phone": info.get("phone", ""),
            "email": info.get("email", ""),
            "address": info.get("address", ""),
            "currency": "IRT",
            "payment": info.get("payment", {}),
            "shipping": {"flatRate": 0, "freeOver": 2_500_000},
        },
    )
    User = get_user_model()
    email = settings.ADMIN_EMAIL.lower()
    password = settings.ADMIN_PASSWORD
    generated = None
    if not password:
        if settings.DEBUG:
            password = "admin12345"
        else:
            password = generated = secrets.token_urlsafe(12)
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        user = User.objects.create_user(email=email, password=password, name="مدیر فروشگاه")
    else:
        generated = None
    StoreMember.objects.create(store=store, user=user, role=StoreMember.Role.OWNER)
    seed_store_content(store, with_sample_catalog=True)
    return True, generated
