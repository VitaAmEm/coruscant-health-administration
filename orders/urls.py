from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("patients/<int:pk>/create/", views.CreateOrderView.as_view(), name="create_order"),
    path("<int:pk>/cancel/", views.CancelOrderView.as_view(), name="cancel_order"),
]
