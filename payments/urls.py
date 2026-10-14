from django.urls import path
from .views import PaymentListView, PaymentCreateView, PaymentReceiptView, InstallmentListView, PendingDebtsView

urlpatterns = [
    path("", PaymentListView.as_view(), name="payment-list"),
    path("nuevo/", PaymentCreateView.as_view(), name="payment-create"),
    path("cuotas/", InstallmentListView.as_view(), name="installment-list"),
    path("deudas-pendientes/", PendingDebtsView.as_view(), name="pending-debts"),
    path("recibo/<int:pk>/", PaymentReceiptView.as_view(), name="payment-receipt"),
]
