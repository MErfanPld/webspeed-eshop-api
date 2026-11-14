from django.db.models import Count, Max, Q, Sum
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.core.views import AdminView

from .models import Customer


class CustomerListView(AdminView):
    @extend_schema(summary="Customers of the current store with order totals", responses={200: dict})
    def get(self, request):
        qs = (
            Customer.objects.filter(store=request.admin.store)
            .annotate(
                order_count=Count("orders"),
                total_spent=Sum("orders__total", filter=~Q(orders__status="cancelled")),
                last_order=Max("orders__created_at"),
            )
            .order_by("-last_order")
        )
        return Response(
            {
                "customers": [
                    {
                        "phone": c.phone,
                        "name": c.name,
                        "email": c.email or None,
                        "orders": c.order_count,
                        "totalSpent": c.total_spent or 0,
                        "firstOrder": c.created_at.isoformat().replace("+00:00", "Z"),
                        "lastOrder": c.last_order.isoformat().replace("+00:00", "Z") if c.last_order else None,
                    }
                    for c in qs
                ]
            }
        )
