from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Campus, User


@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "address", "has_logo")
    list_filter = ("active",)
    search_fields = ("name",)

    @admin.display(boolean=True, description="Tiene logo")
    def has_logo(self, campus):
        return bool(campus.logo)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Acceso al sistema",
            {
                "fields": (
                    "campuses",
                    "can_manage_students",
                    "can_register_payments",
                    "can_manage_promoters",
                    "can_manage_calls",
                    "can_edit_call_notes",
                    "can_manage_campuses",
                )
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Acceso al sistema",
            {
                "fields": (
                    "campuses",
                    "can_manage_students",
                    "can_register_payments",
                    "can_manage_promoters",
                    "can_manage_calls",
                    "can_edit_call_notes",
                    "can_manage_campuses",
                )
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions", "campuses")
    list_display = (
        "username",
        "first_name",
        "last_name",
        "can_manage_students",
        "can_register_payments",
        "can_manage_promoters",
        "can_manage_calls",
        "can_edit_call_notes",
        "can_manage_campuses",
        "is_staff",
        "is_active",
    )
