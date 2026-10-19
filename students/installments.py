"""Reglas compartidas para ajustar las cuotas iniciales de una matrícula."""

LABELS = {"enrollment_fee": "matrícula", "monthly_fee": "mensualidad"}


def installment_kind(installment):
    if installment.concept == "Matrícula":
        return "enrollment_fee"
    if installment.concept.startswith("Mensualidad inicial"):
        return "monthly_fee"
    return None


def fee_conflicts(installments, fees):
    """Impide bajar un costo por debajo de lo ya cobrado en su cuota.

    `fees` mapea "enrollment_fee" y "monthly_fee" al nuevo importe.
    """
    errors = []
    for installment in installments:
        kind = installment_kind(installment)
        if kind is None or not installment.active:
            continue
        paid = installment.paid_amount
        if fees[kind] < paid:
            errors.append(
                (
                    kind,
                    f"Ya se cobró S/ {paid:.2f} de la {LABELS[kind]}; "
                    "el nuevo costo no puede ser menor.",
                )
            )
    return errors


def sync_initial_installments(enrollment, installments, refresh_due_dates=False):
    """Ajusta las cuotas iniciales a los costos actuales de la matrícula.

    Con `refresh_due_dates` también mueve el vencimiento de las cuotas que se
    conservan al inicio del curso actual.
    """
    from payments.models import Installment

    by_kind = {}
    for installment in installments:
        kind = installment_kind(installment)
        if kind and kind not in by_kind:
            by_kind[kind] = installment
    due_date = enrollment.course_start_date or enrollment.enrollment_date
    concepts = {
        "enrollment_fee": "Matrícula",
        "monthly_fee": f"Mensualidad inicial ({due_date:%Y-%m})",
    }
    for kind, concept in concepts.items():
        amount = getattr(enrollment, kind)
        installment = by_kind.get(kind)
        if installment is None:
            if amount > 0:
                Installment.objects.create(
                    enrollment=enrollment, concept=concept, amount=amount, due_date=due_date
                )
        elif amount > 0:
            changed = []
            if installment.amount != amount or not installment.active:
                installment.amount = amount
                installment.active = enrollment.active
                changed += ["amount", "active"]
            if refresh_due_dates:
                if installment.due_date != due_date:
                    installment.due_date = due_date
                    changed.append("due_date")
                if kind == "monthly_fee" and installment.concept != concept:
                    installment.concept = concept
                    changed.append("concept")
            if changed:
                installment.save(update_fields=changed)
        elif installment.active:
            installment.active = False
            installment.save(update_fields=["active"])
