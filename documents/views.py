from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView, ListView, View

from accounts.models import PatientProfile, User
from doctors.models import DoctorPatientAssignment

from .crypto import decrypt_bytes, encrypt_bytes
from .forms import DocumentUploadForm
from .models import Document


def _get_authorized_patient(request, patient_pk):
    """
    Returns the PatientProfile if the requesting user is either that
    patient themselves, or a doctor assigned to them - the same
    "who's allowed to touch this patient's data" boundary used
    throughout the doctors/orders apps. Raises Http404 (not 403)
    otherwise, matching how unassigned-doctor access is handled
    elsewhere in this project, so an unauthorized request can't even
    confirm the patient record exists.
    """
    user = request.user
    patient_profile = get_object_or_404(PatientProfile, pk=patient_pk)

    if user.role == User.Role.PATIENT and hasattr(user, "patient_profile"):
        if user.patient_profile.pk == patient_profile.pk:
            return patient_profile

    if user.role == User.Role.DOCTOR and hasattr(user, "doctor_profile"):
        is_assigned = DoctorPatientAssignment.objects.filter(
            doctor=user.doctor_profile, patient=patient_profile
        ).exists()
        if is_assigned:
            return patient_profile

    raise Http404("No patient found matching the query.")


class DocumentListView(LoginRequiredMixin, ListView):
    template_name = "documents/document_list.html"
    context_object_name = "documents"

    def get_patient(self):
        return _get_authorized_patient(self.request, self.kwargs["patient_pk"])

    def get_queryset(self):
        return Document.objects.filter(patient=self.get_patient()).select_related("uploaded_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["patient"] = self.get_patient()
        context["upload_form"] = DocumentUploadForm()
        return context


class UploadDocumentView(LoginRequiredMixin, FormView):
    form_class = DocumentUploadForm
    http_method_names = ["post"]

    def get_patient(self):
        return _get_authorized_patient(self.request, self.kwargs["patient_pk"])

    def form_valid(self, form):
        patient = self.get_patient()
        uploaded_file = form.cleaned_data["file"]

        # Encryption happens here, before anything touches disk - the
        # FileField below only ever receives ciphertext, so there's no
        # intermediate step where the plaintext file exists in storage.
        raw_bytes = uploaded_file.read()
        encrypted_bytes = encrypt_bytes(raw_bytes)

        document = Document(
            patient=patient,
            uploaded_by=self.request.user,
            title=form.cleaned_data["title"],
            original_filename=uploaded_file.name,
            content_type=uploaded_file.content_type or "application/octet-stream",
        )
        document.encrypted_file.save(f"{uploaded_file.name}.enc", ContentFile(encrypted_bytes), save=True)

        messages.success(self.request, "Document uploaded and encrypted.")
        return redirect("documents:document_list", patient_pk=patient.pk)

    def form_invalid(self, form):
        # Still verify authorization even on the invalid-form path, for
        # the same reason as the analogous check in orders.views - so an
        # unauthorized user can't learn a patient_pk is valid just by
        # submitting a deliberately-broken upload.
        self.get_patient()
        messages.error(self.request, "Upload failed - please choose a file and enter a title.")
        return redirect("documents:document_list", patient_pk=self.kwargs["patient_pk"])


class DownloadDocumentView(LoginRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        _get_authorized_patient(request, document.patient.pk)  # raises Http404 if not authorized

        with document.encrypted_file.open("rb") as f:
            encrypted_bytes = f.read()
        decrypted_bytes = decrypt_bytes(encrypted_bytes)

        response = HttpResponse(decrypted_bytes, content_type=document.content_type)
        response["Content-Disposition"] = f'attachment; filename="{document.original_filename}"'
        return response
