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
    "{fecha_promesa}": "Fecha en que el alumno prometió pagar (plantilla de promesa incumplida)",
}

DEFAULT_PROMISE_TEMPLATE = (
    "Hola {alumno}, le saludamos de {sede}. "
    "El {fecha_promesa} quedamos en que realizaría su pago y aún figura una deuda de "
    "S/ {deuda_total}:\n{detalle_deuda}\n"
    "¿Nos confirma cuándo podrá realizarlo? ¡Gracias!"
)
DEFAULT_WELCOME_TEMPLATE = (
    "¡Hola {alumno}! Te damos la bienvenida a {sede}. "
    "Quedamos atentos a cualquier consulta sobre tus clases. ¡Gracias por confiar en nosotros!"
)


class WhatsAppTemplate(models.Model):
    class Kind(models.TextChoices):
        DEBT = "DEUDA", "Deuda vencida"
        PROMISE = "PROMESA", "Promesa incumplida"
        WELCOME = "BIENVENIDA", "Bienvenida"

    DEFAULT_BODIES = {
        Kind.DEBT: DEFAULT_WHATSAPP_TEMPLATE,
        Kind.PROMISE: DEFAULT_PROMISE_TEMPLATE,
        Kind.WELCOME: DEFAULT_WELCOME_TEMPLATE,
    }

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="whatsapp_templates", verbose_name="Sede"
    )
    kind = models.CharField("Situación", max_length=12, choices=Kind.choices, default=Kind.DEBT)
    body = models.TextField("Mensaje", default=DEFAULT_WHATSAPP_TEMPLATE, max_length=1000)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "plantilla de WhatsApp"
        verbose_name_plural = "plantillas de WhatsApp"
        constraints = [
            models.UniqueConstraint(fields=["campus", "kind"], name="unique_whatsapp_kind_campus"),
        ]

    @classmethod
    def for_campus(cls, campus):
        """Plantillas de la sede por situación; las que no existen usan el texto por defecto."""
        found = {t.kind: t for t in cls.objects.filter(campus=campus)}
        return {
            kind: found.get(kind) or cls(campus=campus, kind=kind, body=cls.DEFAULT_BODIES[kind])
            for kind in cls.Kind.values
        }

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
        NO_ANSWER = "NO_CONTESTO", "No contestó"
        PROMISED_PAYMENT = "PROMETIO_PAGO", "Prometió pago"
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
    promise_date = models.DateField("Fecha prometida de pago", null=True, blank=True)
    created_at = models.DateTimeField("Fecha y hora", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "registro de llamada"
        verbose_name_plural = "historial de llamadas"

    def __str__(self):
        return f"{self.student} - {self.created_at:%d/%m/%Y %H:%M}"
