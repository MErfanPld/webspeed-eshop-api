"""
URL configuration. All API routes live under /api/v1 and mirror the paths
and response shapes of the frontend's former Next.js API (no trailing
slashes, so HttpPageRepository only needs a new base URL).
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.authentication.views import LoginView, LogoutView, MeView, RefreshView
from apps.catalog import views as catalog
from apps.core.views import HealthView
from apps.customers.views import CustomerListView
from apps.media import views as media
from apps.orders import views as orders
from apps.pages import views as pages
from apps.stats.views import DashboardView
from apps.stores import views as stores

api = [
    path("health", HealthView.as_view(), name="health"),
    # Auth
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    # Stores
    path("admin/store", stores.StoreView.as_view(), name="admin-store"),
    path("admin/stores", stores.StoresListView.as_view(), name="admin-stores"),
    path("store", stores.PublicStoreView.as_view(), name="public-store"),
    # Pages
    path("admin/pages", pages.PageListView.as_view(), name="admin-pages"),
    path("admin/pages/<str:key>", pages.PageDetailView.as_view(), name="admin-page"),
    path("admin/pages/<str:key>/publish", pages.PagePublishView.as_view(), name="admin-page-publish"),
    path("admin/pages/<str:key>/unpublish", pages.PageUnpublishView.as_view(), name="admin-page-unpublish"),
    path("admin/pages/<str:key>/duplicate", pages.PageDuplicateView.as_view(), name="admin-page-duplicate"),
    path("pages", pages.PublicPageView.as_view(), name="public-page"),
    # Catalog
    path("admin/products", catalog.AdminProductListView.as_view(), name="admin-products"),
    path("admin/products/<str:key>", catalog.AdminProductDetailView.as_view(), name="admin-product"),
    path("admin/categories", catalog.AdminCategoryListView.as_view(), name="admin-categories"),
    path("admin/categories/<str:key>", catalog.AdminCategoryDetailView.as_view(), name="admin-category"),
    path("products", catalog.PublicProductListView.as_view(), name="public-products"),
    path("products/<str:slug>", catalog.PublicProductDetailView.as_view(), name="public-product"),
    path("categories", catalog.PublicCategoryListView.as_view(), name="public-categories"),
    # Media
    path("admin/media", media.MediaListView.as_view(), name="admin-media"),
    path("admin/media/<uuid:media_id>", media.MediaDetailView.as_view(), name="admin-media-item"),
    # Orders & customers
    path("orders", orders.CheckoutView.as_view(), name="checkout"),
    path("orders/track", orders.TrackView.as_view(), name="track"),
    path("admin/orders", orders.AdminOrderListView.as_view(), name="admin-orders"),
    path("admin/orders/<uuid:order_id>", orders.AdminOrderDetailView.as_view(), name="admin-order"),
    path("admin/orders/<uuid:order_id>/receipt", orders.AdminOrderReceiptView.as_view(), name="admin-order-receipt"),
    path("files/receipts/<str:token>", orders.SignedReceiptFileView.as_view(), name="receipt-file"),
    path("admin/customers", CustomerListView.as_view(), name="admin-customers"),
    # Stats
    path("admin/stats", DashboardView.as_view(), name="admin-stats"),
]

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include(api)),
]

if settings.STORAGE_BACKEND != "s3":
    # Public media from local storage (development only; MinIO/S3 serves it otherwise)
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT / "public")
