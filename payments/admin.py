from django.contrib import admin
from .models import Installment, Payment, PaymentAllocation


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "concept", "amount", "due_date", "active")
    list_filter = ("active", "due_date", "enrollment__campus")
    search_fields = ("enrollment__student__full_name", "concept")


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "created_at",
        "campus",
        "enrollment",
        "cashier",
        "amount",
        "status",
    )
    list_filter = ("campus", "status", "created_at")
    search_fields = ("receipt_number", "enrollment__student__full_name", "cashier__username")
    readonly_fields = (
        "campus",
        "enrollment",
        "cashier",
        "amount",
        "reference",
        "notes",
        "created_at",
    )
    inlines = [PaymentAllocationInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ("payment", "installment", "amount")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
