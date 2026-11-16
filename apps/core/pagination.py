from apps.core.errors import bad_request

MAX_PAGE_SIZE = 100


def paginate(queryset, request, default_size: int = 24):
    """?page=1&pageSize=24 → (items, {page, pageSize, total, pages})"""
    try:
        page = int(request.query_params.get("page", 1))
        size = int(request.query_params.get("pageSize", default_size))
    except (TypeError, ValueError):
        raise bad_request("پارامتر صفحه‌بندی نامعتبر است") from None
    page = max(page, 1)
    size = min(max(size, 1), MAX_PAGE_SIZE)
    total = queryset.count()
    start = (page - 1) * size
    items = list(queryset[start : start + size])
    return items, {"page": page, "pageSize": size, "total": total, "pages": (total + size - 1) // size}


def paginate_optional(queryset, request, limit: int = 500, default_size: int = 25):
    """Paginate only when ?page= is given (keeps the legacy full-list response)."""
    if "page" not in request.query_params:
        return list(queryset[:limit]), None
    return paginate(queryset, request, default_size)
