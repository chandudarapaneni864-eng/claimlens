from rest_framework.permissions import BasePermission

from .models import User

APPROVER_ROLES = {User.Role.MANAGER, User.Role.DEPT_HEAD, User.Role.HR, User.Role.FINANCE, User.Role.ADMIN}
OVERSIGHT_ROLES = {User.Role.FINANCE, User.Role.ADMIN, User.Role.HR}


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.ADMIN)


class IsFinanceOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {User.Role.FINANCE, User.Role.ADMIN}
        )


class IsOversight(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role in OVERSIGHT_ROLES)
