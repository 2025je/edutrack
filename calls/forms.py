from django import forms

from .models import CallNote, WhatsAppTemplate


class CallNoteForm(forms.ModelForm):
    class Meta:
        model = CallNote
        fields = ["response", "note", "promise_date"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 5}),
            "promise_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["response"].widget.attrs["onchange"] = (
            "document.getElementById('promise-box').style.display="
            f"this.value==='{CallNote.Response.PROMISED_PAYMENT}'?'':'none'"
        )

    def clean(self):
        cleaned = super().clean()
        promised = cleaned.get("response") == CallNote.Response.PROMISED_PAYMENT
        if promised and not cleaned.get("promise_date"):
            self.add_error("promise_date", "Indique la fecha en que prometió pagar.")
        if not promised:
            cleaned["promise_date"] = None
        return cleaned

    def clean_note(self):
        note = self.cleaned_data["note"].strip()
        if not note:
            raise forms.ValidationError("Escriba el detalle de la llamada.")
        return note


class QuickCallNoteForm(CallNoteForm):
    """Registro rápido desde la lista: el detalle es opcional."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].required = False

    def clean_note(self):
        return self.cleaned_data["note"].strip()


class WhatsAppTemplateForm(forms.ModelForm):
    class Meta:
        model = WhatsAppTemplate
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 8})}

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Escriba el mensaje.")
        return body
