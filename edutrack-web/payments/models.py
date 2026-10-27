from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ProtectedError, Q, Sum
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
        indexes = [
            models.Index(
                fields=["enrollment", "active", "due_date"], name="installment_enroll_due"
            ),
        ]

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
        return f"{self.enrollment.student_label} — {self.concept}"


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
    voided_on_deactivation = models.BooleanField(
        "Anulado al dar de baja", default=False, editable=False
    )
    created_at = models.DateTimeField("Fecha y hora", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        indexes = [
            models.Index(
                fields=["campus", "status", "-created_at"], name="payment_campus_status_date"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "receipt_number"],
                name="unique_payment_receipt_number_per_campus",
            ),
        ]

    def save(self, *args, **kwargs):
        self.receipt_number = self.receipt_number.strip().upper()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError(
            "Los pagos no se eliminan; deben anularse para conservar el historial.", {self}
        )

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
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="allocation_amount_positive"),
        ]

    def clean(self):
        """Reglas críticas: misma matrícula y sin exceder el pago ni la cuota."""
        if not self.payment_id or not self.installment_id:
            return
        payment, installment = self.payment, self.installment
        if installment.enrollment_id != payment.enrollment_id:
            raise ValidationError("La cuota debe pertenecer a la misma matrícula del pago.")
        if self.amount is None:
            return
        others = PaymentAllocation.objects.exclude(pk=self.pk)
        applied_to_payment = others.filter(payment=payment).aggregate(v=Sum("amount"))["v"]
        if (applied_to_payment or Decimal("0.00")) + self.amount > payment.amount:
            raise ValidationError("Lo aplicado no puede exceder el importe recibido del pago.")
        if payment.status == Payment.Status.CONFIRMED:
            applied_to_installment = others.filter(
                installment=installment, payment__status=Payment.Status.CONFIRMED
            ).aggregate(v=Sum("amount"))["v"]
            if (applied_to_installment or Decimal("0.00")) + self.amount > installment.amount:
                raise ValidationError("Lo aplicado no puede exceder el importe de la cuota.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class CashClosing(models.Model):
    """Cierre de caja de un día: congela los totales y bloquea cambios en los pagos de esa fecha."""

    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="cash_closings", verbose_name="Sede"
    )
    date = models.DateField("Fecha")
    confirmed_total = models.DecimalField("Total confirmado", max_digits=12, decimal_places=2)
    voided_total = models.DecimalField("Total anulado", max_digits=12, decimal_places=2)
    payments_count = models.PositiveIntegerField("Pagos del día")
    note = models.CharField("Observación", max_length=255, blank=True)
    closed_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="cash_closings",
        verbose_name="Cerrada por",
    )
    closed_at = models.DateTimeField("Cerrada el", auto_now_add=True)

    class Meta:
        verbose_name = "cierre de caja"
        verbose_name_plural = "cierres de caja"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["campus", "date"], name="unique_cash_closing_per_day"),
        ]

    def __str__(self):
        return f"Cierre {self.campus} {self.date:%d/%m/%Y}"


def is_cash_closed(campus_id, day):
    return CashClosing.objects.filter(campus_id=campus_id, date=day).exists()
