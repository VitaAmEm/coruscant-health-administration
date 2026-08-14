from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, TemplateView

from .forms import ApprovalAwareLoginForm, DoctorRegistrationForm, PatientRegistrationForm
from .models import ApprovalLog, User


def _notify_by_email(email, subject, message):
    """
    Best-effort notification: if email sending fails (e.g. no SMTP
    configured yet), the approval/rejection itself must still succeed -
    a broken mail server shouldn't be able to block an administrator from
    approving a doctor. Failures are swallowed here rather than raised.
    Takes a raw email address instead of a User object so it still works
    after RejectUserView has already deleted the row it's about.
    """
    if not email:
        return
    try:
        send_mail(subject, message, None, [email], fail_silently=True)
    except Exception:
        pass


class PatientRegisterView(CreateView):
    form_class = PatientRegistrationForm
    template_name = "accounts/register_patient.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Your registration was submitted. An administrator needs to approve "
            "your account before you can log in.",
        )
        return response


class DoctorRegisterView(CreateView):
    form_class = DoctorRegistrationForm
    template_name = "accounts/register_doctor.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Your registration was submitted. An administrator needs to approve "
            "your account before you can log in.",
        )
        return response


class ApprovalAwareLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = ApprovalAwareLoginForm
    redirect_authenticated_user = True


class DashboardRedirectView(LoginRequiredMixin, TemplateView):
    """
    A single '/dashboard/' entry point that sends every stakeholder to
    their own role-specific dashboard, so links/bookmarks/tests don't need
    to know each role's URL in advance - they just need to know the user
    is logged in.
    """

    ROLE_URL_NAMES = {
        User.Role.PATIENT: "accounts:dashboard_patient",
        User.Role.DOCTOR: "accounts:dashboard_doctor",
        User.Role.DEPARTMENT: "accounts:dashboard_department",
        User.Role.ADMINISTRATOR: "accounts:dashboard_administrator",
        User.Role.EMERGENCY: "accounts:dashboard_emergency",
    }

    def get(self, request, *args, **kwargs):
        url_name = self.ROLE_URL_NAMES.get(request.user.role)
        if url_name is None:
            raise PermissionDenied("This account has no recognized role.")
        return redirect(url_name)


class RoleDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Base class for a role's dashboard: only that role (or a superuser) may view it."""

    required_role = None

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.role == self.required_role


class PatientDashboardView(RoleDashboardView):
    required_role = User.Role.PATIENT
    template_name = "accounts/dashboard_patient.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Imported here (rather than at module level) to avoid accounts,
        # the foundation app, taking on a hard top-level dependency on
        # patients/doctors, apps built on top of it - only this one view
        # needs these models, so the imports stay local to where used.
        from doctors.models import Report
        from patients.models import DeviceReading

        patient_profile = getattr(self.request.user, "patient_profile", None)
        if patient_profile is not None:
            context["recent_readings"] = DeviceReading.objects.filter(patient=patient_profile)[:5]
            context["reports"] = Report.objects.filter(patient=patient_profile).select_related("doctor__user")[:5]
        else:
            context["recent_readings"] = []
            context["reports"] = []
        return context


class PatientReportDetailView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/patient_report_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != User.Role.PATIENT:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from doctors.models import Report

        context["report"] = get_object_or_404(
            Report.objects.select_related("doctor__user", "patient__user"),
            pk=self.kwargs["pk"],
            patient__user=self.request.user,
        )
        return context


class DoctorDashboardView(RoleDashboardView):
    required_role = User.Role.DOCTOR
    template_name = "accounts/dashboard_doctor.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        doctor_profile = getattr(self.request.user, "doctor_profile", None)
        if doctor_profile is not None:
            context["patient_count"] = doctor_profile.assigned_patients.count()
        else:
            context["patient_count"] = 0
        return context


class DepartmentDashboardView(RoleDashboardView):
    required_role = User.Role.DEPARTMENT
    template_name = "accounts/dashboard_department.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department_profile = getattr(self.request.user, "department_profile", None)
        if department_profile is not None:
            from orders.models import ServiceOrder

            relevant_types = ServiceOrder.order_types_for_department_type(department_profile.department_type)
            context["pending_count"] = ServiceOrder.objects.filter(
                status=ServiceOrder.Status.PENDING, order_type__in=relevant_types
            ).count()
        else:
            context["pending_count"] = 0
        return context


class EmergencyDashboardView(RoleDashboardView):
    required_role = User.Role.EMERGENCY
    template_name = "accounts/dashboard_emergency.html"


class AdministratorDashboardView(RoleDashboardView):
    required_role = User.Role.ADMINISTRATOR
    template_name = "accounts/dashboard_administrator.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending_count"] = User.objects.filter(
            role__in=User.SELF_REGISTER_ROLES, is_approved=False
        ).count()
        return context


class PendingApprovalsView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    template_name = "accounts/pending_approvals.html"
    context_object_name = "pending_users"

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.role == User.Role.ADMINISTRATOR

    def get_queryset(self):
        return (
            User.objects.filter(role__in=User.SELF_REGISTER_ROLES, is_approved=False)
            .select_related("patient_profile", "doctor_profile")
            .order_by("date_joined")
        )


class ApproveUserView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.role == User.Role.ADMINISTRATOR

    def post(self, request, *args, **kwargs):
        target = get_object_or_404(User, pk=kwargs["pk"], role__in=User.SELF_REGISTER_ROLES)
        target.is_approved = True
        target.is_active = True
        target.save(update_fields=["is_approved", "is_active"])
        ApprovalLog.objects.create(
            target_username=target.username,
            target_role=target.role,
            action=ApprovalLog.Action.APPROVED,
            performed_by=request.user,
            reason=request.POST.get("reason", ""),
        )
        _notify_by_email(
            target.email,
            subject="Your Coruscant Health account has been approved",
            message=(
                f"Hello {target.get_full_name() or target.username},\n\n"
                "Your Coruscant Health Administration account has been approved. "
                "You can now log in and access your dashboard."
            ),
        )
        messages.success(request, f"{target.username} has been approved and can now log in.")
        return redirect("accounts:pending_approvals")


class ApprovalLogView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    template_name = "accounts/approval_log.html"
    context_object_name = "log_entries"
    paginate_by = 25

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.role == User.Role.ADMINISTRATOR

    def get_queryset(self):
        return ApprovalLog.objects.select_related("performed_by")


class ForcePasswordChangeView(LoginRequiredMixin, FormView):
    """
    Where a patient created via Emergency Services lands if
    PatientProfile.must_change_password is still True - enforced by
    ForcePasswordChangeMiddleware, not just a link someone might skip.
    """

    template_name = "accounts/force_password_change.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("accounts:dashboard")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.save()
        # Without this, changing your own password mid-session invalidates
        # the current session hash and immediately logs you out - exactly
        # the opposite of what should happen right after finally setting a
        # real password.
        update_session_auth_hash(self.request, user)

        patient_profile = getattr(user, "patient_profile", None)
        if patient_profile is not None:
            patient_profile.must_change_password = False
            patient_profile.save(update_fields=["must_change_password"])

        messages.success(self.request, "Password updated.")
        return super().form_valid(form)


class RejectUserView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.role == User.Role.ADMINISTRATOR

    def post(self, request, *args, **kwargs):
        target = get_object_or_404(User, pk=kwargs["pk"], role__in=User.SELF_REGISTER_ROLES, is_approved=False)
        username = target.username
        role = target.role
        reason = request.POST.get("reason", "")

        # Capture what we need for the email and log before deleting the row.
        target_email = target.email
        target_full_name = target.get_full_name()

        target.delete()
        ApprovalLog.objects.create(
            target_username=username,
            target_role=role,
            action=ApprovalLog.Action.REJECTED,
            performed_by=request.user,
            reason=reason,
        )
        if target_email:
            message = f"Hello {target_full_name or username},\n\nYour Coruscant Health Administration registration was not approved."
            if reason:
                message += f"\n\nReason given: {reason}"
            _notify_by_email(
                target_email,
                subject="Your Coruscant Health registration was not approved",
                message=message,
            )
        messages.info(request, f"{username}'s registration was rejected and removed.")
        return redirect("accounts:pending_approvals")
