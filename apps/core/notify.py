"""
Outgoing notifications.

SMS (settings.SMS_BACKEND):
  - "console"   development: printed to the API/worker terminal (no cost)
  - "kavenegar" real SMS via https://kavenegar.com (KAVENEGAR_API_KEY, KAVENEGAR_SENDER)
Email: Django's EMAIL_BACKEND (console in development, SMTP in production).

Secrets are never logged; phone numbers are masked in logs.
"""

import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("webspeed.notify")


class NotificationError(Exception):
    pass


def _mask(phone: str) -> str:
    return phone[:4] + "***" + phone[-2:] if len(phone) > 6 else "***"


def send_sms(phone: str, message: str) -> None:
    backend = settings.SMS_BACKEND
    if backend == "console":
        # Development: show the full message (OTP codes) in the terminal
        print(f"\n[SMS → {phone}] {message}\n", flush=True)  # noqa: T201
        logger.info("SMS (console) to %s", _mask(phone))
        return
    if backend == "kavenegar":
        if not settings.KAVENEGAR_API_KEY:
            raise NotificationError("KAVENEGAR_API_KEY is not configured")
        url = f"https://api.kavenegar.com/v1/{settings.KAVENEGAR_API_KEY}/sms/send.json"
        data = {"receptor": phone, "message": message}
        if settings.KAVENEGAR_SENDER:
            data["sender"] = settings.KAVENEGAR_SENDER
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:  # noqa: S310 (fixed https host)
                body = json.loads(res.read().decode() or "{}")
        except Exception as e:  # network/HTTP errors
            raise NotificationError(f"SMS provider error: {type(e).__name__}") from None
        if (body.get("return") or {}).get("status") != 200:
            raise NotificationError(f"SMS provider rejected the message: {(body.get('return') or {}).get('status')}")
        logger.info("SMS (kavenegar) to %s", _mask(phone))
        return
    raise NotificationError(f"Unknown SMS_BACKEND: {backend}")


def send_email(to: str, subject: str, body: str) -> None:
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
