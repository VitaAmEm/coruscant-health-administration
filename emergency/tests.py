from django.test import TestCase
from django.urls import reverse

from accounts.models import PatientProfile, User

from .models import EmergencyIntakeLog


def _make_emergency_staff(username):
    return User.objects.create_user(
        username=username, password="Pass123!", role=User.Role.EMERGENCY, is_approved=True, is_active=True
    )


class EmergencyIntakeTests(TestCase):
    def setUp(self):
        self.staff = _make_emergency_staff("emt_bly")

    def test_intake_creates_an_immediately_active_patient(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("emergency:intake"),
            {"first_name": "Rex", "last_name": "Clone", "date_of_birth": "", "device_id": ""},
        )
        self.assertRedirects(response, reverse("emergency:intake_confirmation"))

        profile = PatientProfile.objects.get(user__first_name="Rex", user__last_name="Clone")
        # The whole point of this flow: no approval wait, unlike normal
        # patient self-registration.
        self.assertTrue(profile.user.is_approved)
        self.assertTrue(profile.user.is_active)
        self.assertTrue(profile.registered_via_emergency)

    def test_generated_username_is_based_on_name(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "Ahsoka", "last_name": "Tano", "date_of_birth": "", "device_id": ""},
        )
        profile = PatientProfile.objects.get(user__first_name="Ahsoka")
        self.assertTrue(profile.user.username.startswith("ahsoka-tano-"))

    def test_duplicate_names_get_different_usernames(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "John", "last_name": "Doe", "date_of_birth": "", "device_id": ""},
        )
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "John", "last_name": "Doe", "date_of_birth": "", "device_id": ""},
        )
        usernames = list(
            PatientProfile.objects.filter(user__first_name="John", user__last_name="Doe").values_list(
                "user__username", flat=True
            )
        )
        self.assertEqual(len(usernames), 2)
        self.assertNotEqual(usernames[0], usernames[1])

    def test_generated_credentials_can_actually_log_in(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "Cad", "last_name": "Bane", "date_of_birth": "", "device_id": ""},
        )
        # Read the real password out of the session, the same place the
        # confirmation view reads it from - not out-of-band knowledge.
        credentials = self.client.session["emergency_new_patient"]

        fresh_client = self.client_class()
        response = fresh_client.post(
            reverse("accounts:login"),
            {"username": credentials["username"], "password": credentials["password"]},
            follow=True,
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_non_emergency_role_cannot_access_intake(self):
        doctor = User.objects.create_user(
            username="dr_not_emergency", password="Pass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
        )
        self.client.force_login(doctor)
        response = self.client.get(reverse("emergency:intake"))
        self.assertEqual(response.status_code, 403)

    def test_missing_last_name_is_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("emergency:intake"),
            {"first_name": "OnlyFirst", "last_name": "", "date_of_birth": "", "device_id": ""},
        )
        self.assertEqual(response.status_code, 200)  # re-renders form with error
        self.assertFalse(PatientProfile.objects.filter(user__first_name="OnlyFirst").exists())

    def test_intake_sets_must_change_password_flag(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "Wolffe", "last_name": "Clone", "date_of_birth": "", "device_id": ""},
        )
        profile = PatientProfile.objects.get(user__first_name="Wolffe")
        self.assertTrue(profile.must_change_password)

    def test_intake_creates_an_audit_log_entry(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "Gregor", "last_name": "Clone", "date_of_birth": "", "device_id": ""},
        )
        profile = PatientProfile.objects.get(user__first_name="Gregor")
        entry = EmergencyIntakeLog.objects.get(patient_username=profile.user.username)
        self.assertEqual(entry.performed_by, self.staff)


class IntakeLogAccessTests(TestCase):
    def setUp(self):
        self.staff = _make_emergency_staff("emt_appo")
        EmergencyIntakeLog.objects.create(patient_username="some-patient-1234", performed_by=self.staff)

    def test_emergency_staff_can_view_intake_log(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("emergency:intake_log"))
        self.assertContains(response, "some-patient-1234")

    def test_non_emergency_role_cannot_view_intake_log(self):
        doctor = User.objects.create_user(
            username="dr_no_log_access", password="Pass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
        )
        self.client.force_login(doctor)
        response = self.client.get(reverse("emergency:intake_log"))
        self.assertEqual(response.status_code, 403)


class ConfirmationOneTimeRevealTests(TestCase):
    def setUp(self):
        self.staff = _make_emergency_staff("emt_fox")

    def test_confirmation_page_shows_credentials_once(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "Echo", "last_name": "Clone", "date_of_birth": "", "device_id": ""},
        )

        first_visit = self.client.get(reverse("emergency:intake_confirmation"))
        self.assertContains(first_visit, "Echo Clone")

    def test_revisiting_confirmation_page_shows_nothing_the_second_time(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("emergency:intake"),
            {"first_name": "Fives", "last_name": "Clone", "date_of_birth": "", "device_id": ""},
        )
        self.client.get(reverse("emergency:intake_confirmation"))  # first visit consumes it

        second_visit = self.client.get(reverse("emergency:intake_confirmation"), follow=True)
        self.assertRedirects(second_visit, reverse("emergency:intake"))
        self.assertNotContains(second_visit, "Fives Clone")
