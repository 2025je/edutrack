from django.contrib import admin
from .models import Student, Course, Enrollment, Promoter

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "campus", "phone", "active")
    list_filter = ("campus", "active")
    search_fields = ("full_name", "document_number")

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "campus", "start_date", "schedule", "group", "capacity", "enrollment_fee", "monthly_fee", "active")
    list_filter = ("campus", "active")
    search_fields = ("name", "schedule", "group")

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "record_code", "promoter", "campus", "active")
    list_filter = ("campus", "active")
    search_fields = ("student__full_name", "course__name", "record_code", "promoter__name")


@admin.register(Promoter)
class PromoterAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active", "campuses")
    search_fields = ("name",)
    filter_horizontal = ("campuses",)
