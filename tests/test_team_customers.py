from rest_framework.test import APIClient

from apps.catalog.models import Product
from apps.customers.models import Customer

from .base import ORIGIN, PASSWORD, ApiTestCase


class TeamTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_owner_manages_members(self):
        r = self.client.post(
            "/api/v1/admin/members",
            {"email": "new@test.local", "role": "editor", "name": "عضو", "password": "Another-Str0ng-pass"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        uid = r.json()["member"]["userId"]
        members = self.client.get("/api/v1/admin/members").json()
        self.assertTrue(members["canManage"])
        self.assertEqual(len(members["members"]), 2)
        self.assertEqual(self.client.patch(f"/api/v1/admin/members/{uid}", {"role": "admin"}, format="json").json()["member"]["role"], "admin")
        # new member can log in and sees the store
        c = APIClient()
        r = c.post("/api/v1/auth/login", {"email": "new@test.local", "password": "Another-Str0ng-pass"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/admin/members/{uid}").status_code, 200)

    def test_validation_and_last_owner(self):
        self.assertEqual(self.client.post("/api/v1/admin/members", {"email": "x@test.local", "role": "editor"}, format="json").status_code, 400)
        r = self.client.post("/api/v1/admin/members", {"email": "x@test.local", "role": "editor", "password": "123"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.json()["details"])
        self.assertEqual(self.client.post("/api/v1/admin/members", {"email": "owner@test.local", "role": "admin"}, format="json").status_code, 409)
        uid = self.owner.id
        self.assertEqual(self.client.patch(f"/api/v1/admin/members/{uid}", {"role": "editor"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/v1/admin/members/{uid}").status_code, 400)

    def test_only_owner_can_manage(self):
        self.make_user("adm@test.local", "admin")
        c = self.client_for("adm@test.local")
        self.assertEqual(c.get("/api/v1/admin/members").status_code, 200)
        self.assertFalse(c.get("/api/v1/admin/members").json()["canManage"])
        r = c.post("/api/v1/admin/members", {"email": "z@test.local", "role": "owner", "password": "Another-Str0ng-pass"}, format="json")
        self.assertEqual(r.status_code, 403)


class PasswordTests(ApiTestCase):
    def test_change_password_revokes_other_sessions(self):
        other = self.login(client=APIClient())
        self.login()
        r = self.client.post("/api/v1/auth/password", {"currentPassword": "wrong", "newPassword": "Brand-New-Pass-42"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/v1/auth/password", {"currentPassword": PASSWORD, "newPassword": "short"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("newPassword", r.json()["details"])
        r = self.client.post("/api/v1/auth/password", {"currentPassword": PASSWORD, "newPassword": "Brand-New-Pass-42"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("refresh", r.json())
        # old refresh token from another session no longer works
        self.assertEqual(self.client.post("/api/v1/auth/refresh", {"refresh": other["refresh"]}, format="json").status_code, 401)
        self.assertEqual(
            APIClient().post("/api/v1/auth/login", {"email": "owner@test.local", "password": "Brand-New-Pass-42"}, format="json").status_code,
            200,
        )


class CustomerOtpTests(ApiTestCase):
    def otp(self, phone="09121112233", client=None):
        c = client or self.client
        with self.settings(OTP_DEV_RETURN_CODE=True):
            r = c.post("/api/v1/customer/otp/request", {"phone": phone}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["devCode"]

    def test_login_profile_and_orders(self):
        code = self.otp()
        r = self.client.post("/api/v1/customer/otp/verify", {"phone": "۰۹۱۲۱۱۱۲۲۳۳", "code": code}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["isNew"])
        self.assertIn("ws_customer", r.cookies)
        me = self.client.get("/api/v1/customer/me")
        self.assertEqual(me.json()["customer"]["phone"], "09121112233")
        r = self.client.patch("/api/v1/customer/me", {"name": "مشتری", "email": "a@b.co"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.json()["customer"]["name"], "مشتری")
        # orders placed with this phone appear in the profile
        p = Product.objects.filter(store=self.store, stock__gt=0).first()
        self.checkout(
            [{"productId": p.key, "size": p.variants["sizes"][0], "color": p.variants["colors"][0]["name"], "quantity": 1}],
            customer={"fullName": "مشتری", "phone": "09121112233", "province": "ت", "city": "ت", "address": "آ", "postalCode": "1234567890"},
        )
        self.assertEqual(len(self.client.get("/api/v1/customer/me").json()["orders"]), 1)
        self.client.post("/api/v1/customer/logout", format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(self.client.get("/api/v1/customer/me").status_code, 401)

    def test_wrong_codes_and_limits(self):
        self.otp("09120000001")
        for _ in range(5):
            r = self.client.post("/api/v1/customer/otp/verify", {"phone": "09120000001", "code": "000000"}, format="json", HTTP_ORIGIN=ORIGIN)
            self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/v1/customer/otp/verify", {"phone": "09120000001", "code": "000000"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertIn("کد جدید", r.json()["error"])
        self.otp("09120000002")
        self.otp("09120000002")
        self.otp("09120000002")
        with self.settings(OTP_DEV_RETURN_CODE=True):
            r = self.client.post("/api/v1/customer/otp/request", {"phone": "09120000002"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(self.client.post("/api/v1/customer/otp/request", {"phone": "123"}, format="json", HTTP_ORIGIN=ORIGIN).status_code, 400)

    def test_code_not_returned_unless_enabled_and_session_is_store_bound(self):
        with self.settings(OTP_DEV_RETURN_CODE=False):
            r = self.client.post("/api/v1/customer/otp/request", {"phone": "09120000003"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertNotIn("devCode", r.json())
        code = self.otp("09120000004")
        self.client.post("/api/v1/customer/otp/verify", {"phone": "09120000004", "code": code}, format="json", HTTP_ORIGIN=ORIGIN)
        self.store.domain = None
        self.store.save()
        from apps.stores.models import Store

        Store.objects.create(name="دوم", slug="other", domain="other.example.com")
        self.assertEqual(self.client.get("/api/v1/customer/me", HTTP_X_STORE_HOST="other.example.com").status_code, 401)
        self.assertTrue(Customer.objects.filter(store=self.store, phone="09120000004").exists())
