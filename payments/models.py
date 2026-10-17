from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.core.validators import MinValueValidator, RegexValidator
from core.models import Campus, User
from students.models import Enrollment, validate_ficha_image_size

receipt_number_validator = RegexValidator(
    r"^(?:\d+|[A-Z]\d+)$",
    "Ingrese solo números o una letra mayúscula seguida de números, por ejemplo: 100 o D100.",
)


class Installment(models.Model):
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.PROTECT, related_name="installments", verbose_name="Matrícula"
    )
    concept = models.CharField("Concepto", max_length=120)
    amount = models.DecimalField(
        "Importe", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    due_date = models.DateField("Vencimiento")
    active = models.BooleanField("Activa", default=True)

    class Meta:
        ordering = ["due_date", "id"]
        verbose_name = "cuota"
        verbose_name_plural = "cuotas"

    @property
    def paid_amount(self):
        total = self.allocations.filter(payment__status=Payment.Status.CONFIRMED).aggregate(
            v=Sum("amount")
        )["v"]
        return total or Decimal("0.00")

    @property
    def balance(self):
        return self.amount - self.paid_amount

    def __str__(self):
        return f"{self.enrollment.student} — {self.concept}"


class Payment(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMADO", "Confirmado"
        VOID = "ANULADO", "Anulado"

    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.PROTECT, related_name="payments", verbose_name="Matrícula"
    )
    cashier = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="registered_payments", verbose_name="Cajero"
    )
    receipt_number = models.CharField(
        "N.º de recibo",
        max_length=40,
        validators=[receipt_number_validator],
    )
    amount = models.DecimalField(
        "Importe recibido",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reference = models.CharField("Referencia", max_length=100, blank=True)
    notes = models.CharField("Observaciones", max_length=250, blank=True)
    voucher = models.ImageField(
        "Foto del voucher",
        upload_to="vouchers/",
        blank=True,
        validators=[validate_ficha_image_size],
    )
    status = models.CharField(
        "Estado", max_length=15, choices=Status.choices, default=Status.CONFIRMED
    )
    created_at = models.DateTimeField("Fecha y hora", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "receipt_number"],
                name="unique_payment_receipt_number_per_campus",
            ),
        ]

    def save(self, *args, **kwargs):
        self.receipt_number = self.receipt_number.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.receipt_number


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="allocations", verbose_name="Pago"
    )
    installment = models.ForeignKey(
        Installment, on_delete=models.PROTECT, related_name="allocations", verbose_name="Cuota"
    )
    amount = models.DecimalField(
        "Importe aplicado",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        verbose_name = "aplicación de pago"
        verbose_name_plural = "aplicaciones de pagos"
