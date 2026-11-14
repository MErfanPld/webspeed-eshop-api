from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response

from apps.catalog.models import Product
from apps.core.views import AdminView
from apps.orders import services as orders
from apps.pages.models import Page


class DashboardView(AdminView):
    @extend_schema(summary="Dashboard KPIs", parameters=[OpenApiParameter("days", int)], responses={200: dict})
    def get(self, request):
        store = request.admin.store
        try:
            days = min(max(int(request.query_params.get("days", 30)), 1), 365)
        except ValueError:
            days = 30
        data = orders.stats(store, days)
        data["products"] = Product.objects.filter(store=store).count()
        data["pages"] = Page.objects.filter(store=store).count()
        data["publishedPages"] = Page.objects.filter(store=store, status="published").count()
        return Response(data)
