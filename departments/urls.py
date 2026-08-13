from django.urls import path

from . import views

app_name = "departments"

urlpatterns = [
    path("orders/", views.OrderQueueView.as_view(), name="order_queue"),
    path("orders/<int:pk>/claim/", views.ClaimOrderView.as_view(), name="claim_order"),
    path("orders/<int:pk>/complete/", views.CompleteOrderView.as_view(), name="complete_order"),
]
