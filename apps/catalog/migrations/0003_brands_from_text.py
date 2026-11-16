"""Create Brand rows from the free-text Product.brand values and link them."""
import re

from django.db import migrations


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9؀-ۿ]+", "-", name.strip().lower()).strip("-")
    return s or "brand"


def forwards(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Brand = apps.get_model("catalog", "Brand")
    for p in Product.objects.exclude(brand="").filter(brand_ref__isnull=True).iterator():
        base = slugify(p.brand)
        brand = Brand.objects.filter(store_id=p.store_id, name=p.brand).first()
        if not brand:
            slug, i = base, 2
            while Brand.objects.filter(store_id=p.store_id, slug=slug).exists():
                slug, i = f"{base}-{i}", i + 1
            brand = Brand.objects.create(store_id=p.store_id, slug=slug, name=p.brand)
        p.brand_ref = brand
        p.save(update_fields=["brand_ref"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_brand_product_brand_ref_review_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
