from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import DepartmentProfile, DoctorProfile, PatientProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_approved", "is_active", "is_staff")
    list_filter = ("role", "is_approved", "is_active", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Coruscant Health role", {"fields": ("role", "is_approved")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Coruscant Health role", {"fields": ("role", "is_approved")}),
    )


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "date_of_birth", "device_id", "registered_via_emergency", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "device_id")


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "specialty", "license_number", "created_at")
    search_fields = ("user__username", "specialty", "license_number")


@admin.register(DepartmentProfile)
class DepartmentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department_type")
    list_filter = ("department_type",)
