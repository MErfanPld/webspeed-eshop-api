from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.orders.models import Order

from .base import ApiTestCase


class OrderTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.store.settings = {**self.store.settings, "shipping": {"flatRate": 50000, "freeOver": 1_000_000}}
        self.store.save()
        self.p = Product.objects.create(
            store=self.store,
            key="tp",
            slug="tp",
            status="active",
            name="محصول",
            price=200000,
            stock=3,
            variants={"sizes": ["M"], "colors": [{"name": "مشکی", "hex": "#000000"}]},
        )

    def line(self, qty=1, **kw):
        return {"productId": "tp", "size": "M", "color": "مشکی", "quantity": qty, **kw}

    def stock(self):
        self.p.refresh_from_db()
        return self.p.stock

    def test_server_side_pricing_shipping_and_reservation(self):
        r = self.checkout([self.line(2, price=1)])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["order"]["total"], 450000)
        o = Order.objects.get(number=r.json()["order"]["number"])
        self.assertEqual((o.subtotal, o.shipping), (400000, 50000))
        self.assertEqual(o.customer_info["phone"], "09121234567")
        self.assertEqual(self.stock(), 1)
        self.assertTrue(Customer.objects.filter(store=self.store, phone="09121234567").exists())

    def test_insufficient_stock_rolls_back(self):
        r = self.checkout([self.line(5)])
        self.assertEqual(r.status_code, 409)
        self.assertIn("موجودی", r.json()["error"])
        self.assertEqual(self.stock(), 3)
        self.assertFalse(Order.objects.exists())

    def test_validation(self):
        self.assertEqual(self.checkout([self.line(size="XXL")]).status_code, 400)
        self.assertEqual(self.checkout([{"productId": "nope", "quantity": 1}]).status_code, 400)
        r = self.checkout([self.line()], customer={"fullName": "", "phone": "1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("phone", r.json()["details"])
        self.assertEqual(self.checkout([self.line()], receipt=b"<svg/>").status_code, 400)
        self.assertEqual(self.checkout([self.line()], receipt=None).status_code, 400)
        self.assertEqual(self.checkout([]).status_code, 400)
        self.assertEqual(self.stock(), 3)

    def test_cancel_restores_and_reopen_reserves(self):
        number = self.checkout([self.line(2)]).json()["order"]["number"]
        o = Order.objects.get(number=number)
        self.login()
        self.client.patch(f"/api/v1/admin/orders/{o.id}", {"status": "cancelled"}, format="json")
        self.assertEqual(self.stock(), 3)
        self.client.patch(f"/api/v1/admin/orders/{o.id}", {"status": "confirmed"}, format="json")
        self.assertEqual(self.stock(), 1)
        self.assertEqual(
            self.client.patch(f"/api/v1/admin/orders/{o.id}", {"status": "lost"}, format="json").status_code, 400
        )

    def test_tracking_requires_matching_phone(self):
        number = self.checkout([self.line()]).json()["order"]["number"]
        c = APIClient()
        self.assertEqual(c.get(f"/api/v1/orders/track?number={number}&phone=09120000000").status_code, 404)
        r = c.get(f"/api/v1/orders/track?number={number}&phone=09121234567")
        self.assertEqual(r.json()["order"]["status"], "pending")
        self.assertNotIn("customer", r.json()["order"])

    def test_receipt_signed_url(self):
        number = self.checkout([self.line()]).json()["order"]["number"]
        o = Order.objects.get(number=number)
        self.login()
        url = self.client.get(f"/api/v1/admin/orders/{o.id}/receipt").json()["url"]
        anon = APIClient()
        r = anon.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertEqual(anon.get(url[:-3] + "xyz").status_code, 403)
        with override_settings(PRIVATE_URL_EXPIRE_SECONDS=-1):
            self.assertEqual(anon.get(url).status_code, 403)

    def test_order_rate_limit(self):
        for _ in range(10):
            self.checkout([self.line()], receipt=None)
        r = self.checkout([self.line()])
        self.assertEqual(r.status_code, 429)

    def test_admin_lists_stats_and_customers(self):
        self.checkout([self.line()])
        self.login()
        self.assertEqual(len(self.client.get("/api/v1/admin/orders?status=pending").json()["orders"]), 1)
        stats = self.client.get("/api/v1/admin/stats").json()
        self.assertEqual((stats["orders"], stats["revenue"], stats["pending"]), (1, 250000, 1))
        customers = self.client.get("/api/v1/admin/customers").json()["customers"]
        self.assertEqual(customers[0]["orders"], 1)
        self.assertEqual(customers[0]["totalSpent"], 250000)
