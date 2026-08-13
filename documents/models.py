from django.db import models

from accounts.models import PatientProfile, User


class Document(models.Model):
    """
    A document belonging to a patient - uploaded either by the patient
    themselves or by a doctor assigned to their care. `encrypted_file`
    stores ciphertext only; the plaintext is never written to disk (see
    documents/crypto.py). `original_filename` and `content_type` are kept
    separately since the stored file's own name is just an opaque
    encrypted blob name, not something to show a person or serve a
    download as.
    """

    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="uploaded_documents")
    title = models.CharField(max_length=200)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    encrypted_file = models.FileField(upload_to="encrypted_documents/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.title} ({self.patient.user.username})"
