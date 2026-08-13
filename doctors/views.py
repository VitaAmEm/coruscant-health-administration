from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, FormView, ListView

from accounts.models import PatientProfile, User

from .forms import AssignPatientForm, ReportForm
from .models import DoctorPatientAssignment, Report
from .utils import compute_trends


class DoctorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Deliberately no superuser bypass here, unlike some other role mixins
    in this project: every view in this app either creates or reads data
    attached to a DoctorProfile, and a superuser created via
    createsuperuser has no DoctorProfile to attach it to. "Acting as a
    doctor" isn't a meaningful concept for an account that isn't one.
    """

    def test_func(self):
        user = self.request.user
        return user.role == User.Role.DOCTOR and hasattr(user, "doctor_profile")


class PatientListView(DoctorRequiredMixin, ListView):
    template_name = "doctors/patient_list.html"
    context_object_name = "patients"

    def get_queryset(self):
        return PatientProfile.objects.filter(
            assigned_doctors__doctor=self.request.user.doctor_profile
        ).select_related("user").distinct()


class AssignPatientView(DoctorRequiredMixin, FormView):
    form_class = AssignPatientForm
    template_name = "doctors/assign_patient.html"

    def form_valid(self, form):
        patient_profile = form.cleaned_data["patient_username"]  # clean_* already resolves to the profile
        _, created = DoctorPatientAssignment.objects.get_or_create(
            doctor=self.request.user.doctor_profile, patient=patient_profile
        )
        if created:
            messages.success(self.request, f"{patient_profile.user.username} was added to your patients.")
        else:
            messages.info(self.request, f"{patient_profile.user.username} was already in your patients.")
        return redirect("doctors:patient_list")


class AssignedPatientMixin(DoctorRequiredMixin):
    """Shared by any view that operates on one specific patient - only
    proceeds if that patient is actually assigned to this doctor."""

    def get_patient(self):
        return get_object_or_404(
            PatientProfile,
            pk=self.kwargs["pk"],
            assigned_doctors__doctor=self.request.user.doctor_profile,
        )


class PatientDetailView(AssignedPatientMixin, DetailView):
    template_name = "doctors/patient_detail.html"
    context_object_name = "patient"

    def get_object(self, queryset=None):
        return self.get_patient()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        readings = list(self.object.device_readings.all()[:30])
        context["readings"] = readings
        context["trends"] = compute_trends(readings)
        context["reports"] = self.object.reports.select_related("doctor__user")
        context["report_form"] = ReportForm()
        # Local import: doctors reads orders' model to display it here,
        # while orders reads doctors' model to check assignment when
        # creating one - the same lazy cross-app pattern used throughout
        # this project rather than a module-level circular import.
        from orders.forms import CreateOrderForm
        from orders.models import ServiceOrder

        context["orders"] = ServiceOrder.objects.filter(patient=self.object).select_related("claimed_by__user")
        context["order_form"] = CreateOrderForm()
        return context


class CreateReportView(AssignedPatientMixin, CreateView):
    form_class = ReportForm
    http_method_names = ["post"]

    def form_valid(self, form):
        patient = self.get_patient()
        form.instance.patient = patient
        form.instance.doctor = self.request.user.doctor_profile
        response = super().form_valid(form)
        messages.success(self.request, "Report saved.")
        return response

    def get_success_url(self):
        return reverse("doctors:patient_detail", args=[self.kwargs["pk"]])

    def form_invalid(self, form):
        messages.error(self.request, "Report couldn't be saved - please enter some content.")
        return redirect("doctors:patient_detail", pk=self.kwargs["pk"])
