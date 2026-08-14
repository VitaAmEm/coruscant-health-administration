from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from accounts.models import User

from .forms import DeviceReadingForm
from .models import DeviceReading


class PatientRequiredMixin(UserPassesTestMixin):
    """Only the PATIENT role (or a superuser, for admin/debugging access) may pass."""

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.role == User.Role.PATIENT


class UploadReadingView(LoginRequiredMixin, PatientRequiredMixin, CreateView):
    form_class = DeviceReadingForm
    template_name = "patients/upload_reading.html"
    success_url = reverse_lazy("patients:reading_list")

    def form_valid(self, form):
        # The patient this reading belongs to is always the logged-in
        # user's own profile - never taken from the form/request, so
        # there's no way to submit a reading under someone else's name.
        form.instance.patient = self.request.user.patient_profile
        response = super().form_valid(form)
        messages.success(self.request, "Reading uploaded.")
        return response


class ReadingListView(LoginRequiredMixin, PatientRequiredMixin, ListView):
    template_name = "patients/reading_list.html"
    context_object_name = "readings"
    paginate_by = 20

    def get_queryset(self):
        # Scoped to the logged-in patient's own profile only - this is the
        # query that matters most for patient data privacy in this app.
        queryset = DeviceReading.objects.filter(patient=self.request.user.patient_profile)
        reading_type = self.request.GET.get("type", "").strip()
        date_from = self.request.GET.get("from", "").strip()
        date_to = self.request.GET.get("to", "").strip()
        if reading_type:
            queryset = queryset.filter(reading_type=reading_type)
        if date_from:
            queryset = queryset.filter(recorded_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(recorded_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reading_type_query"] = self.request.GET.get("type", "")
        context["date_from_query"] = self.request.GET.get("from", "")
        context["date_to_query"] = self.request.GET.get("to", "")
        context["reading_types"] = DeviceReading.ReadingType.choices
        return context
