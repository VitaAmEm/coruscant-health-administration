from django.urls import path

from . import views

app_name = "emergency"

urlpatterns = [
    path("intake/", views.EmergencyIntakeView.as_view(), name="intake"),
    path("intake/confirmation/", views.EmergencyIntakeConfirmationView.as_view(), name="intake_confirmation"),
    path("intake/log/", views.IntakeLogView.as_view(), name="intake_log"),
]
