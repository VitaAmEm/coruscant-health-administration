from django import forms

INPUT_CLASSES = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand"
)


class EmergencyIntakeForm(forms.Form):
    """
    Deliberately minimal: an emergency intake needs to be fast, and a
    patient may arrive unable to provide much information themselves.
    Only a name is required; date of birth and device ID can be filled
    in later once the patient (or a companion) can provide them.
    """

    first_name = forms.CharField(max_length=150, help_text="Use 'Unknown' if the patient can't be identified yet.")
    last_name = forms.CharField(max_length=150)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    device_id = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASSES
