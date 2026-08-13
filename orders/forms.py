from django import forms

from .models import ServiceOrder

INPUT_CLASSES = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand"
)


class CreateOrderForm(forms.ModelForm):
    class Meta:
        model = ServiceOrder
        fields = ["order_type", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASSES


class CompleteOrderForm(forms.ModelForm):
    class Meta:
        model = ServiceOrder
        fields = ["result_text"]
        widgets = {"result_text": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["result_text"].required = True
        self.fields["result_text"].label = "Result"
        self.fields["result_text"].widget.attrs["class"] = INPUT_CLASSES
