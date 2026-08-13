from django.db import models

from accounts.models import User


class EmergencyIntakeLog(models.Model):
    """
    Same rationale as accounts.models.ApprovalLog: 'who registered this
    patient, and when' is a real question a medical system should be
    able to answer, not just something left implicit. Stores the
    username as plain text (not a PatientProfile FK) so the log entry
    stays meaningful even if that patient record is later changed.
    """

    patient_username = models.CharField(max_length=150)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="emergency_intakes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.patient_username} registered by {self.performed_by}"
