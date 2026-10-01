from django.contrib import admin

from .models import LayerInfo, LayerShare, LayerShareLink, LayerShareLinkUsage


class LayerShareLinkUsageInline(admin.TabularInline):
    model = LayerShareLinkUsage
    extra = 0
    can_delete = False
    readonly_fields = ("date", "request_count", "last_request_at")

    def has_add_permission(self, request, obj=None):
        return False


class LayerShareInline(admin.TabularInline):
    model = LayerShare
    extra = 0
    fk_name = "layer"


@admin.register(LayerInfo)
class LayerInfoAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "geometry_type", "feature_count", "created_at")
    list_filter = ("geometry_type",)
    search_fields = ("name", "table_name", "owner__username")
    readonly_fields = ("table_name", "schema_name", "geometry_type", "srid", "feature_count", "bounds", "attribute_schema")
    inlines = [LayerShareInline]


@admin.register(LayerShareLink)
class LayerShareLinkAdmin(admin.ModelAdmin):
    list_display = (
        "layer", "created_by", "token_preview", "expires_at", "is_blocked",
        "is_expired_display", "last_used_at", "created_at",
    )
    list_display_links = ("layer",)
    list_editable = ("is_blocked",)
    list_filter = ("is_blocked",)
    search_fields = ("token", "layer__name", "created_by__username")
    readonly_fields = ("token", "layer", "created_by", "created_at", "last_used_at")
    inlines = [LayerShareLinkUsageInline]
    actions = ["block_links", "unblock_links"]

    @admin.display(description="Token")
    def token_preview(self, obj):
        return f"{obj.token[:10]}…"

    @admin.display(description="Expired", boolean=True)
    def is_expired_display(self, obj):
        return obj.is_expired

    @admin.action(description="Block selected share links")
    def block_links(self, request, queryset):
        queryset.update(is_blocked=True)

    @admin.action(description="Unblock selected share links")
    def unblock_links(self, request, queryset):
        queryset.update(is_blocked=False)
