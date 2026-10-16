from django import forms

from .models import CallNote, WhatsAppTemplate


class CallNoteForm(forms.ModelForm):
    class Meta:
        model = CallNote
        fields = ["response", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 5})}

    def clean_note(self):
        note = self.cleaned_data["note"].strip()
        if not note:
            raise forms.ValidationError("Escriba el detalle de la llamada.")
        return note


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
