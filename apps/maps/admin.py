from django.contrib import admin

from .models import MapLayer, MapProject, MapShare


class MapLayerInline(admin.TabularInline):
    model = MapLayer
    extra = 0


class MapShareInline(admin.TabularInline):
    model = MapShare
    extra = 0
    fk_name = "map"


@admin.register(MapProject)
class MapProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "zoom", "created_at", "updated_at")
    search_fields = ("name", "owner__username")
    inlines = [MapLayerInline, MapShareInline]
