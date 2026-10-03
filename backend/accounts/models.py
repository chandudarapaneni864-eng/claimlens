from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        MANAGER = "MANAGER", "Manager"
        DEPT_HEAD = "DEPT_HEAD", "Department head"
        HR = "HR", "HR"
        FINANCE = "FINANCE", "Finance"
        ADMIN = "ADMIN", "Administrator"

    class Grade(models.TextChoices):
        L1 = "L1", "L1 · Associate"
        L2 = "L2", "L2 · Senior associate"
        L3 = "L3", "L3 · Lead / Manager"
        L4 = "L4", "L4 · Senior leadership"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    grade = models.CharField(max_length=4, choices=Grade.choices, default=Grade.L1)
    department = models.CharField(max_length=80, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    employee_id = models.CharField(max_length=30, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports"
    )

    class Meta:
        ordering = ["first_name", "last_name", "username"]

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.username

    @property
    def is_approver(self):
        return self.role in {self.Role.MANAGER, self.Role.DEPT_HEAD, self.Role.HR, self.Role.FINANCE, self.Role.ADMIN}

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"
