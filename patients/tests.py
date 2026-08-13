from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import PatientProfile, User

from .models import DeviceReading


def _make_patient(username):
    user = User.objects.create_user(
        username=username, password="Pass123!", role=User.Role.PATIENT, is_approved=True, is_active=True
    )
    return user, PatientProfile.objects.create(user=user)


class UploadReadingTests(TestCase):
    def setUp(self):
        self.patient_user, self.patient_profile = _make_patient("luke_skywalker")

    def test_patient_can_upload_a_reading(self):
        self.client.force_login(self.patient_user)
        response = self.client.post(
            reverse("patients:upload_reading"),
            {
                "reading_type": DeviceReading.ReadingType.HEART_RATE,
                "value": "72",
                "device_id": "wearable-001",
                "recorded_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertRedirects(response, reverse("patients:reading_list"))

        reading = DeviceReading.objects.get(patient=self.patient_profile)
        self.assertEqual(reading.value, "72")
        self.assertEqual(reading.reading_type, DeviceReading.ReadingType.HEART_RATE)

    def test_uploaded_reading_is_always_attributed_to_the_logged_in_patient(self):
        # Even if a malicious form submission tried to specify a different
        # patient, the view hardcodes it to request.user.patient_profile -
        # there's no "patient" field exposed in the form at all.
        other_user, other_profile = _make_patient("leia_organa")

        self.client.force_login(self.patient_user)
        self.client.post(
            reverse("patients:upload_reading"),
            {
                "reading_type": DeviceReading.ReadingType.TEMPERATURE,
                "value": "37.0",
                "device_id": "",
                "recorded_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "patient": other_profile.pk,  # not a real form field - should be ignored
            },
        )
        reading = DeviceReading.objects.get(reading_type=DeviceReading.ReadingType.TEMPERATURE)
        self.assertEqual(reading.patient, self.patient_profile)
        self.assertNotEqual(reading.patient, other_profile)

    def test_non_patient_cannot_upload_a_reading(self):
        doctor = User.objects.create_user(
            username="dr_kenobi", password="Pass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
        )
        self.client.force_login(doctor)
        response = self.client.get(reverse("patients:upload_reading"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("patients:upload_reading"))
        self.assertEqual(response.status_code, 302)


class ReadingListPrivacyTests(TestCase):
    def setUp(self):
        self.patient_a, self.profile_a = _make_patient("patient_a")
        self.patient_b, self.profile_b = _make_patient("patient_b")

        DeviceReading.objects.create(
            patient=self.profile_a,
            reading_type=DeviceReading.ReadingType.HEART_RATE,
            value="70",
            recorded_at=timezone.now(),
        )
        DeviceReading.objects.create(
            patient=self.profile_b,
            reading_type=DeviceReading.ReadingType.HEART_RATE,
            value="99",
            recorded_at=timezone.now(),
        )

    def test_patient_only_sees_their_own_readings(self):
        self.client.force_login(self.patient_a)
        response = self.client.get(reverse("patients:reading_list"))

        # Check the actual queryset the view returned, not a substring
        # match against rendered HTML - "70" as a raw string can coincide
        # with unrelated page content (e.g. a font-weight value), so this
        # is the precise way to verify privacy scoping.
        returned_ids = {reading.pk for reading in response.context["readings"]}
        self.assertEqual(
            returned_ids,
            set(DeviceReading.objects.filter(patient=self.profile_a).values_list("pk", flat=True)),
        )

    def test_other_patient_sees_only_their_own_reading(self):
        self.client.force_login(self.patient_b)
        response = self.client.get(reverse("patients:reading_list"))

        returned_ids = {reading.pk for reading in response.context["readings"]}
        self.assertEqual(
            returned_ids,
            set(DeviceReading.objects.filter(patient=self.profile_b).values_list("pk", flat=True)),
        )
