import secrets

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.template.defaultfilters import slugify
from django.urls import reverse_lazy
from django.utils.crypto import get_random_string
from django.views.generic import FormView, ListView, TemplateView

from accounts.models import PatientProfile, User

from .forms import EmergencyIntakeForm
from .models import EmergencyIntakeLog


class EmergencyRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == User.Role.EMERGENCY


def _generate_unique_username(first_name, last_name):
    """
    'quickly and efficiently' rules out asking the patient to pick their
    own username. Base it on their name with a random numeric suffix,
    retrying only in the rare case of a collision.
    """
    base = slugify(f"{first_name}-{last_name}") or "patient"
    for _ in range(20):
        candidate = f"{base}-{secrets.randbelow(9000) + 1000}"
        if not User.objects.filter(username=candidate).exists():
            return candidate
    # Astronomically unlikely to be reached given the 9000-value range
    # and retry count, but fail loudly rather than silently looping
    # forever or returning a colliding username.
    raise RuntimeError("Could not generate a unique username after 20 attempts.")


class EmergencyIntakeView(EmergencyRequiredMixin, FormView):
    form_class = EmergencyIntakeForm
    template_name = "emergency/intake.html"
    success_url = reverse_lazy("emergency:intake_confirmation")

    def form_valid(self, form):
        username = _generate_unique_username(form.cleaned_data["first_name"], form.cleaned_data["last_name"])
        password = get_random_string(12)

        # is_approved=True bypasses the normal Patient approval queue
        # (see accounts.models.User.SELF_REGISTER_ROLES) - a deliberate
        # exception for this one flow, since a patient created by
        # Emergency Services needs to be usable immediately, not pending
        # review. User.save()'s creation logic only ever *forces*
        # is_approved to True for non-self-register roles; it never resets
        # an explicitly-passed True back to False for a self-register
        # role like PATIENT, so this value is preserved as intended.
        user = User.objects.create_user(
            username=username,
            password=password,
            role=User.Role.PATIENT,
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            is_approved=True,
        )
        PatientProfile.objects.create(
            user=user,
            date_of_birth=form.cleaned_data.get("date_of_birth"),
            device_id=form.cleaned_data.get("device_id", ""),
            registered_via_emergency=True,
            must_change_password=True,
        )
        EmergencyIntakeLog.objects.create(patient_username=username, performed_by=self.request.user)

        # Passed via the session, not the URL or a template context after
        # a GET, so the one-time password isn't sitting in browser
        # history or reachable by simply revisiting the confirmation URL.
        self.request.session["emergency_new_patient"] = {
            "username": username,
            "password": password,
            "full_name": f"{form.cleaned_data['first_name']} {form.cleaned_data['last_name']}",
        }
        return super().form_valid(form)


class EmergencyIntakeConfirmationView(EmergencyRequiredMixin, TemplateView):
    template_name = "emergency/intake_confirmation.html"

    def get(self, request, *args, **kwargs):
        # .pop() rather than .get(): the credentials are shown exactly
        # once. Revisiting this URL afterward (back button, refresh,
        # bookmark) finds nothing left in the session and bounces back
        # to the intake form instead of re-displaying a stale password.
        credentials = request.session.pop("emergency_new_patient", None)
        if not credentials:
            messages.info(request, "No pending intake to confirm - start a new one below.")
            return redirect("emergency:intake")
        return self.render_to_response(self.get_context_data(credentials=credentials))


class IntakeLogView(EmergencyRequiredMixin, ListView):
    template_name = "emergency/intake_log.html"
    context_object_name = "log_entries"

    def get_queryset(self):
        return EmergencyIntakeLog.objects.select_related("performed_by")
