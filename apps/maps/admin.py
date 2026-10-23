from django.contrib import admin

from .models import MapLayer, MapProject, MapShare, MapShareLink


class MapLayerInline(admin.TabularInline):
    model = MapLayer
    extra = 0


class MapShareInline(admin.TabularInline):
    model = MapShare
    extra = 0
    fk_name = "map"


class MapShareLinkInline(admin.TabularInline):
    model = MapShareLink
    extra = 0
    readonly_fields = ("token", "created_at", "last_used_at")
    fields = ("token", "expires_at", "is_blocked", "created_at", "last_used_at")


@admin.register(MapProject)
class MapProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "zoom", "created_at", "updated_at")
    search_fields = ("name", "owner__username")
    inlines = [MapLayerInline, MapShareInline, MapShareLinkInline]


@admin.register(MapShareLink)
class MapShareLinkAdmin(admin.ModelAdmin):
    list_display = ("map", "token", "expires_at", "is_blocked", "created_at", "last_used_at")
    list_filter = ("is_blocked",)
    search_fields = ("token", "map__name")
    readonly_fields = ("token", "created_at", "last_used_at")
