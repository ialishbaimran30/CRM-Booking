from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Persistent, queryable record of privileged business actions — role
    assignment changes, invoice create/update/void/refund, client
    create/update/delete, booking cancel/delete (SecurityFeatures.md F-1).

    Distinct from the `security` logger (core/audit.py): that emits
    authentication/authorization *events* to stdout for shipping/alerting;
    this survives log rotation and is queryable from the ORM/admin.
    """

    class Action(models.TextChoices):
        ROLE_ASSIGNED = "role_assigned", "Role assigned"
        ROLE_REMOVED = "role_removed", "Role removed"
        INVOICE_CREATED = "invoice_created", "Invoice created"
        INVOICE_UPDATED = "invoice_updated", "Invoice updated"
        INVOICE_DELETED = "invoice_deleted", "Invoice deleted"
        INVOICE_PAID = "invoice_paid", "Invoice marked paid"
        INVOICE_UNPAID = "invoice_unpaid", "Invoice marked unpaid"
        INVOICE_REFUNDED = "invoice_refunded", "Invoice refunded"
        CLIENT_CREATED = "client_created", "Client created"
        CLIENT_UPDATED = "client_updated", "Client updated"
        CLIENT_DELETED = "client_deleted", "Client deleted"
        BOOKING_CANCELLED = "booking_cancelled", "Booking cancelled"
        BOOKING_DELETED = "booking_deleted", "Booking deleted"

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    # Nullable + a denormalized email snapshot: the actor's User row can be
    # deleted later (SET_NULL, same pattern as Payment.marked_by), but the
    # audit trail must still say *who* took the action.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_log_entries",
    )
    actor_email = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    # Before/after state, where meaningful — never secrets (passwords, OTP
    # codes, tokens); only business-field values.
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["target_type", "target_id"])]

    def __str__(self):
        who = self.actor_email or "system"
        return f"{self.timestamp:%Y-%m-%d %H:%M} {who} {self.action} {self.target_type}#{self.target_id}"
