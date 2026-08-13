from django.core.mail import send_mail


def send_completion_email(order):
    """
    Best-effort notification to the ordering doctor once a department
    finishes an order. Same fail-silently philosophy as
    accounts.views._notify_by_email: a broken mail server shouldn't be
    able to block a department from marking real work done.
    """
    email = order.doctor.user.email
    if not email:
        return
    try:
        send_mail(
            subject=f"{order.get_order_type_display()} completed for {order.patient.user.username}",
            message=f"Result: {order.result_text}",
            from_email=None,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception:
        pass
