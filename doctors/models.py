from django.db import models

from accounts.models import DoctorProfile, PatientProfile


class DoctorPatientAssignment(models.Model):
    """
    The spec says a doctor 'views the patient record' and 'monitors' a
    patient, but never specifies how a doctor gets access to a given
    patient in the first place. Letting any approved doctor see every
    patient's data would be a real problem for a medical system, so this
    model makes that relationship explicit: a doctor can only see a
    patient's readings and write reports for them once this assignment
    exists. For this MVP, a doctor creates the assignment themselves by
    looking up a patient's username (like adding someone to their care
    panel in a real EHR) - administrator-mediated assignment would be a
    reasonable next step, but isn't required by the spec as written.
    """

    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name="assigned_patients")
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name="assigned_doctors")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["doctor", "patient"]
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"Dr. {self.doctor.user.username} <-> {self.patient.user.username}"


class Report(models.Model):
    """A doctor's written prescription/suggestion for a patient - what the
    patient sees as 'suggestions prescribed by the doctor' on their dashboard."""

    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name="reports")
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name="reports")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report for {self.patient.user.username} by Dr. {self.doctor.user.username}"


class ReportReadStatus(models.Model):
    """Tracks whether the report's intended patient has opened it."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="read_statuses")
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name="report_read_statuses")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["report", "patient"], name="unique_report_patient_read_status"),
        ]

    def __str__(self):
        return f"Read: report {self.report_id} by patient {self.patient_id}"
