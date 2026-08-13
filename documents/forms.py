from django import forms
from django.conf import settings

INPUT_CLASSES = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand"
)


class DocumentUploadForm(forms.Form):
    title = forms.CharField(max_length=200)
    file = forms.FileField()

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if uploaded_file.size > settings.MAX_DOCUMENT_UPLOAD_BYTES:
            limit_mb = settings.MAX_DOCUMENT_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"Files must be {limit_mb} MiB or smaller.")
        return uploaded_file

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs["class"] = INPUT_CLASSES
        self.fields["file"].widget.attrs["class"] = (
            "w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand-light "
            "file:text-brand-dark file:px-3 file:py-2 file:text-sm"
        )
