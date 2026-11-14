"""
Business validators ported 1:1 from the frontend (src/lib/page-slug.ts,
src/lib/safe-url.ts, src/server/services/media.ts).
"""
import re
from urllib.parse import urlparse

# --- Page slugs --------------------------------------------------------------

RESERVED_SLUGS = {"/", "/admin", "/login", "/cart", "/checkout", "/products", "/profile", "/track", "/api"}
_SLUG_SEGMENT = r"[a-z0-9؀-ۿ_-]+"
_SLUG_RE = re.compile(rf"^/{_SLUG_SEGMENT}(/{_SLUG_SEGMENT})*$", re.IGNORECASE)


def normalize_slug(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9؀-ۿ/_-]", "", s)
    s = re.sub(r"/+", "/", s)
    s = re.sub(r"-+", "-", s)
    if not s.startswith("/"):
        s = "/" + s
    if len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s or "/"


def is_valid_slug(value: str) -> bool:
    n = normalize_slug(value)
    return n == "/" or bool(_SLUG_RE.match(n))


def is_reserved_slug(value: str) -> bool:
    n = normalize_slug(value)
    return (
        n in RESERVED_SLUGS
        or n.startswith("/admin")
        or n.startswith("/products/")
        or n.startswith("/api/")
        or n.startswith("/_")
    )


# Product / category slugs (no leading slash)
CATALOG_SLUG_RE = re.compile(r"^[a-z0-9؀-ۿ]+(?:-[a-z0-9؀-ۿ]+)*$")
STORE_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

# --- URLs ----------------------------------------------------------------------

ALLOWED_PROTOCOLS = {"http", "https", "mailto", "tel"}
URL_KEYS = {"href", "ctaHref", "viewAllHref", "url", "src", "image", "logo", "avatar", "ogImage"}
_CTRL = re.compile(r"[\x00-\x1f\x7f\s]+")
_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


def is_safe_url(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    compact = _CTRL.sub("", v)
    if compact.startswith("/") and not compact.startswith("//"):
        return True
    if compact.startswith(("#", "?")):
        return True
    if compact.startswith("//"):
        return False
    m = _SCHEME.match(compact)
    if not m:
        return True
    return m.group(1).lower() in ALLOWED_PROTOCOLS


def safe_embed_url(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    return value.strip() if parsed.scheme == "https" and parsed.netloc else None


def sanitize_urls(value):
    """Deep copy; unsafe URL values under URL_KEYS become "#" (links) or "" (media)."""
    if isinstance(value, list):
        return [sanitize_urls(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in URL_KEYS and isinstance(v, str) and not is_safe_url(v):
                out[k] = "#" if "href" in k.lower() else ""
            else:
                out[k] = sanitize_urls(v)
        return out
    return value


# --- Images (magic bytes; SVG intentionally rejected) -----------------------------

def sniff_image(data: bytes) -> tuple[str, str] | None:
    b = data
    if len(b) >= 8 and b[:4] == b"\x89PNG":
        return "image/png", "png"
    if len(b) >= 3 and b[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if len(b) >= 6 and b[:4] == b"GIF8":
        return "image/gif", "gif"
    if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


# --- Digits ----------------------------------------------------------------------

_FA = "۰۱۲۳۴۵۶۷۸۹"
_AR = "٠١٢٣٤٥٦٧٨٩"


def to_english_digits(s: str) -> str:
    return "".join(
        str(_FA.index(c)) if c in _FA else str(_AR.index(c)) if c in _AR else c for c in s
    )
