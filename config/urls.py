"""
URL configuration. All API routes live under /api/v1 and mirror the paths
and response shapes of the frontend's former Next.js API (no trailing
slashes, so HttpPageRepository only needs a new base URL).
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.authentication.views import (
    AuditLogView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    PasswordForgotView,
    PasswordResetView,
    RefreshView,
)
from apps.catalog import views as catalog
from apps.core.views import HealthView
from apps.customers import views as customers
from apps.customers.views import CustomerListView
from apps.marketing import views as marketing
from apps.media import views as media
from apps.orders import views as orders
from apps.pages import views as pages
from apps.platform import views as platform
from apps.stats.views import DashboardView
from apps.stores import members
from apps.stores import views as stores

api = [
    path("health", HealthView.as_view(), name="health"),
    # Auth
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/password", PasswordChangeView.as_view(), name="auth-password"),
    path("auth/password/forgot", PasswordForgotView.as_view(), name="auth-password-forgot"),
    path("auth/password/reset", PasswordResetView.as_view(), name="auth-password-reset"),
    path("admin/audit", AuditLogView.as_view(), name="admin-audit"),
    # Stores
    path("admin/store", stores.StoreView.as_view(), name="admin-store"),
    path("admin/stores", stores.StoresListView.as_view(), name="admin-stores"),
    path("admin/members", members.MemberListView.as_view(), name="admin-members"),
    path("admin/members/<int:user_id>", members.MemberDetailView.as_view(), name="admin-member"),
    path("store", stores.PublicStoreView.as_view(), name="public-store"),
    # Pages
    path("admin/pages", pages.PageListView.as_view(), name="admin-pages"),
    path("admin/pages/<str:key>", pages.PageDetailView.as_view(), name="admin-page"),
    path("admin/pages/<str:key>/publish", pages.PagePublishView.as_view(), name="admin-page-publish"),
    path("admin/pages/<str:key>/unpublish", pages.PageUnpublishView.as_view(), name="admin-page-unpublish"),
    path("admin/pages/<str:key>/duplicate", pages.PageDuplicateView.as_view(), name="admin-page-duplicate"),
    path("pages", pages.PublicPageView.as_view(), name="public-page"),
    path("admin/saved-blocks", pages.SavedBlockListView.as_view(), name="admin-saved-blocks"),
    path("admin/saved-blocks/<int:item_id>", pages.SavedBlockDetailView.as_view(), name="admin-saved-block"),
    # Catalog
    path("admin/products", catalog.AdminProductListView.as_view(), name="admin-products"),
    path("admin/products/<str:key>", catalog.AdminProductDetailView.as_view(), name="admin-product"),
    path("admin/categories", catalog.AdminCategoryListView.as_view(), name="admin-categories"),
    path("admin/categories/<str:key>", catalog.AdminCategoryDetailView.as_view(), name="admin-category"),
    path("products", catalog.PublicProductListView.as_view(), name="public-products"),
    path("products/<str:slug>", catalog.PublicProductDetailView.as_view(), name="public-product"),
    path("products/<str:slug>/reviews", catalog.ProductReviewView.as_view(), name="product-reviews"),
    path("categories", catalog.PublicCategoryListView.as_view(), name="public-categories"),
    path("brands", catalog.PublicBrandListView.as_view(), name="public-brands"),
    path("admin/brands", catalog.AdminBrandListView.as_view(), name="admin-brands"),
    path("admin/brands/<int:brand_id>", catalog.AdminBrandDetailView.as_view(), name="admin-brand"),
    path("admin/reviews", catalog.AdminReviewListView.as_view(), name="admin-reviews"),
    path("admin/reviews/<int:review_id>", catalog.AdminReviewDetailView.as_view(), name="admin-review"),
    # Marketing
    path("admin/coupons", marketing.AdminCouponListView.as_view(), name="admin-coupons"),
    path("admin/coupons/<int:coupon_id>", marketing.AdminCouponDetailView.as_view(), name="admin-coupon"),
    path("coupons/validate", marketing.CouponValidateView.as_view(), name="coupon-validate"),
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
    path("customer/otp/request", customers.OtpRequestView.as_view(), name="customer-otp-request"),
    path("customer/otp/verify", customers.OtpVerifyView.as_view(), name="customer-otp-verify"),
    path("customer/me", customers.CustomerMeView.as_view(), name="customer-me"),
    path("customer/logout", customers.CustomerLogoutView.as_view(), name="customer-logout"),
    path("customer/addresses", customers.AddressListView.as_view(), name="customer-addresses"),
    path("customer/addresses/<int:address_id>", customers.AddressDetailView.as_view(), name="customer-address"),
    # Payments
    path("payments/callback", orders.PaymentCallbackView.as_view(), name="payment-callback"),
    path("payments/mock/<str:authority>", orders.MockGatewayView.as_view(), name="payment-mock"),
    # Platform: landing page plans, sign-up, subscriptions, platform admin
    path("platform/plans", platform.PlanListView.as_view(), name="platform-plans"),
    path("platform/landing", platform.LandingView.as_view(), name="platform-landing"),
    path("platform/articles", platform.ArticleListView.as_view(), name="platform-articles"),
    path("platform/articles/<str:slug>", platform.ArticleDetailView.as_view(), name="platform-article"),
    path("platform/check-subdomain", platform.SubdomainCheckView.as_view(), name="platform-check-subdomain"),
    path("platform/signup", platform.SignupView.as_view(), name="platform-signup"),
    path("platform/stores", platform.PlatformStoresView.as_view(), name="platform-stores"),
    path("platform/stores/<uuid:store_id>", platform.PlatformStoreDetailView.as_view(), name="platform-store"),
    path("admin/subscription", platform.StoreSubscriptionView.as_view(), name="admin-subscription"),
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
