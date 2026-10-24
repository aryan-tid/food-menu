from django import template
from django.utils import timezone
from django.db.models import Sum
from accounts.models import Customer, StaffProfile
from menu.models import MenuItem
from orders.models import RestaurantTable, Order, Payment

register = template.Library()


@register.simple_tag
def get_admin_dashboard_kpis():
    """Returns real-time analytics KPIs for the customized Django Admin console."""
    today = timezone.localdate()
    
    total_revenue = Payment.objects.filter(status=Payment.STATUS_PAID).aggregate(Sum('amount'))['amount__sum'] or 0
    today_revenue = Payment.objects.filter(status=Payment.STATUS_PAID, payment_date__date=today).aggregate(Sum('amount'))['amount__sum'] or 0
    active_orders = Order.objects.exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).count()
    locked_tables = RestaurantTable.objects.filter(is_locked=True).count()
    total_tables = RestaurantTable.objects.filter(is_active=True).count()
    menu_items = MenuItem.objects.count()
    customers = Customer.objects.count()
    staff = StaffProfile.objects.count()

    return {
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        'active_orders': active_orders,
        'locked_tables': locked_tables,
        'total_tables': total_tables,
        'menu_items': menu_items,
        'customers': customers,
        'staff': staff,
    }
