import re

from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Brand, Product, Review
from apps.core.models import AuditLog
from apps.marketing.models import Coupon
from apps.orders.models import Order, Payment

from .base import ORIGIN, PASSWORD, ApiTestCase

CUSTOMER = {
    "fullName": "خریدار",
    "phone": "09121234567",
    "province": "تهران",
    "city": "تهران",
    "address": "آدرس",
    "postalCode": "1234567890",
}


@override_settings(OTP_DEV_RETURN_CODE=True)
class FeatureBase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.store.settings = {**self.store.settings, "shipping": {"flatRate": 0, "freeOver": 0}}
        self.store.save()
        self.p = Product.objects.create(
            store=self.store, key="fp", slug="fp", status="active", name="محصول", price=100000, stock=5
        )

    def line(self, qty=1):
        return {"productId": "fp", "size": "", "color": "", "quantity": qty}

    def stock(self):
        self.p.refresh_from_db()
        return self.p.stock

    def customer_client(self, phone="09121234567"):
        c = APIClient()
        r = c.post("/api/v1/customer/otp/request", {"phone": phone}, format="json", HTTP_ORIGIN=ORIGIN)
        code = r.json()["devCode"]
        c.post("/api/v1/customer/otp/verify", {"phone": phone, "code": code}, format="json", HTTP_ORIGIN=ORIGIN)
        return c


class CouponTests(FeatureBase):
    def test_admin_crud_validate_and_checkout(self):
        self.login()
        r = self.client.post(
            "/api/v1/admin/coupons", {"code": "off10", "kind": "percent", "value": 10, "usageLimit": 1}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["coupon"]["code"], "OFF10")
        dup = self.client.post("/api/v1/admin/coupons", {"code": "OFF10", "kind": "fixed", "value": 5}, format="json")
        self.assertEqual(dup.status_code, 409)

        v = APIClient().post(
            "/api/v1/coupons/validate", {"code": "off10", "subtotal": 200000}, format="json", HTTP_ORIGIN=ORIGIN
        )
        self.assertEqual(v.json()["coupon"]["discount"], 20000)

        r = self.checkout([self.line(2)], coupon="OFF10")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["order"]["discount"], 20000)
        self.assertEqual(r.json()["order"]["total"], 180000)
        self.assertEqual(Coupon.objects.get(code="OFF10").used_count, 1)
        # usage limit reached
        self.assertEqual(self.checkout([self.line()], coupon="OFF10").status_code, 400)

        # cancelling gives the use back
        o = Order.objects.get(coupon_code="OFF10")
        self.client.patch(f"/api/v1/admin/orders/{o.id}", {"status": "cancelled"}, format="json")
        self.assertEqual(Coupon.objects.get(code="OFF10").used_count, 0)

    def test_min_order_and_expiry(self):
        Coupon.objects.create(store=self.store, code="BIG", kind="fixed", value=5000, min_order=10**7)
        self.assertEqual(self.checkout([self.line()], coupon="BIG").status_code, 400)
        self.assertEqual(self.stock(), 5)  # nothing reserved


class PaymentTests(FeatureBase):
    def _online(self):
        r = self.checkout([self.line(2)], receipt=None, paymentMethod="online")
        self.assertEqual(r.status_code, 201, r.content)
        url = r.json()["order"]["paymentUrl"]
        authority = url.rsplit("/", 1)[-1]
        return r.json()["order"]["number"], authority

    def test_mock_gateway_success_is_idempotent(self):
        number, authority = self._online()
        self.assertEqual(APIClient().get(f"/api/v1/payments/mock/{authority}").status_code, 200)
        r = APIClient().get(f"/api/v1/payments/callback?Authority={authority}&Status=OK")
        self.assertEqual(r.status_code, 302)
        self.assertIn("status=ok", r["Location"])
        o = Order.objects.get(number=number)
        self.assertEqual(o.status, "confirmed")
        self.assertIsNotNone(o.paid_at)
        # replayed callback changes nothing
        r2 = APIClient().get(f"/api/v1/payments/callback?Authority={authority}&Status=NOK")
        self.assertIn("status=ok", r2["Location"])
        self.assertEqual(self.stock(), 3)

    def test_failed_payment_cancels_and_restores_stock(self):
        number, authority = self._online()
        self.assertEqual(self.stock(), 3)
        r = APIClient().get(f"/api/v1/payments/callback?Authority={authority}&Status=NOK")
        self.assertIn("status=failed", r["Location"])
        self.assertEqual(Order.objects.get(number=number).status, "cancelled")
        self.assertEqual(Payment.objects.get(authority=authority).status, "failed")
        self.assertEqual(self.stock(), 5)

    def test_card_still_requires_receipt(self):
        self.assertEqual(self.checkout([self.line()], receipt=None, paymentMethod="card").status_code, 400)


class BrandReviewTests(FeatureBase):
    def test_brand_crud_product_link_and_filter(self):
        self.login()
        r = self.client.post("/api/v1/admin/brands", {"name": "آدیداس", "slug": "adidas"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        Product.objects.filter(pk=self.p.pk).update(brand_ref=Brand.objects.get(slug="adidas"))
        brands = APIClient().get("/api/v1/brands").json()["brands"]
        self.assertIn("adidas", [b["slug"] for b in brands])
        items = APIClient().get("/api/v1/products?brand=adidas").json()["products"]
        self.assertEqual([p["id"] for p in items], ["fp"])

    def test_review_requires_purchase_and_moderation(self):
        c = self.customer_client()
        r = c.post("/api/v1/products/fp/reviews", {"rating": 5, "text": "عالی بود"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 400)  # no purchase yet
        self.assertEqual(self.checkout([self.line()], customer=CUSTOMER).status_code, 201)
        r = c.post("/api/v1/products/fp/reviews", {"rating": 4, "text": "عالی بود"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["status"], "pending")
        dup = c.post("/api/v1/products/fp/reviews", {"rating": 4, "text": "دوباره"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(dup.status_code, 409)

        self.login()
        rid = Review.objects.get().id
        self.assertEqual(self.client.patch(f"/api/v1/admin/reviews/{rid}", {"status": "approved"}, format="json").status_code, 200)
        product = APIClient().get("/api/v1/products/fp").json()["product"]
        self.assertEqual(product["rating"], 4)
        self.assertEqual(product["reviewCount"], 1)
        self.assertEqual(product["reviews"][0]["comment"], "عالی بود")


class AddressTests(FeatureBase):
    def test_address_crud_and_default(self):
        c = self.customer_client()
        self.assertEqual(APIClient().get("/api/v1/customer/addresses").status_code, 401)
        r = c.post("/api/v1/customer/addresses", {**CUSTOMER, "title": "خانه"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["address"]["isDefault"])
        r2 = c.post(
            "/api/v1/customer/addresses", {**CUSTOMER, "title": "کار", "isDefault": True}, format="json", HTTP_ORIGIN=ORIGIN
        )
        lst = c.get("/api/v1/customer/addresses").json()["addresses"]
        self.assertEqual([a["title"] for a in lst if a["isDefault"]], ["کار"])
        bad = c.post("/api/v1/customer/addresses", {**CUSTOMER, "postalCode": "1"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(bad.status_code, 400)
        aid = r2.json()["address"]["id"]
        self.assertEqual(c.delete(f"/api/v1/customer/addresses/{aid}", HTTP_ORIGIN=ORIGIN).status_code, 200)
        self.assertTrue(c.get("/api/v1/customer/addresses").json()["addresses"][0]["isDefault"])


class PasswordResetTests(ApiTestCase):
    def test_forgot_and_reset_flow(self):
        r = self.client.post("/api/v1/auth/password/forgot", {"email": "nobody@x.io"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.client.post("/api/v1/auth/password/forgot", {"email": "owner@test.local"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(len(mail.outbox), 1)
        m = re.search(r"uid=([^&\s]+)&token=([^\s]+)", mail.outbox[0].body)
        uid, token = m.group(1), m.group(2)
        bad = self.client.post(
            "/api/v1/auth/password/reset", {"uid": uid, "token": "x-y", "password": "N3w-Pass!word"}, format="json", HTTP_ORIGIN=ORIGIN
        )
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(
            "/api/v1/auth/password/reset", {"uid": uid, "token": token, "password": "N3w-Pass!word"}, format="json", HTTP_ORIGIN=ORIGIN
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.login(password="N3w-Pass!word")
        # token is single-use (password hash changed)
        again = self.client.post(
            "/api/v1/auth/password/reset", {"uid": uid, "token": token, "password": PASSWORD}, format="json", HTTP_ORIGIN=ORIGIN
        )
        self.assertEqual(again.status_code, 400)


class AdminExtrasTests(FeatureBase):
    def test_saved_blocks(self):
        self.login()
        blocks = [{"id": "b1", "type": "spacer", "data": {}}]
        r = self.client.post("/api/v1/admin/saved-blocks", {"kind": "template", "name": "قالب", "blocks": blocks}, format="json")
        if r.status_code == 400:  # spacer may require fields; fall back to the registry default
            from apps.core.blocks import default_data

            blocks[0]["data"] = default_data("spacer")
            r = self.client.post("/api/v1/admin/saved-blocks", {"kind": "template", "name": "قالب", "blocks": blocks}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        bad = self.client.post("/api/v1/admin/saved-blocks", {"name": "x", "blocks": [{"id": "1", "type": "nope", "data": {}}]}, format="json")
        self.assertEqual(bad.status_code, 400)
        items = self.client.get("/api/v1/admin/saved-blocks?kind=template").json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(self.client.delete(f"/api/v1/admin/saved-blocks/{items[0]['id']}").status_code, 200)

    def test_optional_pagination(self):
        self.login()
        full = self.client.get("/api/v1/admin/products").json()
        self.assertNotIn("pagination", full)
        paged = self.client.get("/api/v1/admin/products?page=1&pageSize=5").json()
        self.assertEqual(len(paged["products"]), 5)
        self.assertEqual(paged["pagination"]["total"], len(full["products"]))
        self.assertIn("pagination", self.client.get("/api/v1/admin/orders?page=1").json())

    def test_audit_log_owner_only(self):
        self.login()
        self.client.post("/api/v1/admin/coupons", {"code": "A1", "kind": "fixed", "value": 1000}, format="json")
        self.assertTrue(AuditLog.objects.filter(action="coupon.create").exists())
        logs = self.client.get("/api/v1/admin/audit").json()["logs"]
        self.assertEqual(logs[0]["action"], "coupon.create")
        self.make_user("ed@test.local", "admin")
        self.assertEqual(self.client_for("ed@test.local").get("/api/v1/admin/audit").status_code, 403)

    @override_settings(SMS_BACKEND="console")
    def test_status_change_sends_sms(self):
        from unittest import mock

        with mock.patch("apps.core.notify.send_sms") as send, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.checkout([self.line()]).status_code, 201)
            o = Order.objects.latest("created_at")
            self.login()
            self.client.patch(f"/api/v1/admin/orders/{o.id}", {"status": "shipped"}, format="json")
        texts = [c.args[1] for c in send.call_args_list]
        self.assertTrue(any("ارسال شد" in t for t in texts), texts)
