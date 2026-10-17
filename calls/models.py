from django.db import models

from core.models import Campus, User

DEFAULT_WHATSAPP_TEMPLATE = (
    "Hola {alumno}, le saludamos de {sede}. "
    "Le recordamos que tiene una deuda pendiente de S/ {deuda_total}:\n"
    "{detalle_deuda}\n"
    "Por favor regularice su pago. ¡Gracias!"
)

EMOJIS = [
    "👋",
    "😊",
    "🙂",
    "😀",
    "😃",
    "😄",
    "😁",
    "😉",
    "🤗",
    "😇",
    "🥰",
    "😍",
    "🤝",
    "🙏",
    "🙌",
    "👏",
    "👍",
    "👌",
    "✌️",
    "💪",
    "👉",
    "👈",
    "👆",
    "👇",
    "☝️",
    "✍️",
    "🤞",
    "🫶",
    "📚",
    "📖",
    "📝",
    "✏️",
    "🎓",
    "🏫",
    "🏢",
    "💻",
    "🖥️",
    "📱",
    "📲",
    "☎️",
    "📞",
    "📧",
    "💬",
    "🗣️",
    "💰",
    "💵",
    "💳",
    "💸",
    "🧾",
    "🏦",
    "📊",
    "📈",
    "📉",
    "🪙",
    "💲",
    "🔔",
    "📢",
    "📣",
    "📅",
    "📆",
    "🗓️",
    "⏰",
    "⌛",
    "⏳",
    "🕒",
    "🕘",
    "🔜",
    "🔝",
    "📌",
    "📍",
    "⚠️",
    "❗",
    "❕",
    "❓",
    "‼️",
    "🚨",
    "🛑",
    "⛔",
    "🚫",
    "❌",
    "✅",
    "✔️",
    "☑️",
    "⭐",
    "🌟",
    "✨",
    "🎉",
    "🎊",
    "🏆",
    "🥇",
    "🎁",
    "❤️",
    "💙",
    "💚",
    "💛",
    "🔥",
    "🚀",
    "💡",
    "🔒",
    "🔑",
    "🙏🏻",
    "😅",
]

PLACEHOLDERS = {
    "{alumno}": "Nombre del alumno",
    "{sede}": "Nombre de la sede",
    "{deuda_total}": "Deuda total del alumno (solo el número)",
    "{detalle_deuda}": "Una línea por curso con deuda: curso y monto",
}


class WhatsAppTemplate(models.Model):
    campus = models.OneToOneField(
        Campus, on_delete=models.CASCADE, related_name="whatsapp_template", verbose_name="Sede"
    )
    body = models.TextField("Mensaje", default=DEFAULT_WHATSAPP_TEMPLATE, max_length=1000)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "plantilla de WhatsApp"
        verbose_name_plural = "plantillas de WhatsApp"

    def render(self, **values):
        text = self.body
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        return text


class CallAssignment(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="call_assignments", verbose_name="Usuario"
    )
    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="call_assignments",
        verbose_name="Matrícula",
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Asignado por",
    )
    created_at = models.DateTimeField("Asignado el", auto_now_add=True)

    class Meta:
        verbose_name = "asignación de llamada"
        verbose_name_plural = "asignaciones de llamadas"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "enrollment"], name="unique_call_assignment_per_user_enrollment"
            )
        ]

    def __str__(self):
        return f"{self.user} → {self.enrollment}"


class CallNote(models.Model):
    class Response(models.TextChoices):
        WILL_ATTEND = "ASISTIRA", "Asistirá"
        WONT_ATTEND = "NO_ASISTIRA", "No asistirá"
        OTHER = "OTROS", "Otros"

    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.PROTECT,
        related_name="call_notes",
        verbose_name="Alumno",
    )
    author = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="call_notes", verbose_name="Registrado por"
    )
    response = models.CharField(
        "Tipo de respuesta", max_length=15, choices=Response.choices, default=Response.OTHER
    )
    note = models.TextField("Detalle", max_length=1000)
    created_at = models.DateTimeField("Fecha y hora", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "registro de llamada"
        verbose_name_plural = "historial de llamadas"

    def __str__(self):
        return f"{self.student} - {self.created_at:%d/%m/%Y %H:%M}"
