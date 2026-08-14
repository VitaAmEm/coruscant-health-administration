def patient_unread_report_count(request):
    if not request.user.is_authenticated or request.user.role != "PATIENT":
        return {"unread_report_count": 0}

    from doctors.models import Report

    patient_profile = getattr(request.user, "patient_profile", None)
    if patient_profile is None:
        return {"unread_report_count": 0}

    return {
        "unread_report_count": Report.objects.filter(patient=patient_profile)
        .exclude(read_statuses__patient=patient_profile)
        .count()
    }