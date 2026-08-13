from django.urls import path

from . import views

app_name = "patients"

urlpatterns = [
    path("readings/upload/", views.UploadReadingView.as_view(), name="upload_reading"),
    path("readings/", views.ReadingListView.as_view(), name="reading_list"),
]
