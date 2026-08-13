from django import forms

from accounts.models import PatientProfile, User

from .models import Report

INPUT_CLASSES = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand"
)


class AssignPatientForm(forms.Form):
    patient_username = forms.CharField(label="Patient's username")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASSES

    def clean_patient_username(self):
        username = self.cleaned_data["patient_username"].strip()
        try:
            user = User.objects.select_related("patient_profile").get(
                username=username, role=User.Role.PATIENT
            )
        except User.DoesNotExist:
            raise forms.ValidationError("No approved patient with that username was found.")
        if not user.is_approved:
            raise forms.ValidationError("That patient's registration hasn't been approved yet.")
        try:
            return user.patient_profile
        except PatientProfile.DoesNotExist:
            raise forms.ValidationError("That patient doesn't have a complete profile yet.")


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["content"]
        widgets = {"content": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content"].widget.attrs["class"] = INPUT_CLASSES
        self.fields["content"].label = "Suggestion / prescription"
