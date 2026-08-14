from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/patient/", views.PatientRegisterView.as_view(), name="register_patient"),
    path("register/doctor/", views.DoctorRegisterView.as_view(), name="register_doctor"),
    path("login/", views.ApprovalAwareLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/", views.DashboardRedirectView.as_view(), name="dashboard"),
    path("dashboard/patient/", views.PatientDashboardView.as_view(), name="dashboard_patient"),
    path("dashboard/patient/reports/<int:pk>/", views.PatientReportDetailView.as_view(), name="patient_report_detail"),
    path("dashboard/patient/reports/", views.PatientReportListView.as_view(), name="patient_report_list"),
    path("dashboard/patient/doctors/", views.PatientDoctorListView.as_view(), name="patient_doctor_list"),
    path("dashboard/doctor/", views.DoctorDashboardView.as_view(), name="dashboard_doctor"),
    path("dashboard/department/", views.DepartmentDashboardView.as_view(), name="dashboard_department"),
    path("dashboard/emergency/", views.EmergencyDashboardView.as_view(), name="dashboard_emergency"),
    path("dashboard/administrator/", views.AdministratorDashboardView.as_view(), name="dashboard_administrator"),
    path("administrator/approvals/", views.PendingApprovalsView.as_view(), name="pending_approvals"),
    path("administrator/approvals/<int:pk>/approve/", views.ApproveUserView.as_view(), name="approve_user"),
    path("administrator/approvals/<int:pk>/reject/", views.RejectUserView.as_view(), name="reject_user"),
    path("administrator/approval-log/", views.ApprovalLogView.as_view(), name="approval_log"),
    path("force-password-change/", views.ForcePasswordChangeView.as_view(), name="force_password_change"),
]
