from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DoctorProfile, PatientProfile, User
from patients.models import DeviceReading

from .models import DoctorPatientAssignment, Report
from .utils import compute_trends


def _make_doctor(username):
    user = User.objects.create_user(
        username=username, password="Pass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
    )
    return user, DoctorProfile.objects.create(user=user, license_number=f"LIC-{username}")


def _make_patient(username):
    user = User.objects.create_user(
        username=username, password="Pass123!", role=User.Role.PATIENT, is_approved=True, is_active=True
    )
    return user, PatientProfile.objects.create(user=user)


class AssignPatientTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_apana")
        self.patient_user, self.patient_profile = _make_patient("ahsoka_tano")

    def test_doctor_can_assign_an_approved_patient_by_username(self):
        self.client.force_login(self.doctor_user)
        response = self.client.post(reverse("doctors:assign_patient"), {"patient_username": "ahsoka_tano"})
        self.assertRedirects(response, reverse("doctors:patient_list"))
        self.assertTrue(
            DoctorPatientAssignment.objects.filter(doctor=self.doctor_profile, patient=self.patient_profile).exists()
        )

    def test_assigning_the_same_patient_twice_does_not_error(self):
        self.client.force_login(self.doctor_user)
        self.client.post(reverse("doctors:assign_patient"), {"patient_username": "ahsoka_tano"})
        response = self.client.post(reverse("doctors:assign_patient"), {"patient_username": "ahsoka_tano"})
        self.assertRedirects(response, reverse("doctors:patient_list"))
        self.assertEqual(
            DoctorPatientAssignment.objects.filter(doctor=self.doctor_profile, patient=self.patient_profile).count(),
            1,
        )

    def test_cannot_assign_a_nonexistent_username(self):
        self.client.force_login(self.doctor_user)
        response = self.client.post(reverse("doctors:assign_patient"), {"patient_username": "does_not_exist"})
        self.assertEqual(response.status_code, 200)  # re-renders form with error
        self.assertContains(response, "No approved patient")

    def test_cannot_assign_an_unapproved_patient(self):
        unapproved_user = User.objects.create_user(username="pending_p", password="Pass123!", role=User.Role.PATIENT)
        PatientProfile.objects.create(user=unapproved_user)

        self.client.force_login(self.doctor_user)
        response = self.client.post(reverse("doctors:assign_patient"), {"patient_username": "pending_p"})
        self.assertContains(response, "been approved yet")

    def test_non_doctor_cannot_access_assignment(self):
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("doctors:assign_patient"))
        self.assertEqual(response.status_code, 403)


class PatientDetailAccessTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_kalonia")
        self.other_doctor_user, self.other_doctor_profile = _make_doctor("dr_vokara_che")
        self.patient_user, self.patient_profile = _make_patient("anakin_skywalker")
        DoctorPatientAssignment.objects.create(doctor=self.doctor_profile, patient=self.patient_profile)

    def test_assigned_doctor_can_view_patient_detail(self):
        self.client.force_login(self.doctor_user)
        response = self.client.get(reverse("doctors:patient_detail", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 200)

    def test_unassigned_doctor_cannot_view_patient_detail(self):
        self.client.force_login(self.other_doctor_user)
        response = self.client.get(reverse("doctors:patient_detail", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 404)

    def test_superuser_without_doctor_profile_is_forbidden(self):
        # Deliberate design choice: a superuser has no DoctorProfile, so
        # there's nothing to attach a report/assignment to - this app
        # doesn't grant superusers a bypass the way some others do.
        admin = User.objects.create_superuser(username="chancellor2", password="Pass123!", email="c@coruscant.gov")
        self.client.force_login(admin)
        response = self.client.get(reverse("doctors:patient_detail", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 403)

    def test_patient_cannot_view_the_doctor_view_of_their_own_record(self):
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("doctors:patient_detail", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 403)


class ReportWritingTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_bant")
        self.other_doctor_user, self.other_doctor_profile = _make_doctor("dr_che2")
        self.patient_user, self.patient_profile = _make_patient("obi_wan")
        DoctorPatientAssignment.objects.create(doctor=self.doctor_profile, patient=self.patient_profile)

    def test_assigned_doctor_can_write_a_report(self):
        self.client.force_login(self.doctor_user)
        response = self.client.post(
            reverse("doctors:create_report", args=[self.patient_profile.pk]),
            {"content": "Rest and hydration recommended."},
        )
        self.assertRedirects(response, reverse("doctors:patient_detail", args=[self.patient_profile.pk]))

        report = Report.objects.get(patient=self.patient_profile)
        self.assertEqual(report.doctor, self.doctor_profile)
        self.assertEqual(report.content, "Rest and hydration recommended.")

    def test_unassigned_doctor_cannot_write_a_report(self):
        self.client.force_login(self.other_doctor_user)
        response = self.client.post(
            reverse("doctors:create_report", args=[self.patient_profile.pk]),
            {"content": "Should not be allowed."},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Report.objects.filter(patient=self.patient_profile).exists())

    def test_report_appears_on_patient_dashboard(self):
        Report.objects.create(doctor=self.doctor_profile, patient=self.patient_profile, content="Take it easy.")
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("accounts:dashboard_patient"))
        self.assertContains(response, "Take it easy.")


class ComputeTrendsTests(TestCase):
    """compute_trends is pure logic, so it's tested directly rather than through a view."""

    def setUp(self):
        _, self.patient_profile = _make_patient("padme")

    def _reading(self, reading_type, value, when):
        return DeviceReading.objects.create(
            patient=self.patient_profile, reading_type=reading_type, value=value, recorded_at=when
        )

    def test_numeric_increase_is_trend_up(self):
        now = timezone.now()
        self._reading(DeviceReading.ReadingType.HEART_RATE, "70", now - timezone.timedelta(hours=1))
        self._reading(DeviceReading.ReadingType.HEART_RATE, "90", now)

        readings = list(DeviceReading.objects.filter(patient=self.patient_profile))
        trends = compute_trends(readings)
        self.assertEqual(trends[DeviceReading.ReadingType.HEART_RATE]["trend"], "up")

    def test_numeric_decrease_is_trend_down(self):
        now = timezone.now()
        self._reading(DeviceReading.ReadingType.TEMPERATURE, "38.5", now - timezone.timedelta(hours=1))
        self._reading(DeviceReading.ReadingType.TEMPERATURE, "37.0", now)

        readings = list(DeviceReading.objects.filter(patient=self.patient_profile))
        trends = compute_trends(readings)
        self.assertEqual(trends[DeviceReading.ReadingType.TEMPERATURE]["trend"], "down")

    def test_single_reading_has_no_trend(self):
        self._reading(DeviceReading.ReadingType.GLUCOSE, "95", timezone.now())
        readings = list(DeviceReading.objects.filter(patient=self.patient_profile))
        trends = compute_trends(readings)
        self.assertIsNone(trends[DeviceReading.ReadingType.GLUCOSE]["trend"])

    def test_non_numeric_blood_pressure_has_no_trend_arrow(self):
        now = timezone.now()
        self._reading(DeviceReading.ReadingType.BLOOD_PRESSURE, "120/80", now - timezone.timedelta(hours=1))
        self._reading(DeviceReading.ReadingType.BLOOD_PRESSURE, "130/85", now)

        readings = list(DeviceReading.objects.filter(patient=self.patient_profile))
        trends = compute_trends(readings)
        self.assertIsNone(trends[DeviceReading.ReadingType.BLOOD_PRESSURE]["trend"])
