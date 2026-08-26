from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import TeamRoleAssignment


def get_user_role(user):
    """The single source of truth for a user's role: 'Admin', 'Booking Manager', or
    None (no Staff Role — treated as a Client everywhere in the app)."""
    if not user or not user.is_authenticated:
        return None
    assignment = (
        TeamRoleAssignment.objects
        .filter(assigned_user=user)
        .order_by("role_name")  # 'Admin' sorts before 'Booking Manager' — highest privilege wins
        .first()
    )
    return assignment.role_name if assignment else None


def is_admin(user):
    """True if `user` currently holds the single 'Admin' team role seat."""
    return get_user_role(user) == 'Admin'


def is_staff_member(user):
    """True if `user` holds ANY Staff Role (Admin or Booking Manager)."""
    return get_user_role(user) is not None


class IsAdmin(BasePermission):
    """Grants access only to the user currently holding the 'Admin' team role."""

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrReadOnly(BasePermission):
    """Any authenticated user may read; only the current Admin may write."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return is_admin(request.user)


class IsStaffMember(BasePermission):
    """Grants access only to users holding a Staff Role (Admin or Booking Manager).
    Clients — anyone with no TeamRoleAssignment row — are denied."""

    def has_permission(self, request, view):
        return is_staff_member(request.user)
