from django.urls import path

from . import views

app_name = "doctors"

urlpatterns = [
    path("patients/", views.PatientListView.as_view(), name="patient_list"),
    path("patients/assign/", views.AssignPatientView.as_view(), name="assign_patient"),
    path("patients/<int:pk>/", views.PatientDetailView.as_view(), name="patient_detail"),
    path("patients/<int:pk>/report/", views.CreateReportView.as_view(), name="create_report"),
]
