from rest_framework.test import APIClient

from apps.customers.models import ContactMessage
from apps.stores.models import Store

from .base import ORIGIN, ApiTestCase


class ContactFormTests(ApiTestCase):
    def send(self, **kw):
        data = {"name": "مشتری", "email": "c@test.local", "message": "سلام، سؤال دارم", **kw}
        return APIClient().post("/api/v1/contact", data, format="json", HTTP_ORIGIN=ORIGIN)

    def test_message_is_saved_and_listed_for_the_store(self):
        self.assertEqual(self.send().status_code, 201)
        self.assertEqual(ContactMessage.objects.get().store, self.store)
        self.login()
        d = self.client.get("/api/v1/admin/messages").json()
        self.assertEqual(d["unread"], 1)
        mid = d["messages"][0]["id"]
        self.client.patch(f"/api/v1/admin/messages/{mid}", {"read": True}, format="json")
        self.assertEqual(self.client.get("/api/v1/admin/messages").json()["unread"], 0)

    def test_validation_and_rate_limit(self):
        r = self.send(name="", email="", message="x")
        self.assertEqual(set(r.json()["details"]), {"name", "email", "message"})
        for _ in range(5):
            self.send()
        self.assertEqual(self.send().status_code, 429)

    def test_other_store_cannot_read_messages(self):
        self.send()
        other = Store.objects.create(name="دیگر", slug="other")
        self.make_user("o@test.local", "owner", store=other)
        c = self.client_for("o@test.local")
        self.assertEqual(c.get("/api/v1/admin/messages", HTTP_X_STORE_ID=str(other.id)).json()["messages"], [])
