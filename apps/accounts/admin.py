from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Role, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Roles & Organization", {"fields": ("roles", "organization")}),
    )
    filter_horizontal = BaseUserAdmin.filter_horizontal + ("roles",)
    list_display = ("username", "email", "first_name", "last_name", "is_staff")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "user_count", "created_at")
    filter_horizontal = ("permissions",)
    search_fields = ("name",)

    def user_count(self, obj):
        return obj.users.count()
