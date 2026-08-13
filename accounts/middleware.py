from django.shortcuts import redirect
from django.urls import reverse

# Paths a flagged user must still be able to reach, or they'd be locked
# out entirely: the change-password page itself (obviously), logging out
# (an escape hatch if something goes wrong), and static/media/admin so
# this middleware can never interfere with anything outside the
# patient-facing app.
_EXEMPT_URL_NAMES = ("accounts:force_password_change", "accounts:logout")
_EXEMPT_PATH_PREFIXES = ("/static/", "/media/", "/admin/")


class ForcePasswordChangeMiddleware:
    """
    Redirects a logged-in patient to the password-change form if their
    PatientProfile.must_change_password flag is set - currently only true
    right after Emergency Services intake. Enforced server-side on every
    request rather than relying on the person to click a "please change
    your password" link, since the whole point is a password that may
    have been seen by someone other than the account's owner.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt_paths = None

    def _get_exempt_paths(self):
        if self._exempt_paths is None:
            self._exempt_paths = {reverse(name) for name in _EXEMPT_URL_NAMES}
        return self._exempt_paths

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated:
            patient_profile = getattr(user, "patient_profile", None)
            if patient_profile is not None and patient_profile.must_change_password:
                if request.path not in self._get_exempt_paths() and not request.path.startswith(
                    _EXEMPT_PATH_PREFIXES
                ):
                    return redirect("accounts:force_password_change")

        return self.get_response(request)
