from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, View

from accounts.models import User
from orders.forms import CompleteOrderForm
from orders.models import ServiceOrder
from orders.utils import send_completion_email


class DepartmentRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Same no-superuser-bypass design as doctors.views.DoctorRequiredMixin,
    for the same reason: a superuser has no DepartmentProfile to act as."""

    def test_func(self):
        user = self.request.user
        return user.role == User.Role.DEPARTMENT and hasattr(user, "department_profile")


class OrderQueueView(DepartmentRequiredMixin, ListView):
    template_name = "departments/order_queue.html"
    context_object_name = "orders"

    def get_queryset(self):
        department_profile = self.request.user.department_profile
        relevant_types = ServiceOrder.order_types_for_department_type(department_profile.department_type)
        return (
            ServiceOrder.objects.filter(
                Q(status=ServiceOrder.Status.PENDING, order_type__in=relevant_types)
                | Q(claimed_by=department_profile)
            )
            .select_related("patient__user", "doctor__user")
            .distinct()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["complete_form"] = CompleteOrderForm()
        return context


class ClaimOrderView(DepartmentRequiredMixin, View):
    def post(self, request, pk):
        department_profile = request.user.department_profile
        relevant_types = ServiceOrder.order_types_for_department_type(department_profile.department_type)

        # A plain get-then-save here would be vulnerable to a real race:
        # two department staff clicking "claim" at nearly the same moment
        # could both pass a SELECT-based check before either write lands.
        # QuerySet.update() instead issues a single UPDATE ... WHERE
        # statement, so the "is it still PENDING and unclaimed" check and
        # the write happen as one atomic database operation - only one
        # concurrent request can ever match and update the row.
        updated_count = ServiceOrder.objects.filter(
            pk=pk,
            order_type__in=relevant_types,
            status=ServiceOrder.Status.PENDING,
            claimed_by__isnull=True,
        ).update(claimed_by=department_profile, status=ServiceOrder.Status.IN_PROGRESS)

        if updated_count == 0:
            messages.error(request, "That order is no longer available to claim.")
        else:
            messages.success(request, "Order claimed.")
        return redirect(reverse("departments:order_queue"))


class CompleteOrderView(DepartmentRequiredMixin, View):
    def post(self, request, pk):
        department_profile = request.user.department_profile
        order = get_object_or_404(
            ServiceOrder,
            pk=pk,
            claimed_by=department_profile,
            status=ServiceOrder.Status.IN_PROGRESS,
        )
        form = CompleteOrderForm(request.POST, instance=order)
        if form.is_valid():
            completed_order = form.save(commit=False)
            completed_order.status = ServiceOrder.Status.COMPLETED
            completed_order.completed_at = timezone.now()
            completed_order.save()
            send_completion_email(completed_order)
            messages.success(request, "Order marked complete.")
        else:
            messages.error(request, "Please enter a result before completing the order.")
        return redirect(reverse("departments:order_queue"))
