from django.core.cache import cache
from menu.models import Restaurant
from orders.models import RestaurantTable, Order, DiningSession


def invalidate_restaurant_cache():
    """Call whenever restaurant details or tables are added, modified, or deleted."""
    cache.delete('app_restaurant_info')
    cache.delete('app_all_active_tables')


def restaurant_context(request):
    """
    Makes restaurant info, cart count, active table, active order & session accessible in all templates.
    Optimized with in-memory caching to eliminate redundant DB queries on every request.
    """
    restaurant = cache.get_or_set('app_restaurant_info', lambda: Restaurant.objects.first(), 3600)
    cart = request.session.get('cart', {})
    cart_count = sum(cart.values()) if isinstance(cart, dict) else 0

    table_id = request.session.get('table_id')
    current_table = None
    table_is_locked_by_other = False
    table_is_locked_for_me = False

    if table_id:
        try:
            current_table = RestaurantTable.objects.filter(table_number__iexact=str(table_id).strip()).first()
            if current_table and current_table.is_locked:
                if hasattr(request.user, 'customer_profile'):
                    if current_table.current_customer != request.user.customer_profile:
                        table_is_locked_by_other = True
                    else:
                        table_is_locked_for_me = True
                else:
                    table_is_locked_by_other = True
        except Exception:
            current_table = None

    # Fetch active customer order and dining session
    active_order = None
    active_session = None
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        customer = request.user.customer_profile
        active_session = DiningSession.objects.filter(
            customer=customer,
            is_active=True
        ).first()

        if active_session:
            active_order = active_session.orders.filter(
                status__in=[Order.STATUS_PENDING, Order.STATUS_PREPARING, Order.STATUS_READY, Order.STATUS_SERVED]
            ).order_by('-order_date').first()
        else:
            active_order = Order.objects.filter(
                customer=customer,
                session__isnull=True,
                status__in=[Order.STATUS_PENDING, Order.STATUS_PREPARING, Order.STATUS_READY, Order.STATUS_SERVED]
            ).order_by('-order_date').first()

    # Check staff role for navigation
    staff_profile = getattr(request.user, 'staff_profile', None) if request.user.is_authenticated else None

    # All active tables for easy one-tap selection modal (cached for 5 minutes)
    all_active_tables = cache.get_or_set(
        'app_all_active_tables',
        lambda: list(RestaurantTable.objects.filter(is_active=True).order_by('table_number')),
        300
    )

    from django.conf import settings
    firebase_config = getattr(settings, 'FIREBASE_CONFIG', {})

    return {
        'restaurant': restaurant,
        'cart_count': cart_count,
        'current_table': current_table,
        'current_table_number': table_id,
        'table_is_locked_by_other': table_is_locked_by_other,
        'table_is_locked_for_me': table_is_locked_for_me,
        'active_order': active_order,
        'active_session': active_session,
        'staff_profile': staff_profile,
        'all_active_tables': all_active_tables,
        'firebase_config': firebase_config,
    }
