from django.contrib import admin

from .models import LayerInfo, LayerShare


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
