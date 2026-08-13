## Task

The Coruscant Health Administration needs its Medical Management System
rebuilt from scratch, serving five different stakeholders - Patient,
Doctor, Department, Administrator, and Emergency Services - each with
different permissions and workflows in one system.

The real challenge isn't any single screen; it's the structure
underneath: who's allowed to see what, how new accounts get vetted
before touching patient data, how a doctor's order actually reaches the
right department, and how uploaded documents stay genuinely protected at
rest - not just labeled as protected.

## Description

**Roles and approval**: a single custom `User` model covers all five
stakeholders via a `role` field. Patients and Doctors self-register and
require Administrator approval before their account is active; an
`ApprovalLog` records who approved or rejected each one, and why.
Department and Emergency Services accounts are created directly by an
Administrator. Emergency-registered patients are a deliberate exception:
active immediately (an emergency can't wait on a review queue), with a
forced password change on first login since the generated password may
have been seen by someone other than the patient.

**Patients** upload device readings and view them alongside prescriptions
their doctor has written. **Doctors** add patients to their care, review
readings with a simple condition-trend indicator, write prescriptions,
and place service orders (CT scan, lab test, etc.). **Departments** see
only the orders that route to their type, claim and complete them -
claiming uses an atomic database update so two staff can't claim the
same order in a race. **Documents** uploaded by patients or doctors are
encrypted with Fernet (AES-128 + HMAC) before ever touching disk; only
the patient themselves or a doctor assigned to them can retrieve one.

Every workflow above is covered by automated tests (95 total), including
the ones that matter most to get right: that a rejected user's audit
entry survives their own account deletion, that an unassigned doctor
gets a 404 (not a 403) trying to view a patient, and that an uploaded
document's stored bytes genuinely don't contain the original plaintext.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste that output into .env as DOCUMENT_ENCRYPTION_KEY

python manage.py migrate
python manage.py createsuperuser   # creates your first Administrator
```

## Usage

```bash
python manage.py runserver
```

Open `http://localhost:8000`. Register a Patient or Doctor, then log in
as the Administrator to approve them. Department and Emergency Services
accounts are created via `/admin/`.

For production, set `AWS_STORAGE_BUCKET_NAME` and the AWS credential variables
to use a private S3-compatible bucket for encrypted documents. The local
filesystem is intended only for development. Configure the SMTP variables in
`.env` if approval and order-completion emails should be delivered.

```bash
python manage.py test
```
