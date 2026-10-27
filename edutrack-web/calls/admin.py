from django.contrib import admin

from .models import CallNote


@admin.register(CallNote)
class CallNoteAdmin(admin.ModelAdmin):
    list_display = ("student", "campus", "author", "created_at")
    list_filter = ("campus",)
    search_fields = ("student__full_name", "note")
    readonly_fields = ("created_at",)
