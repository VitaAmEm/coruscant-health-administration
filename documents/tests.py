import shutil
import tempfile

from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import DoctorProfile, PatientProfile, User
from doctors.models import DoctorPatientAssignment

from .crypto import decrypt_bytes, encrypt_bytes
from .forms import DocumentUploadForm
from .models import Document

TEST_KEY = Fernet.generate_key().decode()


def _make_patient(username):
    user = User.objects.create_user(
        username=username, password="Pass123!", role=User.Role.PATIENT, is_approved=True, is_active=True
    )
    return user, PatientProfile.objects.create(user=user)


def _make_doctor(username):
    user = User.objects.create_user(
        username=username, password="Pass123!", role=User.Role.DOCTOR, is_approved=True, is_active=True
    )
    return user, DoctorProfile.objects.create(user=user, license_number=f"LIC-{username}")


@override_settings(DOCUMENT_ENCRYPTION_KEY=TEST_KEY)
class CryptoRoundTripTests(TestCase):
    """The encryption helper itself, tested in isolation from any view/model."""

    def test_encrypt_then_decrypt_returns_original_bytes(self):
        original = b"This is a confidential medical record."
        encrypted = encrypt_bytes(original)
        self.assertNotEqual(encrypted, original)
        self.assertEqual(decrypt_bytes(encrypted), original)

    def test_encrypted_output_does_not_contain_the_plaintext(self):
        original = b"a very specific and identifiable string of patient data"
        encrypted = encrypt_bytes(original)
        self.assertNotIn(original, encrypted)


class MissingEncryptionKeyTests(TestCase):
    @override_settings(DOCUMENT_ENCRYPTION_KEY="")
    def test_missing_key_raises_a_clear_error_rather_than_failing_silently(self):
        with self.assertRaises(ImproperlyConfigured):
            encrypt_bytes(b"test")


class DocumentUploadValidationTests(TestCase):
    @override_settings(MAX_DOCUMENT_UPLOAD_BYTES=4)
    def test_document_upload_rejects_files_over_the_configured_limit(self):
        form = DocumentUploadForm(
            data={"title": "Large file"},
            files={"file": SimpleUploadedFile("large.txt", b"12345")},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("smaller", form.errors["file"][0])


@override_settings(DOCUMENT_ENCRYPTION_KEY=TEST_KEY)
class DocumentUploadAndStorageTests(TestCase):
    """
    The single most important test class here: it proves files are
    genuinely encrypted on disk, not just labeled as encrypted while
    actually stored as plaintext.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.patient_user, self.patient_profile = _make_patient("luke_docs")

    def tearDown(self):
        self.override.disable()

    def test_uploaded_file_content_is_not_stored_as_plaintext_on_disk(self):
        secret_content = b"Patient has a confirmed diagnosis of Bantha flu."
        upload = SimpleUploadedFile("chart.txt", secret_content, content_type="text/plain")

        self.client.force_login(self.patient_user)
        self.client.post(
            reverse("documents:upload_document", args=[self.patient_profile.pk]),
            {"title": "Chart", "file": upload},
        )

        document = Document.objects.get(patient=self.patient_profile)
        with document.encrypted_file.open("rb") as f:
            raw_bytes_on_disk = f.read()

        # This is the check that actually matters: read the literal bytes
        # Django wrote to storage and confirm the original plaintext is
        # nowhere in them.
        self.assertNotIn(secret_content, raw_bytes_on_disk)
        self.assertNotEqual(raw_bytes_on_disk, secret_content)

    def test_downloading_returns_the_exact_original_bytes(self):
        secret_content = b"Byte-for-byte round trip check \x00\x01\xff."
        upload = SimpleUploadedFile("data.bin", secret_content, content_type="application/octet-stream")

        self.client.force_login(self.patient_user)
        self.client.post(
            reverse("documents:upload_document", args=[self.patient_profile.pk]),
            {"title": "Binary", "file": upload},
        )
        document = Document.objects.get(patient=self.patient_profile)

        response = self.client.get(reverse("documents:download_document", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, secret_content)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="data.bin"')

    def test_uploaded_by_is_recorded(self):
        upload = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        self.client.force_login(self.patient_user)
        self.client.post(
            reverse("documents:upload_document", args=[self.patient_profile.pk]),
            {"title": "Note", "file": upload},
        )
        document = Document.objects.get(patient=self.patient_profile)
        self.assertEqual(document.uploaded_by, self.patient_user)


@override_settings(DOCUMENT_ENCRYPTION_KEY=TEST_KEY)
class DocumentAccessBoundaryTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        self.patient_user, self.patient_profile = _make_patient("leia_docs")
        self.other_patient_user, self.other_patient_profile = _make_patient("han_docs")
        self.assigned_doctor_user, self.assigned_doctor_profile = _make_doctor("dr_assigned_docs")
        self.unassigned_doctor_user, self.unassigned_doctor_profile = _make_doctor("dr_unassigned_docs")
        DoctorPatientAssignment.objects.create(doctor=self.assigned_doctor_profile, patient=self.patient_profile)

        self.document = Document.objects.create(
            patient=self.patient_profile,
            uploaded_by=self.patient_user,
            title="Existing doc",
            original_filename="existing.txt",
            content_type="text/plain",
        )
        # Give it real (encrypted) content so download tests have something to read.
        from django.core.files.base import ContentFile

        self.document.encrypted_file.save("existing.txt.enc", ContentFile(encrypt_bytes(b"existing content")))

    def tearDown(self):
        self.override.disable()

    def test_patient_can_view_their_own_document_list(self):
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("documents:document_list", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existing doc")

    def test_other_patient_cannot_view_someone_elses_documents(self):
        self.client.force_login(self.other_patient_user)
        response = self.client.get(reverse("documents:document_list", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 404)

    def test_assigned_doctor_can_view_the_document_list(self):
        self.client.force_login(self.assigned_doctor_user)
        response = self.client.get(reverse("documents:document_list", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 200)

    def test_unassigned_doctor_cannot_view_the_document_list(self):
        self.client.force_login(self.unassigned_doctor_user)
        response = self.client.get(reverse("documents:document_list", args=[self.patient_profile.pk]))
        self.assertEqual(response.status_code, 404)

    def test_unassigned_doctor_cannot_download_the_document_directly(self):
        self.client.force_login(self.unassigned_doctor_user)
        response = self.client.get(reverse("documents:download_document", args=[self.document.pk]))
        self.assertEqual(response.status_code, 404)

    def test_other_patient_cannot_download_via_direct_document_id(self):
        # Guards against a specific attack shape: guessing/incrementing a
        # document pk directly, bypassing the list view entirely.
        self.client.force_login(self.other_patient_user)
        response = self.client.get(reverse("documents:download_document", args=[self.document.pk]))
        self.assertEqual(response.status_code, 404)

    def test_assigned_doctor_can_download(self):
        self.client.force_login(self.assigned_doctor_user)
        response = self.client.get(reverse("documents:download_document", args=[self.document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"existing content")
