from django.db import models

from accounts.models import DepartmentProfile, DoctorProfile, PatientProfile


class ServiceOrder(models.Model):
    """
    A doctor's order for a department to carry out (a CT scan, a lab
    test, etc.) and its lifecycle from PENDING -> IN_PROGRESS ->
    COMPLETED. Lives in its own app rather than inside 'doctors' or
    'departments' since both apps need to read and write it - putting it
    in either one would make the other depend on that one's internals.
    """

    class OrderType(models.TextChoices):
        CT_SCAN = "CT_SCAN", "CT Scan"
        PET_SCAN = "PET_SCAN", "PET Scan"
        LAB_TEST = "LAB_TEST", "Lab Test"
        PRESCRIPTION_FULFILLMENT = "PRESCRIPTION_FULFILLMENT", "Prescription Fulfillment"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    # Which DepartmentType is responsible for each OrderType. A CT/PET
    # scan order routes to Radiology's queue, a lab test to Laboratory's,
    # and so on - this is what lets a department only ever see orders
    # relevant to them instead of every order in the whole system.
    ORDER_TYPE_TO_DEPARTMENT_TYPE = {
        OrderType.CT_SCAN: DepartmentProfile.DepartmentType.RADIOLOGY,
        OrderType.PET_SCAN: DepartmentProfile.DepartmentType.RADIOLOGY,
        OrderType.LAB_TEST: DepartmentProfile.DepartmentType.LABORATORY,
        OrderType.PRESCRIPTION_FULFILLMENT: DepartmentProfile.DepartmentType.PHARMACY,
        OrderType.OTHER: DepartmentProfile.DepartmentType.OTHER,
    }

    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name="orders_placed")
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name="orders")
    order_type = models.CharField(max_length=30, choices=OrderType.choices)
    notes = models.TextField(blank=True, help_text="Instructions or context for the department.")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)

    claimed_by = models.ForeignKey(
        DepartmentProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders_claimed"
    )
    result_text = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def department_type_for(cls, order_type):
        return cls.ORDER_TYPE_TO_DEPARTMENT_TYPE.get(order_type, cls.OrderType.OTHER)

    @classmethod
    def order_types_for_department_type(cls, department_type):
        """Reverse lookup: which OrderTypes route to a given DepartmentType's queue."""
        return [
            order_type
            for order_type, mapped_department_type in cls.ORDER_TYPE_TO_DEPARTMENT_TYPE.items()
            if mapped_department_type == department_type
        ]

    def __str__(self):
        return f"{self.get_order_type_display()} for {self.patient.user.username} ({self.get_status_display()})"
