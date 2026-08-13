from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, View

from accounts.models import PatientProfile, User

from .forms import CreateOrderForm
from .models import ServiceOrder


class CreateOrderView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Mirrors doctors.views.CreateReportView's shape and permission model
    deliberately: same "must be an assigned doctor" rule, same
    form_valid/form_invalid pattern - a report and an order are both
    "a doctor acts on a patient they're responsible for."
    """

    form_class = CreateOrderForm
    http_method_names = ["post"]

    def test_func(self):
        user = self.request.user
        return user.role == User.Role.DOCTOR and hasattr(user, "doctor_profile")

    def get_patient(self):
        # No import of doctors.models needed here: 'assigned_doctors' is
        # the reverse accessor Django creates from
        # DoctorPatientAssignment.patient's related_name, reachable
        # through PatientProfile without a direct cross-app import.
        return get_object_or_404(
            PatientProfile,
            pk=self.kwargs["pk"],
            assigned_doctors__doctor=self.request.user.doctor_profile,
        )

    def form_valid(self, form):
        patient = self.get_patient()
        form.instance.patient = patient
        form.instance.doctor = self.request.user.doctor_profile
        response = super().form_valid(form)
        messages.success(self.request, "Order placed.")
        return response

    def get_success_url(self):
        return reverse("doctors:patient_detail", args=[self.kwargs["pk"]])

    def form_invalid(self, form):
        # Verify the assignment even on the invalid path, so an
        # unassigned doctor can't learn a patient exists just by
        # submitting a deliberately-invalid order.
        self.get_patient()
        messages.error(self.request, "Order couldn't be placed - please choose an order type.")
        return redirect("doctors:patient_detail", pk=self.kwargs["pk"])


class CancelOrderView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Only the doctor who placed an order can cancel it, and only while
    it's still PENDING - once a department has claimed it (IN_PROGRESS),
    real work may already be underway, so cancellation is deliberately
    not offered past that point rather than silently discarding it.
    """

    def test_func(self):
        user = self.request.user
        return user.role == User.Role.DOCTOR and hasattr(user, "doctor_profile")

    def post(self, request, pk):
        # A plain read-then-write here would have the same race-condition
        # problem solved in departments.views.ClaimOrderView: use the same
        # atomic conditional UPDATE, so a cancel attempt racing against a
        # department's claim can't both "succeed."
        order = get_object_or_404(ServiceOrder, pk=pk, doctor=request.user.doctor_profile)
        updated_count = ServiceOrder.objects.filter(
            pk=pk, doctor=request.user.doctor_profile, status=ServiceOrder.Status.PENDING
        ).update(status=ServiceOrder.Status.CANCELLED)

        if updated_count:
            messages.success(request, "Order cancelled.")
        else:
            messages.error(
                request, "This order can no longer be cancelled - it may already be in progress."
            )
        return redirect("doctors:patient_detail", pk=order.patient.pk)
