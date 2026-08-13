from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import DoctorProfile, PatientProfile, User

INPUT_CLASSES = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand"
)


def _style_fields(fields):
    """Apply consistent Tailwind classes to every widget in a form's fields dict."""
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing} {INPUT_CLASSES}".strip()


class PatientRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    date_of_birth = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    device_id = forms.CharField(
        required=False,
        help_text="If you already know the ID of your assigned wearable device, enter it here.",
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self.fields)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PATIENT
        if commit:
            user.save()
            PatientProfile.objects.create(
                user=user,
                date_of_birth=self.cleaned_data.get("date_of_birth"),
                device_id=self.cleaned_data.get("device_id", ""),
            )
        return user


class DoctorRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    specialty = forms.CharField(required=False)
    license_number = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self.fields)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.DOCTOR
        if commit:
            user.save()
            DoctorProfile.objects.create(
                user=user,
                specialty=self.cleaned_data.get("specialty", ""),
                license_number=self.cleaned_data["license_number"],
            )
        return user


class ApprovalAwareLoginForm(AuthenticationForm):
    """
    Standard Django auth blocks inactive users before this form's
    confirm_login_allowed() hook is even reached, which produces a vague
    "invalid credentials" message for someone whose account is simply
    pending approval - not what actually happened. Pairing this form with
    AUTHENTICATION_BACKENDS = [AllowAllUsersModelBackend] (see settings.py)
    lets authentication succeed regardless of is_active, so this hook can
    give an accurate, specific reason instead.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self.fields)

    def confirm_login_allowed(self, user):
        if user.is_active:
            return
        if user.role in User.SELF_REGISTER_ROLES and not user.is_approved:
            raise forms.ValidationError(
                "Your account is still awaiting administrator approval.",
                code="pending_approval",
            )
        raise forms.ValidationError("This account is inactive.", code="inactive")
