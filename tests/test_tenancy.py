from apps.catalog.models import Product
from apps.stores.models import Store

from .base import ORIGIN, ApiTestCase


class TenancyAndPermissionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        r = self.client.post(
            "/api/v1/admin/store", {"create": {"name": "دوم", "slug": "second", "domain": "shop2.example.com"}}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.second = Store.objects.get(slug="second")

    def test_new_store_has_default_pages_and_no_catalog(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.client._credentials["HTTP_AUTHORIZATION"], HTTP_X_STORE_ID=str(self.second.id))
        keys = {p["id"] for p in self.client.get("/api/v1/admin/pages").json()["pages"]}
        self.assertIn("home", keys)
        self.assertEqual(self.client.get("/api/v1/admin/products").json()["products"], [])

    def test_outsider_cannot_reach_other_store(self):
        outsider = self.make_user("out@test.local", "owner", store=self.second)
        c = self.client_for(outsider.email)
        # Pointing at the default store is ignored: falls back to own store
        c.credentials(HTTP_AUTHORIZATION=c._credentials["HTTP_AUTHORIZATION"], HTTP_X_STORE_ID=str(self.store.id))
        products = c.get("/api/v1/admin/products").json()["products"]
        self.assertEqual(products, [])
        key = Product.objects.filter(store=self.store).first().key
        self.assertEqual(c.get(f"/api/v1/admin/products/{key}").status_code, 404)
        self.assertEqual(c.delete(f"/api/v1/admin/products/{key}").status_code, 404)
        self.assertTrue(Product.objects.filter(store=self.store, key=key).exists())
        r = c.post("/api/v1/admin/store", {"storeId": str(self.store.id)}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_cross_store_order_access(self):
        p = Product.objects.filter(store=self.store, stock__gt=0).first()
        order_resp = self.checkout([{"productId": p.key, "size": p.variants["sizes"][0], "color": p.variants["colors"][0]["name"], "quantity": 1}])
        self.assertEqual(order_resp.status_code, 201, order_resp.content)
        from apps.orders.models import Order

        order = Order.objects.get(store=self.store)
        outsider = self.make_user("o2@test.local", "owner", store=self.second)
        c = self.client_for(outsider.email)
        self.assertEqual(c.get(f"/api/v1/admin/orders/{order.id}").status_code, 404)
        self.assertEqual(c.get(f"/api/v1/admin/orders/{order.id}/receipt").status_code, 404)
        self.assertEqual(c.patch(f"/api/v1/admin/orders/{order.id}", {"status": "cancelled"}, format="json").status_code, 404)

    def test_editor_role_limits(self):
        self.make_user("ed@test.local", "editor")
        c = self.client_for("ed@test.local")
        self.assertEqual(c.get("/api/v1/admin/pages").status_code, 200)
        self.assertEqual(c.post("/api/v1/admin/pages", {"name": "e", "slug": "/e"}, format="json").status_code, 201)
        key = c.get("/api/v1/admin/pages").json()["pages"][0]["id"]
        self.assertEqual(c.delete(f"/api/v1/admin/pages/{key}").status_code, 403)
        self.assertEqual(c.post("/api/v1/admin/products", {"name": "x"}, format="json").status_code, 403)
        self.assertEqual(c.patch("/api/v1/admin/store", {"name": "hack"}, format="json").status_code, 403)

    def test_public_store_resolved_by_domain(self):
        r = self.client.get("/api/v1/store", HTTP_X_STORE_HOST="shop2.example.com:443")
        self.assertEqual(r.json()["store"]["name"], "دوم")
        r = self.client.get("/api/v1/store", HTTP_X_STORE_HOST="unknown.example.com")
        self.assertEqual(r.json()["store"]["name"], "WebSpeed")
        r = self.client.get("/api/v1/products", HTTP_X_STORE_HOST="shop2.example.com")
        self.assertEqual(r.json()["pagination"]["total"], 0)

    def test_store_validation(self):
        r = self.client.post("/api/v1/admin/store", {"create": {"name": "x", "slug": "second"}}, format="json")
        self.assertEqual(r.status_code, 409)
        r = self.client.post("/api/v1/admin/store", {"create": {"name": "x", "slug": "BAD SLUG"}}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch("/api/v1/admin/store", {"domain": "not a domain"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 400)
