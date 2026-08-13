from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("patients/<int:patient_pk>/", views.DocumentListView.as_view(), name="document_list"),
    path("patients/<int:patient_pk>/upload/", views.UploadDocumentView.as_view(), name="upload_document"),
    path("<int:pk>/download/", views.DownloadDocumentView.as_view(), name="download_document"),
]
