from django.core.files.uploadedfile import SimpleUploadedFile

from .base import PNG, ApiTestCase

PRODUCT = {
    "name": "محصول تست",
    "slug": "test-product",
    "price": 200000,
    "stock": 3,
    "status": "active",
    "sizes": ["M"],
    "colors": [{"name": "مشکی", "hex": "#000000"}],
    "category": "t-shirts",
}


class CatalogTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_product_crud_and_validation(self):
        r = self.client.post("/api/v1/admin/products", PRODUCT, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        p = r.json()["product"]
        self.assertEqual((p["category"], p["sizes"], p["status"]), ("t-shirts", ["M"], "active"))
        self.assertEqual(self.client.post("/api/v1/admin/products", PRODUCT, format="json").status_code, 409)
        for bad in ({"price": 0}, {"slug": "Bad Slug"}, {"name": ""}, {"compareAtPrice": 100}, {"category": "nope"}):
            r = self.client.post("/api/v1/admin/products", {**PRODUCT, "slug": "other", **bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
        r = self.client.put(f"/api/v1/admin/products/{p['id']}", {**PRODUCT, "price": 250000, "images": ["javascript:x"]}, format="json")
        self.assertEqual(r.json()["product"]["price"], 250000)
        self.assertEqual(r.json()["product"]["images"], ["javascript:x"])  # not a URL key → kept as text
        self.assertEqual(self.client.delete(f"/api/v1/admin/products/{p['id']}").status_code, 200)

    def test_public_listing_pagination_and_filters(self):
        self.client.post("/api/v1/admin/products", {**PRODUCT, "status": "draft"}, format="json")
        r = self.client.get("/api/v1/products?pageSize=5&page=2")
        self.assertEqual(r.json()["pagination"], {"page": 2, "pageSize": 5, "total": 20, "pages": 4})
        self.assertEqual(len(r.json()["products"]), 5)
        self.assertNotIn("status", r.json()["products"][0])
        cats = {p["category"] for p in self.client.get("/api/v1/products?category=jeans&pageSize=100").json()["products"]}
        self.assertEqual(cats, {"jeans"})
        prices = [p["price"] for p in self.client.get("/api/v1/products?sort=price-asc&pageSize=100").json()["products"]]
        self.assertEqual(prices, sorted(prices))
        self.assertEqual(self.client.get("/api/v1/products/test-product").status_code, 404)  # draft hidden

    def test_categories(self):
        r = self.client.post("/api/v1/admin/categories", {"name": "کیف", "slug": "bags"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.post("/api/v1/admin/categories", {"name": "x", "slug": "bags"}, format="json").status_code, 409)
        slugs = [c["slug"] for c in self.client.get("/api/v1/categories").json()["categories"]]
        self.assertIn("bags", slugs)


class MediaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def upload(self, content, name="a.png"):
        return self.client.post("/api/v1/admin/media", {"file": SimpleUploadedFile(name, content, "image/png")}, format="multipart")

    def test_magic_bytes_and_limits(self):
        r = self.upload(b"<svg onload=alert(1)>", "evil.png")
        self.assertEqual(r.status_code, 400)
        self.assertIn("فقط تصاویر", r.json()["error"])
        self.assertEqual(self.upload(PNG + b"0" * (5 * 1024 * 1024)).status_code, 413)
        r = self.upload(PNG, "pixel.png")
        self.assertEqual(r.status_code, 201)
        item = r.json()["item"]
        self.assertEqual(item["mime"], "image/png")
        self.assertEqual(len(self.client.get("/api/v1/admin/media").json()["items"]), 1)
        self.assertEqual(self.client.delete(f"/api/v1/admin/media/{item['id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/media").json()["items"], [])
