from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import DepartmentProfile, DoctorProfile, PatientProfile, User
from doctors.models import DoctorPatientAssignment

from .models import ServiceOrder


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


def _make_department(username, department_type):
    user = User.objects.create_user(
        username=username, password="Pass123!", role=User.Role.DEPARTMENT, is_approved=True, is_active=True
    )
    return user, DepartmentProfile.objects.create(user=user, department_type=department_type)


class CreateOrderTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_fyre")
        self.other_doctor_user, self.other_doctor_profile = _make_doctor("dr_offee")
        self.patient_user, self.patient_profile = _make_patient("padme_amidala")
        DoctorPatientAssignment.objects.create(doctor=self.doctor_profile, patient=self.patient_profile)

    def test_assigned_doctor_can_place_an_order(self):
        self.client.force_login(self.doctor_user)
        response = self.client.post(
            reverse("orders:create_order", args=[self.patient_profile.pk]),
            {"order_type": ServiceOrder.OrderType.CT_SCAN, "notes": "Rule out fracture"},
        )
        self.assertRedirects(response, reverse("doctors:patient_detail", args=[self.patient_profile.pk]))

        order = ServiceOrder.objects.get(patient=self.patient_profile)
        self.assertEqual(order.doctor, self.doctor_profile)
        self.assertEqual(order.order_type, ServiceOrder.OrderType.CT_SCAN)
        self.assertEqual(order.status, ServiceOrder.Status.PENDING)

    def test_unassigned_doctor_cannot_place_an_order(self):
        self.client.force_login(self.other_doctor_user)
        response = self.client.post(
            reverse("orders:create_order", args=[self.patient_profile.pk]),
            {"order_type": ServiceOrder.OrderType.CT_SCAN, "notes": ""},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ServiceOrder.objects.filter(patient=self.patient_profile).exists())


class OrderQueueScopingTests(TestCase):
    """A department should only ever see orders that route to its own department_type."""

    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_che")
        _, self.patient_profile = _make_patient("bail_organa")
        DoctorPatientAssignment.objects.create(doctor=self.doctor_profile, patient=self.patient_profile)

        self.radiology_user, self.radiology_profile = _make_department(
            "radiology_dept", DepartmentProfile.DepartmentType.RADIOLOGY
        )
        self.lab_user, self.lab_profile = _make_department(
            "lab_dept", DepartmentProfile.DepartmentType.LABORATORY
        )

        self.ct_order = ServiceOrder.objects.create(
            doctor=self.doctor_profile, patient=self.patient_profile, order_type=ServiceOrder.OrderType.CT_SCAN
        )
        self.lab_order = ServiceOrder.objects.create(
            doctor=self.doctor_profile, patient=self.patient_profile, order_type=ServiceOrder.OrderType.LAB_TEST
        )

    def test_radiology_sees_only_ct_pet_orders(self):
        self.client.force_login(self.radiology_user)
        response = self.client.get(reverse("departments:order_queue"))
        order_ids = {o.pk for o in response.context["orders"]}
        self.assertEqual(order_ids, {self.ct_order.pk})

    def test_laboratory_sees_only_lab_orders(self):
        self.client.force_login(self.lab_user)
        response = self.client.get(reverse("departments:order_queue"))
        order_ids = {o.pk for o in response.context["orders"]}
        self.assertEqual(order_ids, {self.lab_order.pk})

    def test_non_department_cannot_access_queue(self):
        self.client.force_login(self.doctor_user)
        response = self.client.get(reverse("departments:order_queue"))
        self.assertEqual(response.status_code, 403)

    def test_superuser_without_department_profile_is_forbidden(self):
        admin = User.objects.create_superuser(username="chancellor3", password="Pass123!", email="c@coruscant.gov")
        self.client.force_login(admin)
        response = self.client.get(reverse("departments:order_queue"))
        self.assertEqual(response.status_code, 403)


class ClaimOrderTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_apana2")
        _, self.patient_profile = _make_patient("mace_windu")
        self.radiology_user, self.radiology_profile = _make_department(
            "radiology2", DepartmentProfile.DepartmentType.RADIOLOGY
        )
        self.other_radiology_user, self.other_radiology_profile = _make_department(
            "radiology3", DepartmentProfile.DepartmentType.RADIOLOGY
        )
        self.lab_user, self.lab_profile = _make_department(
            "lab2", DepartmentProfile.DepartmentType.LABORATORY
        )
        self.order = ServiceOrder.objects.create(
            doctor=self.doctor_profile, patient=self.patient_profile, order_type=ServiceOrder.OrderType.PET_SCAN
        )

    def test_matching_department_can_claim_a_pending_order(self):
        self.client.force_login(self.radiology_user)
        self.client.post(reverse("departments:claim_order", args=[self.order.pk]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.IN_PROGRESS)
        self.assertEqual(self.order.claimed_by, self.radiology_profile)

    def test_wrong_department_type_cannot_claim(self):
        self.client.force_login(self.lab_user)
        self.client.post(reverse("departments:claim_order", args=[self.order.pk]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.PENDING)
        self.assertIsNone(self.order.claimed_by)

    def test_cannot_claim_an_already_claimed_order(self):
        # Simulates the race condition sequentially: first claim succeeds,
        # a second claim attempt (by a different department user of the
        # same type) against the now-already-claimed row must be rejected
        # by the atomic UPDATE's WHERE clause, not just by client-side UI
        # hiding the button.
        self.client.force_login(self.radiology_user)
        self.client.post(reverse("departments:claim_order", args=[self.order.pk]))

        self.client.force_login(self.other_radiology_user)
        self.client.post(reverse("departments:claim_order", args=[self.order.pk]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.claimed_by, self.radiology_profile)  # still the first claimant


class CompleteOrderTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_windu2")
        _, self.patient_profile = _make_patient("yoda")
        self.radiology_user, self.radiology_profile = _make_department(
            "radiology4", DepartmentProfile.DepartmentType.RADIOLOGY
        )
        self.order = ServiceOrder.objects.create(
            doctor=self.doctor_profile,
            patient=self.patient_profile,
            order_type=ServiceOrder.OrderType.CT_SCAN,
            claimed_by=self.radiology_profile,
            status=ServiceOrder.Status.IN_PROGRESS,
        )

    def test_claimant_can_complete_with_a_result(self):
        self.client.force_login(self.radiology_user)
        self.client.post(
            reverse("departments:complete_order", args=[self.order.pk]),
            {"result_text": "No abnormalities detected."},
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.COMPLETED)
        self.assertEqual(self.order.result_text, "No abnormalities detected.")
        self.assertIsNotNone(self.order.completed_at)

    def test_cannot_complete_without_a_result(self):
        self.client.force_login(self.radiology_user)
        self.client.post(reverse("departments:complete_order", args=[self.order.pk]), {"result_text": ""})

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.IN_PROGRESS)  # unchanged

    def test_non_claimant_cannot_complete_someone_elses_order(self):
        other_user, _ = _make_department("radiology5", DepartmentProfile.DepartmentType.RADIOLOGY)
        self.client.force_login(other_user)
        self.client.post(
            reverse("departments:complete_order", args=[self.order.pk]),
            {"result_text": "Should not be allowed."},
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.IN_PROGRESS)
        self.assertNotEqual(self.order.result_text, "Should not be allowed.")


class CancelOrderTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_cancel")
        self.other_doctor_user, self.other_doctor_profile = _make_doctor("dr_cancel_other")
        _, self.patient_profile = _make_patient("cancel_patient")
        DoctorPatientAssignment.objects.create(doctor=self.doctor_profile, patient=self.patient_profile)
        self.order = ServiceOrder.objects.create(
            doctor=self.doctor_profile, patient=self.patient_profile, order_type=ServiceOrder.OrderType.LAB_TEST
        )

    def test_doctor_can_cancel_their_own_pending_order(self):
        self.client.force_login(self.doctor_user)
        response = self.client.post(reverse("orders:cancel_order", args=[self.order.pk]))
        self.assertRedirects(response, reverse("doctors:patient_detail", args=[self.patient_profile.pk]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.CANCELLED)

    def test_cannot_cancel_an_order_already_in_progress(self):
        _, dept_profile = _make_department("cancel_dept", DepartmentProfile.DepartmentType.LABORATORY)
        self.order.status = ServiceOrder.Status.IN_PROGRESS
        self.order.claimed_by = dept_profile
        self.order.save(update_fields=["status", "claimed_by"])

        self.client.force_login(self.doctor_user)
        self.client.post(reverse("orders:cancel_order", args=[self.order.pk]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.IN_PROGRESS)  # unchanged, not cancelled

    def test_a_different_doctor_cannot_cancel_someone_elses_order(self):
        self.client.force_login(self.other_doctor_user)
        response = self.client.post(reverse("orders:cancel_order", args=[self.order.pk]))
        self.assertEqual(response.status_code, 404)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.PENDING)  # unchanged

    def test_non_doctor_cannot_cancel(self):
        patient_user, _ = _make_patient("cancel_bystander")
        self.client.force_login(patient_user)
        response = self.client.post(reverse("orders:cancel_order", args=[self.order.pk]))
        self.assertEqual(response.status_code, 403)


class CompletionNotificationTests(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor_profile = _make_doctor("dr_notify")
        self.doctor_user.email = "dr_notify@cha.gov"
        self.doctor_user.save(update_fields=["email"])
        _, self.patient_profile = _make_patient("notify_patient")
        self.dept_user, self.dept_profile = _make_department(
            "notify_dept", DepartmentProfile.DepartmentType.LABORATORY
        )
        self.order = ServiceOrder.objects.create(
            doctor=self.doctor_profile,
            patient=self.patient_profile,
            order_type=ServiceOrder.OrderType.LAB_TEST,
            claimed_by=self.dept_profile,
            status=ServiceOrder.Status.IN_PROGRESS,
        )

    def test_completing_an_order_emails_the_ordering_doctor(self):
        self.client.force_login(self.dept_user)
        self.client.post(
            reverse("departments:complete_order", args=[self.order.pk]),
            {"result_text": "Bloodwork normal."},
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["dr_notify@cha.gov"])
        self.assertIn("Bloodwork normal.", mail.outbox[0].body)

    def test_no_email_sent_if_doctor_has_no_address(self):
        self.doctor_user.email = ""
        self.doctor_user.save(update_fields=["email"])

        self.client.force_login(self.dept_user)
        self.client.post(
            reverse("departments:complete_order", args=[self.order.pk]),
            {"result_text": "Bloodwork normal."},
        )
        self.assertEqual(len(mail.outbox), 0)


class OrderDepartmentMappingTests(TestCase):
    """Pure logic test for the OrderType <-> DepartmentType mapping itself."""

    def test_ct_and_pet_scan_route_to_radiology(self):
        types = ServiceOrder.order_types_for_department_type(DepartmentProfile.DepartmentType.RADIOLOGY)
        self.assertIn(ServiceOrder.OrderType.CT_SCAN, types)
        self.assertIn(ServiceOrder.OrderType.PET_SCAN, types)
        self.assertNotIn(ServiceOrder.OrderType.LAB_TEST, types)

    def test_lab_test_routes_to_laboratory(self):
        types = ServiceOrder.order_types_for_department_type(DepartmentProfile.DepartmentType.LABORATORY)
        self.assertEqual(types, [ServiceOrder.OrderType.LAB_TEST])
