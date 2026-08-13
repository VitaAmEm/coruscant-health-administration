from django.db import models

from accounts.models import PatientProfile


class DeviceReading(models.Model):
    """
    A single health reading uploaded for a patient - either logged by the
    patient themselves from their wearable device, or (later) synced
    automatically. Real device integration is out of scope here; this MVP
    covers the "uploads the data collected by the device" requirement via
    manual entry, which is honest about what it actually does rather than
    simulating a device connection that doesn't exist.
    """

    class ReadingType(models.TextChoices):
        HEART_RATE = "HEART_RATE", "Heart Rate (bpm)"
        BLOOD_PRESSURE = "BLOOD_PRESSURE", "Blood Pressure (mmHg)"
        TEMPERATURE = "TEMPERATURE", "Temperature (°C)"
        OXYGEN_SATURATION = "OXYGEN_SATURATION", "Oxygen Saturation (%)"
        GLUCOSE = "GLUCOSE", "Blood Glucose (mg/dL)"
        OTHER = "OTHER", "Other"

    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name="device_readings")
    reading_type = models.CharField(max_length=30, choices=ReadingType.choices)
    # Stored as text rather than a plain number: blood pressure readings are
    # naturally "120/80", not a single float, and forcing every reading
    # type into one numeric column would either break that or require a
    # second column most reading types never use.
    value = models.CharField(max_length=50, help_text="e.g. '72' for heart rate, or '120/80' for blood pressure")
    device_id = models.CharField(max_length=100, blank=True)
    recorded_at = models.DateTimeField(help_text="When the device captured this reading.")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.patient.user.username}: {self.get_reading_type_display()} = {self.value}"
