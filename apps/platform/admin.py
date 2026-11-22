from django.contrib import admin
from django.utils.html import format_html

from .models import Article, FaqItem, LandingFeature, LandingSettings, Plan, RoadmapStep, Subscription, Testimonial

admin.site.site_header = "مدیریت وب‌اسپید"
admin.site.site_title = "وب‌اسپید"
admin.site.index_title = "محتوای سایت معرفی، پلن‌ها و اشتراک‌ها"


@admin.register(LandingSettings)
class LandingSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("بخش اول (Hero)", {"fields": ("hero_badge", "hero_title", "hero_highlight", "hero_title_end", "hero_subtitle",
                                       "cta_primary", "cta_secondary", "show_stats")}),
        ("ویدیو معرفی", {"fields": ("video_title", "video_text", "video_url", "video_file", "video_poster")}),
        ("تماس و اعتماد", {"fields": ("support_phone", "support_email", "support_hours", "instagram", "telegram", "enamad_html")}),
    )

    def has_add_permission(self, request):  # single row
        return not LandingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class OrderedAdmin(admin.ModelAdmin):
    list_editable = ("sort", "active")
    list_filter = ("active",)


@admin.register(LandingFeature)
class LandingFeatureAdmin(OrderedAdmin):
    list_display = ("title", "icon", "sort", "active")
    search_fields = ("title", "text")


@admin.register(RoadmapStep)
class RoadmapStepAdmin(OrderedAdmin):
    list_display = ("title", "when", "icon", "sort", "active")


@admin.register(FaqItem)
class FaqItemAdmin(OrderedAdmin):
    list_display = ("question", "sort", "active")
    search_fields = ("question", "answer")


@admin.register(Testimonial)
class TestimonialAdmin(OrderedAdmin):
    list_display = ("name", "role", "rating", "sort", "active")
    search_fields = ("name", "text")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "published_at", "cover_preview")
    list_filter = ("status", "category")
    search_fields = ("title", "excerpt", "body")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"
    fields = ("title", "slug", "category", "excerpt", "cover", "body", "author", "status", "published_at")

    @admin.display(description="کاور")
    def cover_preview(self, obj):
        return format_html('<img src="{}" style="height:36px;border-radius:6px">', obj.cover.url) if obj.cover else "—"


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price_monthly", "price_yearly", "max_products", "highlighted", "active", "sort")
    list_editable = ("price_monthly", "price_yearly", "highlighted", "active", "sort")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("store", "plan", "status", "trial_ends_at", "paid_until")
    list_filter = ("status", "plan")
    search_fields = ("store__name", "store__slug")
    autocomplete_fields = ()
