from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import ApprovalLog, DepartmentProfile, DoctorProfile, PatientProfile, User
from doctors.models import Report, ReportReadStatus


class PatientRegistrationTests(TestCase):
    def test_registration_creates_inactive_unapproved_patient_with_profile(self):
        response = self.client.post(
            reverse("accounts:register_patient"),
            {
                "username": "leia_organa",
                "email": "leia@alderaan.gov",
                "first_name": "Leia",
                "last_name": "Organa",
                "password1": "SenatePassword123!",
                "password2": "SenatePassword123!",
                "date_of_birth": "1990-01-01",
                "device_id": "",
            },
        )
        self.assertRedirects(response, reverse("accounts:login"))

        user = User.objects.get(username="leia_organa")
        self.assertEqual(user.role, User.Role.PATIENT)
        self.assertFalse(user.is_approved)
        self.assertFalse(user.is_active)
        self.assertTrue(PatientProfile.objects.filter(user=user).exists())

    def test_unapproved_patient_cannot_log_in(self):
        self._register_patient("han_solo")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "han_solo", "password": "FalconPassword123!"},
        )
        self.assertContains(response, "Invalid username or password.")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_approved_patient_can_log_in(self):
        self._register_patient("chewbacca")
        user = User.objects.get(username="chewbacca")
        user.is_approved = True
        user.is_active = True
        user.save(update_fields=["is_approved", "is_active"])

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "chewbacca", "password": "FalconPassword123!"},
            follow=True,
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def _register_patient(self, username):
        self.client.post(
            reverse("accounts:register_patient"),
            {
                "username": username,
                "email": f"{username}@rebels.gov",
                "first_name": "Test",
                "last_name": "Patient",
                "password1": "FalconPassword123!",
                "password2": "FalconPassword123!",
                "date_of_birth": "1980-01-01",
                "device_id": "",
            },
        )


class DoctorRegistrationTests(TestCase):
    def test_registration_creates_inactive_unapproved_doctor_with_profile(self):
        response = self.client.post(
            reverse("accounts:register_doctor"),
            {
                "username": "dr_onuta",
                "email": "onuta@cha.gov",
                "first_name": "Harribore",
                "last_name": "Onuta",
                "password1": "MedcenterPass123!",
                "password2": "MedcenterPass123!",
                "specialty": "Infectious Disease",
                "license_number": "CHA-0001",
            },
        )
        self.assertRedirects(response, reverse("accounts:login"))

        user = User.objects.get(username="dr_onuta")
        self.assertEqual(user.role, User.Role.DOCTOR)
        self.assertFalse(user.is_approved)
        self.assertFalse(user.is_active)
        profile = DoctorProfile.objects.get(user=user)
        self.assertEqual(profile.license_number, "CHA-0001")


class PatientReportReadTrackingTests(TestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            username="report_patient", password="PatientPass123!", role=User.Role.PATIENT,
            is_approved=True, is_active=True,
        )
        self.patient_profile = PatientProfile.objects.create(user=self.patient_user)
        self.other_patient_user = User.objects.create_user(
            username="other_report_patient", password="PatientPass123!", role=User.Role.PATIENT,
            is_approved=True, is_active=True,
        )
        self.other_patient_profile = PatientProfile.objects.create(user=self.other_patient_user)
        doctor_user = User.objects.create_user(
            username="report_doctor", password="DoctorPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True,
        )
        doctor_profile = DoctorProfile.objects.create(user=doctor_user, license_number="READ-001")
        self.report = Report.objects.create(
            doctor=doctor_profile, patient=self.patient_profile, content="Please rest and hydrate.",
        )

    def test_patient_dashboard_shows_unread_report_count(self):
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("accounts:dashboard_patient"))

        self.assertContains(response, "1 new")

    def test_opening_report_marks_it_read_and_removes_unread_count(self):
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("accounts:patient_report_detail", args=[self.report.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ReportReadStatus.objects.filter(report=self.report, patient=self.patient_profile).exists())
        dashboard = self.client.get(reverse("accounts:dashboard_patient"))
        self.assertNotContains(dashboard, "1 new")

    def test_other_patient_cannot_read_report_or_create_read_status(self):
        self.client.force_login(self.other_patient_user)
        response = self.client.get(reverse("accounts:patient_report_detail", args=[self.report.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ReportReadStatus.objects.exists())


class AdministratorCreatedAccountTests(TestCase):
    def test_department_account_is_auto_approved_and_active(self):
        user = User.objects.create_user(
            username="radiology_dept", password="DeptPass123!", role=User.Role.DEPARTMENT
        )
        DepartmentProfile.objects.create(user=user, department_type=DepartmentProfile.DepartmentType.RADIOLOGY)

        self.assertTrue(user.is_approved)
        self.assertTrue(user.is_active)

    def test_emergency_services_account_is_auto_approved_and_active(self):
        user = User.objects.create_user(
            username="emergency_intake", password="EmergencyPass123!", role=User.Role.EMERGENCY
        )
        self.assertTrue(user.is_approved)
        self.assertTrue(user.is_active)

    def test_superuser_is_always_active_regardless_of_role(self):
        admin = User.objects.create_superuser(
            username="chancellor", password="ChancellorPass123!", email="chancellor@coruscant.gov"
        )
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_approved)
        self.assertEqual(admin.role, User.Role.ADMINISTRATOR)


class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin_user", password="AdminPass123!", email="admin@cha.gov"
        )
        self.pending_patient = User.objects.create_user(
            username="pending_patient", password="PatientPass123!", role=User.Role.PATIENT
        )
        PatientProfile.objects.create(user=self.pending_patient)

    def test_pending_approvals_list_requires_administrator(self):
        # Anonymous users are redirected to log in.
        response = self.client.get(reverse("accounts:pending_approvals"))
        self.assertEqual(response.status_code, 302)

        # A non-administrator, non-superuser role is forbidden even if logged in.
        doctor = User.objects.create_user(
            username="dr_regular", password="DoctorPass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
        )
        self.client.force_login(doctor)
        response = self.client.get(reverse("accounts:pending_approvals"))
        self.assertEqual(response.status_code, 403)

    def test_administrator_sees_pending_patient_in_queue(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:pending_approvals"))
        self.assertContains(response, "pending_patient")

    def test_approving_a_user_activates_their_account(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:approve_user", args=[self.pending_patient.pk]))

        self.pending_patient.refresh_from_db()
        self.assertTrue(self.pending_patient.is_approved)
        self.assertTrue(self.pending_patient.is_active)

    def test_rejecting_a_user_deletes_their_account(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:reject_user", args=[self.pending_patient.pk]))

        self.assertFalse(User.objects.filter(pk=self.pending_patient.pk).exists())

    def test_approving_creates_an_approval_log_entry(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("accounts:approve_user", args=[self.pending_patient.pk]),
            {"reason": "License and ID verified in person"},
        )

        entry = ApprovalLog.objects.get(target_username="pending_patient")
        self.assertEqual(entry.action, ApprovalLog.Action.APPROVED)
        self.assertEqual(entry.performed_by, self.admin)
        self.assertEqual(entry.target_role, User.Role.PATIENT)
        self.assertEqual(entry.reason, "License and ID verified in person")

    def test_approving_sends_a_notification_email(self):
        self.pending_patient.email = "pending_patient@rebels.gov"
        self.pending_patient.save(update_fields=["email"])

        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:approve_user", args=[self.pending_patient.pk]))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["pending_patient@rebels.gov"])
        self.assertIn("approved", mail.outbox[0].subject.lower())

    def test_approving_a_user_with_no_email_does_not_crash(self):
        self.pending_patient.email = ""
        self.pending_patient.save(update_fields=["email"])

        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:approve_user", args=[self.pending_patient.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_rejecting_creates_a_log_entry_that_survives_user_deletion(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("accounts:reject_user", args=[self.pending_patient.pk]),
            {"reason": "Could not verify identity"},
        )

        # The User row is gone, but the audit trail still knows who it was.
        self.assertFalse(User.objects.filter(username="pending_patient").exists())
        entry = ApprovalLog.objects.get(target_username="pending_patient")
        self.assertEqual(entry.action, ApprovalLog.Action.REJECTED)
        self.assertEqual(entry.reason, "Could not verify identity")
        self.assertEqual(entry.performed_by, self.admin)

    def test_rejecting_sends_a_notification_email_before_deleting_the_user(self):
        self.pending_patient.email = "pending_patient@rebels.gov"
        self.pending_patient.save(update_fields=["email"])

        self.client.force_login(self.admin)
        self.client.post(
            reverse("accounts:reject_user", args=[self.pending_patient.pk]),
            {"reason": "Could not verify identity"},
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["pending_patient@rebels.gov"])
        self.assertIn("Could not verify identity", mail.outbox[0].body)

    def test_approval_log_requires_administrator(self):
        response = self.client.get(reverse("accounts:approval_log"))
        self.assertEqual(response.status_code, 302)  # anonymous -> redirected to login

        doctor = User.objects.create_user(
            username="dr_no_access", password="Pass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
        )
        self.client.force_login(doctor)
        response = self.client.get(reverse("accounts:approval_log"))
        self.assertEqual(response.status_code, 403)

    def test_approval_log_visible_to_administrator(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:approve_user", args=[self.pending_patient.pk]))

        response = self.client.get(reverse("accounts:approval_log"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pending_patient")


class ForcePasswordChangeMiddlewareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="temp_password_patient", password="TempPass123!", role=User.Role.PATIENT,
            is_approved=True, is_active=True,
        )
        self.profile = PatientProfile.objects.create(user=self.user, must_change_password=True)

    def test_flagged_patient_is_redirected_away_from_dashboard(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:dashboard_patient"))
        self.assertRedirects(response, reverse("accounts:force_password_change"))

    def test_unflagged_patient_is_not_redirected(self):
        self.profile.must_change_password = False
        self.profile.save(update_fields=["must_change_password"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:dashboard_patient"))
        self.assertEqual(response.status_code, 200)

    def test_force_password_change_page_itself_is_reachable(self):
        # If this redirected too, a flagged patient could never actually
        # reach the page that clears the flag - an infinite loop.
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:force_password_change"))
        self.assertEqual(response.status_code, 200)

    def test_logout_remains_reachable_even_while_flagged(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertNotEqual(response.status_code, 403)
        self.assertRedirects(response, reverse("accounts:login"))

    def test_changing_password_clears_the_flag_and_stops_the_redirect(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:force_password_change"),
            {
                "old_password": "TempPass123!",
                "new_password1": "BrandNewPass456!",
                "new_password2": "BrandNewPass456!",
            },
            follow=True,  # accounts:dashboard is itself a redirecting dispatcher, not a terminal page
        )
        self.assertRedirects(response, reverse("accounts:dashboard_patient"))

        self.profile.refresh_from_db()
        self.assertFalse(self.profile.must_change_password)

        # And the redirect loop is genuinely gone now, not just this one time.
        dashboard_response = self.client.get(reverse("accounts:dashboard_patient"))
        self.assertEqual(dashboard_response.status_code, 200)

    def test_wrong_old_password_does_not_clear_the_flag(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("accounts:force_password_change"),
            {
                "old_password": "WrongPassword!",
                "new_password1": "BrandNewPass456!",
                "new_password2": "BrandNewPass456!",
            },
        )
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.must_change_password)

    def test_non_patient_users_are_never_affected(self):
        # The flag lives on PatientProfile - a doctor has no such profile
        # attribute at all, so getattr(..., None) must handle that
        # gracefully rather than raising.
        doctor = User.objects.create_user(
            username="dr_unaffected", password="Pass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
        )
        self.client.force_login(doctor)
        response = self.client.get(reverse("accounts:dashboard_doctor"))
        self.assertEqual(response.status_code, 200)


class DashboardRoutingTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="dashboard_patient", password="Pass123!", role=User.Role.PATIENT, is_approved=True, is_active=True
        )
        PatientProfile.objects.create(user=self.patient)

    def test_dashboard_redirects_patient_to_patient_dashboard(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertRedirects(response, reverse("accounts:dashboard_patient"))

    def test_patient_cannot_access_doctor_dashboard(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse("accounts:dashboard_doctor"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
