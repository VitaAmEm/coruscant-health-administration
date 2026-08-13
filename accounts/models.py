from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    A single user model shared by every stakeholder in the spec (Patient,
    Doctor, Department, Administrator, Emergency Services), distinguished
    by `role`. Role-specific data lives in the OneToOne profile models
    below rather than on User itself, so this model stays small and the
    profile models can grow independently per role.
    """

    class Role(models.TextChoices):
        PATIENT = "PATIENT", "Patient"
        DOCTOR = "DOCTOR", "Doctor"
        DEPARTMENT = "DEPARTMENT", "Department"
        ADMINISTRATOR = "ADMINISTRATOR", "Administrator"
        EMERGENCY = "EMERGENCY", "Emergency Services"

    # Per the spec, only Patients and Doctors "register with the
    # acknowledgment from the administrator." Department and Emergency
    # Services accounts are created directly by an Administrator (e.g. via
    # the Django admin), and Administrators themselves aren't part of the
    # self-registration flow at all - so those three roles are considered
    # pre-approved the moment an Administrator creates them.
    SELF_REGISTER_ROLES = {Role.PATIENT, Role.DOCTOR}

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ADMINISTRATOR)
    is_approved = models.BooleanField(
        default=False,
        help_text="Set once an Administrator has acknowledged this registration.",
    )

    def save(self, *args, **kwargs):
        creating = self._state.adding
        if creating:
            if self.role not in self.SELF_REGISTER_ROLES or self.is_superuser:
                self.is_approved = True
            self.is_active = self.is_approved
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    date_of_birth = models.DateField(null=True, blank=True)
    device_id = models.CharField(max_length=100, blank=True, help_text="ID of the wearable device assigned to this patient.")
    registered_via_emergency = models.BooleanField(
        default=False,
        help_text="True if this patient record was created through the Emergency Services quick-intake flow.",
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text=(
            "True right after Emergency Services intake, where a staff-generated "
            "password may have been seen by someone other than the patient (a "
            "companion reading it off screen, e.g.). Forces a password change on "
            "next login rather than trusting that handoff was private."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Patient profile: {self.user.username}"


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    specialty = models.CharField(max_length=150, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Doctor profile: {self.user.username}"


class DepartmentProfile(models.Model):
    class DepartmentType(models.TextChoices):
        RADIOLOGY = "RADIOLOGY", "Radiology (CT / PET Scan)"
        LABORATORY = "LABORATORY", "Laboratory"
        PHARMACY = "PHARMACY", "Pharmacy"
        OTHER = "OTHER", "Other"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="department_profile")
    department_type = models.CharField(max_length=20, choices=DepartmentType.choices, default=DepartmentType.OTHER)

    def __str__(self):
        return f"Department profile: {self.user.username} ({self.get_department_type_display()})"


class ApprovalLog(models.Model):
    """
    A permanent audit trail of every approve/reject decision. Kept as a
    separate append-only model - rather than just toggling is_approved on
    User - for two reasons: (1) rejection deletes the User row entirely,
    so without this the fact a rejection ever happened would vanish with
    it, and (2) "who approved this doctor, and when" is exactly the kind
    of question a medical system should be able to answer, not just infer
    from a boolean's current value.
    """

    class Action(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    target_username = models.CharField(max_length=150)
    target_role = models.CharField(max_length=20, choices=User.Role.choices)
    action = models.CharField(max_length=10, choices=Action.choices)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="approval_actions"
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action}: {self.target_username} by {self.performed_by}"
