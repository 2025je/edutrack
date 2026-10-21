from django import forms

from .models import CallNote, WhatsAppTemplate


class CallNoteForm(forms.ModelForm):
    wrong_phone = forms.ChoiceField(
        label="Teléfono inválido",
        required=False,
        widget=forms.Select(attrs={"class": "browser-default"}),
    )

    class Meta:
        model = CallNote
        fields = ["response", "note", "promise_date"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 5}),
            "promise_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.valid_phones = (
            [p.strip() for p in student.phone.split(",") if p.strip()] if student else []
        )
        self.fields["wrong_phone"].choices = [("", "Elige el teléfono")] + [
            (p, p) for p in self.valid_phones
        ]
        self.fields["response"].widget.attrs["onchange"] = (
            "var p=document.getElementById('promise-box');"
            f"if(p)p.style.display=this.value==='{CallNote.Response.PROMISED_PAYMENT}'?'':'none';"
            "var w=document.getElementById('wrong-box');"
            f"if(w)w.style.display=this.value==='{CallNote.Response.WRONG_NUMBER}'?'':'none'"
        )

    def clean(self):
        cleaned = super().clean()
        promised = cleaned.get("response") == CallNote.Response.PROMISED_PAYMENT
        if promised and not cleaned.get("promise_date"):
            self.add_error("promise_date", "Indique la fecha en que prometió pagar.")
        if not promised:
            cleaned["promise_date"] = None
        if cleaned.get("response") == CallNote.Response.WRONG_NUMBER:
            if not cleaned.get("wrong_phone") and len(self.valid_phones) == 1:
                cleaned["wrong_phone"] = self.valid_phones[0]
            elif not cleaned.get("wrong_phone") and len(self.valid_phones) > 1:
                self.add_error("wrong_phone", "Indique cuál teléfono es inválido.")
        else:
            cleaned["wrong_phone"] = ""
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
