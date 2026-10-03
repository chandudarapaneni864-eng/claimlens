from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class ClaimUserAdmin(UserAdmin):
    list_display = ("username", "full_name", "employee_id", "role", "grade", "department", "manager")
    list_filter = ("role", "grade", "department")
    fieldsets = UserAdmin.fieldsets + (
        ("Organisation", {"fields": ("employee_id", "role", "grade", "department", "designation", "phone", "manager")}),
    )
