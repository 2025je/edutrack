from django.urls import path
from .views import (
    EnrollmentStatementView,
    PaymentExcelExportView,
    CashClosingView,
    CashClosingExcelView,
    PaymentListView,
    PendingDebtsExcelView,
    PaymentSelectView,
    PaymentCreateView,
    PaymentUpdateView,
    PaymentDeleteView,
    PaymentReceiptView,
    InstallmentListView,
    PendingDebtsView,
)

urlpatterns = [
    path("", PaymentListView.as_view(), name="payment-list"),
    path("exportar/", PaymentExcelExportView.as_view(), name="payment-excel"),
    path("cierre-de-caja/", CashClosingView.as_view(), name="cash-closing"),
    path("cierre-de-caja/exportar/", CashClosingExcelView.as_view(), name="cash-closing-excel"),
    path("nuevo/", PaymentSelectView.as_view(), name="payment-create"),
    path("nuevo/<int:enrollment_id>/", PaymentCreateView.as_view(), name="payment-create-for"),
    path("<int:pk>/editar/", PaymentUpdateView.as_view(), name="payment-update"),
    path("<int:pk>/eliminar/", PaymentDeleteView.as_view(), name="payment-delete"),
    path("cuotas/", InstallmentListView.as_view(), name="installment-list"),
    path("deudas-pendientes/", PendingDebtsView.as_view(), name="pending-debts"),
    path(
        "deudas-pendientes/exportar/", PendingDebtsExcelView.as_view(), name="pending-debts-excel"
    ),
    path(
        "estado-de-cuenta/<int:enrollment_id>/",
        EnrollmentStatementView.as_view(),
        name="enrollment-statement",
    ),
    path("recibo/<int:pk>/", PaymentReceiptView.as_view(), name="payment-receipt"),
]
