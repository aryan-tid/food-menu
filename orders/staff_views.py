import random
import string
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Q, Value, DecimalField, Avg
from django.db.models.functions import Coalesce
from accounts.models import StaffProfile, Customer
from menu.models import MenuItem, Category, Review
from .models import RestaurantTable, Order, OrderItem, Payment, WaiterAlert, DiningSession


def staff_role_required(allowed_roles):
    """Decorator ensuring user is authenticated and belongs to allowed staff roles."""
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please log in to access staff portals.")
                return redirect('accounts:staff_login')
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            profile = getattr(request.user, 'staff_profile', None)
            if not profile or (profile.role not in allowed_roles and profile.role != StaffProfile.ROLE_MANAGER):
                messages.error(request, "Permission denied for this staff section.")
                return redirect('accounts:staff_login')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


# ==============================================================================
# 1. KITCHEN MANAGER DASHBOARD
# ==============================================================================
@login_required
@staff_role_required([StaffProfile.ROLE_KITCHEN, StaffProfile.ROLE_MANAGER])
def kitchen_dashboard_view(request):
    """
    Kitchen Display System (KDS):
    - Displays incoming tickets: Pending (Queued) -> Preparing (Cooking) -> Ready.
    - Kitchen staff can move order to 'Preparing' (locks customer cancellation).
    - Kitchen staff can mark order as 'Ready'.
    - Lightweight JSON response when ?json=1 is requested to power live audio chime notifications.
    """
    pending_orders = Order.objects.filter(status=Order.STATUS_PENDING).prefetch_related('items__menu_item').order_by('order_date')
    preparing_orders = Order.objects.filter(status=Order.STATUS_PREPARING).prefetch_related('items__menu_item').order_by('order_date')
    ready_orders = Order.objects.filter(status=Order.STATUS_READY).prefetch_related('items__menu_item').order_by('order_date')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('json') == '1':
        return JsonResponse({
            'pending_count': pending_orders.count(),
            'preparing_count': preparing_orders.count(),
            'ready_count': ready_orders.count(),
            'latest_pending_id': pending_orders.last().id if pending_orders.exists() else None,
        })

    context = {
        'pending_orders': pending_orders,
        'preparing_orders': preparing_orders,
        'ready_orders': ready_orders,
    }
    return render(request, 'staff/kitchen_dashboard.html', context)


@login_required
@staff_role_required([StaffProfile.ROLE_KITCHEN, StaffProfile.ROLE_MANAGER])
@require_POST
def kitchen_update_status_view(request, order_id):
    """Moves order along kitchen pipeline: Pending -> Preparing -> Ready."""
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get('status')

    if new_status in [Order.STATUS_PREPARING, Order.STATUS_READY, Order.STATUS_SERVED, Order.STATUS_CANCELLED]:
        order.status = new_status
        order.save(update_fields=['status'])
        messages.success(request, f"Order #{order.id} status updated to {new_status}.")
    return redirect('orders:kitchen_dashboard')


@login_required
@staff_role_required([StaffProfile.ROLE_KITCHEN, StaffProfile.ROLE_MANAGER])
@require_POST
def kitchen_cancel_item_view(request, item_id):
    """Cancels a specific item from kitchen if out of ingredients."""
    order_item = get_object_or_404(OrderItem, pk=item_id)
    order = order_item.order
    order_item.is_cancelled = True
    order_item.save(update_fields=['is_cancelled'])
    order.recalculate_totals()
    messages.warning(request, f"Kitchen cancelled item: {order_item.menu_item.name} for Order #{order.id}.")
    return redirect('orders:kitchen_dashboard')


# ==============================================================================
# 2. WAITER DASHBOARD
# ==============================================================================
@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
def waiter_dashboard_view(request):
    """
    Waiter / Floor Staff Dashboard:
    - Visual table grid: Available (Free) vs. Occupied (Locked) vs. Ready to Serve.
    - View active running orders for each table.
    - Mark food as 'Served' to the table.
    - Collect cash payment at counter/table and settle the bill (uplifts table lock).
    - Manually uplift/release table locks anytime.
    """
    tables = RestaurantTable.objects.filter(is_active=True).prefetch_related('orders').order_by('table_number')

    for table in tables:
        table.active_order = Order.objects.filter(
            table=table,
            status__in=[Order.STATUS_PENDING, Order.STATUS_PREPARING, Order.STATUS_READY, Order.STATUS_SERVED]
        ).prefetch_related('items__menu_item').first()

        table.active_session = DiningSession.objects.filter(table=table, is_active=True).first()
        table.last_session = DiningSession.objects.filter(table=table).select_related('customer__user').prefetch_related('orders').order_by('-started_at').first()

        if table.is_locked and not table.active_order and table.active_session:
            table.latest_session_order = table.active_session.orders.exclude(status=Order.STATUS_CANCELLED).order_by('-order_date').first()
        else:
            table.latest_session_order = None

    unresolved_alerts = WaiterAlert.objects.filter(is_resolved=False).order_by('-created_at')[:10]

    context = {
        'tables': tables,
        'unresolved_alerts': unresolved_alerts,
    }
    return render(request, 'staff/waiter_dashboard.html', context)


@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
@require_POST
def waiter_mark_served_view(request, order_id):
    """Marks an order as Served to the table."""
    order = get_object_or_404(Order, pk=order_id)
    order.status = Order.STATUS_SERVED
    order.save(update_fields=['status'])
    messages.success(request, f"Order #{order.id} marked as Served to Table {order.table_number}.")
    return redirect('orders:waiter_dashboard')


@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
@require_POST
def waiter_settle_cash_view(request, order_id):
    """
    Settles order with Cash Payment at Reception/Waiter:
    1. Marks Payment as Paid.
    2. Marks Order as Completed.
    3. Uplifts Table Concurrency Lock.
    """
    order = get_object_or_404(Order, pk=order_id)
    cash_txn = "CASH_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    payment, _ = Payment.objects.get_or_create(
        order=order,
        defaults={'amount': order.total_amount, 'method': Payment.METHOD_CASH_COUNTER, 'transaction_id': cash_txn}
    )
    payment.status = Payment.STATUS_PAID
    payment.method = Payment.METHOD_CASH_COUNTER
    if not payment.transaction_id:
        payment.transaction_id = cash_txn
    payment.collected_by = request.user
    payment.save()

    order.payment_status = Order.PAYMENT_STATUS_PAID
    order.status = Order.STATUS_COMPLETED
    order.save(update_fields=['payment_status', 'status'])

    # Uplift Table Lock & Settle entire Dining Session if applicable
    if order.session:
        for sess_ord in order.session.orders.exclude(status=Order.STATUS_CANCELLED):
            sess_ord.payment_status = Order.PAYMENT_STATUS_PAID
            sess_ord.status = Order.STATUS_COMPLETED
            sess_ord.save(update_fields=['payment_status', 'status'])
            
            p, created = Payment.objects.get_or_create(
                order=sess_ord,
                defaults={'amount': sess_ord.total_amount, 'method': Payment.METHOD_CASH_COUNTER, 'transaction_id': cash_txn}
            )
            if not created and p.status != Payment.STATUS_PAID:
                p.status = Payment.STATUS_PAID
                p.method = Payment.METHOD_CASH_COUNTER
                if not p.transaction_id:
                    p.transaction_id = cash_txn
                p.collected_by = request.user
                p.save()
            elif created:
                p.status = Payment.STATUS_PAID
                p.collected_by = request.user
                p.save()

        order.session.update_totals()
        order.session.end_session()
    elif order.table:
        order.table.release_lock()

    messages.success(request, f"Order #{order.id} settled with cash! Table {order.table_number} is now released.")
    return redirect('orders:waiter_dashboard')


@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
@require_POST
def staff_unlock_table_view(request, table_id):
    """Manually releases a table lock by staff anytime."""
    table = get_object_or_404(RestaurantTable, pk=table_id)
    active_sessions = table.sessions.filter(is_active=True)
    for s in active_sessions:
        s.end_session()
    table.release_lock()
    messages.info(request, f"Lock uplifted for Table {table.table_number}. Table is now available.")
    
    next_url = request.META.get('HTTP_REFERER') or 'orders:waiter_dashboard'
    return redirect(next_url)


@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
@require_POST
def waiter_relock_table_view(request, table_id):
    """
    Re-locks an available table ONLY to the most recent dining session on that table.
    Enables guests who settled early (or paid before eating) to keep dining or order another round.
    Older sessions cannot be resumed. If table is already occupied, re-locking is rejected.
    """
    table = get_object_or_404(RestaurantTable, pk=table_id)
    next_url = request.META.get('HTTP_REFERER') or 'orders:waiter_dashboard'

    # 1. Prevent re-locking if table is currently occupied
    if table.is_locked:
        messages.error(request, f"Table {table.table_number} is already occupied. It cannot be re-locked.")
        return redirect(next_url)

    # 2. Strictly find ONLY the most recent dining session for this table
    last_session = DiningSession.objects.filter(table=table).order_by('-started_at').first()

    if not last_session:
        messages.error(request, f"No previous dining session found for Table {table.table_number}.")
        return redirect(next_url)

    # 3. Enforce that ONLY this last session can be resumed (prevent resuming any older sessions)
    session_id = request.POST.get('session_id')
    if session_id and int(session_id) != last_session.id:
        messages.error(
            request,
            f"Action Blocked: Only the last session on Table {table.table_number} "
            f"(Session #{last_session.id}) can be resumed. Older sessions cannot be reopened."
        )
        return redirect(next_url)

    session = last_session

    # Re-lock table for this customer
    table.lock_for(session.customer)

    # Reactivate the dining session
    session.is_active = True
    session.ended_at = None
    session.save(update_fields=['is_active', 'ended_at'])

    messages.success(
        request,
        f"Table {table.table_number} re-locked to {session.customer.name} under Session #{session.id}. "
        "Customer can continue dining and order more food."
    )
    return redirect(next_url)


@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
@require_POST
def waiter_lock_offline_table_view(request, table_id):
    """
    Locks an unoccupied table for offline/walk-in users who do not want to use the online website.
    - Locks the table so online users cannot order on or occupy it.
    - Creates an active offline dining session for floor service.
    """
    table = get_object_or_404(RestaurantTable, pk=table_id)
    next_url = request.META.get('HTTP_REFERER') or 'orders:waiter_dashboard'

    if table.is_locked:
        messages.warning(request, f"Table {table.table_number} is already occupied.")
        return redirect(next_url)

    guest_name = request.POST.get('guest_name', '').strip()
    if not guest_name:
        guest_name = f"Walk-In Guest (Table {table.table_number})"
    phone = request.POST.get('phone', '').strip()
    notes = request.POST.get('notes', '').strip()

    # Create distinct walk-in customer profile
    unique_suffix = timezone.now().strftime("%y%m%d%H%M%S")
    clean_table = table.table_number.lower().replace('-', '_').replace(' ', '_')
    offline_username = f"walkin_{clean_table}_{unique_suffix}"

    user = User.objects.create_user(
        username=offline_username,
        first_name=guest_name,
        last_name="[Offline Walk-In]"
    )
    customer = Customer.objects.get(user=user)
    if phone:
        customer.phone = phone
    if notes:
        customer.address = f"Walk-In Notes: {notes}"
    customer.save(update_fields=['phone', 'address'])

    # Lock table for offline guest
    table.lock_for(customer)

    # Create active dining session
    session = DiningSession.objects.create(
        customer=customer,
        table=table,
        table_number=table.table_number,
        is_active=True
    )

    messages.success(
        request,
        f"Table {table.table_number} successfully locked for '{guest_name}' (Offline Dining). "
        "Online orders on this table are now blocked."
    )
    return redirect(next_url)


# ==============================================================================
# 3. RESTAURANT MANAGER DASHBOARD (Full Administrative Control)
# ==============================================================================
@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
def manager_dashboard_view(request):
    """
    Master Restaurant Manager Console:
    - Business KPIs: Total Revenue, Today's Orders, Cash vs. Online revenue.
    - Staff Management: view, create staff accounts, change roles (Manager, Waiter, Kitchen).
    - Table Management & QR Code Generator: generate and preview printable static QR codes.
    - Menu Catalog & Live Stock Control: toggle out of stock, update prices.
    - Live Order Monitoring & Emergency Overrides.
    - Session-Wise All Orders View (Expandable/Accordion with Payment IDs).
    - Customer Directory (Lifetime metrics, Google auth, visits, spend).
    """
    today = timezone.localdate()
    today_orders = Order.objects.filter(order_date__date=today)

    total_revenue = Payment.objects.filter(status=Payment.STATUS_PAID).aggregate(Sum('amount'))['amount__sum'] or 0
    today_revenue = Payment.objects.filter(status=Payment.STATUS_PAID, payment_date__date=today).aggregate(Sum('amount'))['amount__sum'] or 0

    cash_revenue = Payment.objects.filter(status=Payment.STATUS_PAID, method=Payment.METHOD_CASH_COUNTER).aggregate(Sum('amount'))['amount__sum'] or 0
    online_revenue = Payment.objects.filter(status=Payment.STATUS_PAID).exclude(method=Payment.METHOD_CASH_COUNTER).aggregate(Sum('amount'))['amount__sum'] or 0

    order_filter = request.GET.get('order_filter', 'active')
    latest_session_ids = set()
    if order_filter == 'all':
        orders_list = Order.objects.all().select_related('customer__user', 'table').prefetch_related('items__menu_item', 'payment').order_by('-order_date')
        sessions_list = DiningSession.objects.filter(orders__isnull=False).distinct().select_related('customer__user', 'table').prefetch_related(
            'orders__items__menu_item',
            'orders__payment'
        ).order_by('-started_at')
        standalone_orders = Order.objects.filter(session__isnull=True).select_related('customer__user', 'table').prefetch_related(
            'items__menu_item',
            'payment'
        ).order_by('-order_date')

        # Strictly map each table to its single latest session ID (only the last session can be resumed)
        latest_session_map = {}
        for s in DiningSession.objects.filter(table__isnull=False).order_by('-started_at'):
            if s.table_id not in latest_session_map:
                latest_session_map[s.table_id] = s.id
                latest_session_ids.add(s.id)
    else:
        orders_list = Order.objects.exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).select_related('customer__user', 'table').prefetch_related('items__menu_item', 'payment').order_by('-order_date')
        sessions_list = []
        standalone_orders = []

    active_orders_count = Order.objects.exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).count()
    all_orders_count = Order.objects.count()
    all_sessions_count = DiningSession.objects.count()
    status_hash = "-".join(f"{o.id}:{o.status}:{o.payment_status}" for o in orders_list)

    if request.GET.get('poll') == '1' or request.GET.get('json') == '1':
        orders_payload = [
            {
                'id': o.id,
                'status': o.status,
                'status_display': o.get_status_display(),
                'payment_status': o.payment_status,
                'total_amount': str(o.total_amount),
            } for o in orders_list
        ]
        return JsonResponse({
            'success': True,
            'active_orders_count': active_orders_count,
            'all_orders_count': all_orders_count,
            'status_hash': status_hash,
            'orders': orders_payload,
        })

    # Customer Directory with aggregated lifetime metrics
    customers = Customer.objects.select_related('user').annotate(
        total_sessions=Count('dining_sessions', distinct=True),
        total_orders=Count('orders', distinct=True),
        lifetime_spend=Coalesce(
            Sum('orders__total_amount', filter=~Q(orders__status=Order.STATUS_CANCELLED)),
            Value(Decimal('0.00'))
        )
    ).order_by('-user__date_joined')

    tables = RestaurantTable.objects.all().order_by('table_number')
    staff_members = StaffProfile.objects.select_related('user').all()
    menu_items = MenuItem.objects.select_related('category').all().order_by('category', 'name')
    categories = Category.objects.all().order_by('name')

    # Review Moderation & Feedback Analytics
    reviews_qs = Review.objects.select_related('customer__user', 'menu_item__category').order_by('-review_date')
    reviews_count = reviews_qs.count()
    avg_rating_val = reviews_qs.aggregate(Avg('rating'))['rating__avg']
    avg_rating = round(avg_rating_val, 1) if avg_rating_val else None

    reviews_breakdown = {
        5: reviews_qs.filter(rating=5).count(),
        4: reviews_qs.filter(rating=4).count(),
        3: reviews_qs.filter(rating=3).count(),
        2: reviews_qs.filter(rating=2).count(),
        1: reviews_qs.filter(rating=1).count(),
    }

    # Generate QR codes for all tables and attach last session for manager re-lock support
    host = request.build_absolute_uri('/')[:-1]
    tables_with_qr = []
    for t in tables:
        last_s = DiningSession.objects.filter(table=t).select_related('customer__user').order_by('-started_at').first()
        tables_with_qr.append({
            'table': t,
            'qr_data_uri': t.generate_qr_base64(host),
            'last_session': last_s,
        })

    context = {
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        'cash_revenue': cash_revenue,
        'online_revenue': online_revenue,
        'orders_list': orders_list,
        'active_orders': orders_list,
        'sessions_list': sessions_list,
        'standalone_orders': standalone_orders,
        'latest_session_ids': latest_session_ids,
        'order_filter': order_filter,
        'active_orders_count': active_orders_count,
        'all_orders_count': all_orders_count,
        'all_sessions_count': all_sessions_count,
        'customers': customers,
        'status_hash': status_hash,
        'tables_with_qr': tables_with_qr,
        'staff_members': staff_members,
        'menu_items': menu_items,
        'categories': categories,
        'reviews_list': reviews_qs,
        'reviews_count': reviews_count,
        'avg_rating': avg_rating,
        'reviews_breakdown': reviews_breakdown,
        'role_choices': StaffProfile.ROLE_CHOICES,
        'status_choices': Order.STATUS_CHOICES,
        'payment_status_choices': Order.PAYMENT_STATUS_CHOICES,
    }
    return render(request, 'staff/manager_dashboard.html', context)


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_create_staff_view(request):
    """Creates a new staff user and assigns role."""
    username = request.POST.get('username', '').strip().lower()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    password = request.POST.get('password', '')
    role = request.POST.get('role', StaffProfile.ROLE_WAITER)
    phone = request.POST.get('phone', '').strip()

    if not username or not password:
        messages.error(request, "Username and password are required.")
        return redirect(reverse('orders:manager_dashboard') + '#staff-pane')

    if User.objects.filter(username=username).exists():
        messages.error(request, f"Username '{username}' already exists.")
        return redirect(reverse('orders:manager_dashboard') + '#staff-pane')

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=True
    )
    StaffProfile.objects.create(user=user, role=role, phone=phone)
    messages.success(request, f"Created staff account for {user.get_full_name() or username} with role: {role}.")
    return redirect(reverse('orders:manager_dashboard') + '#staff-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_update_staff_role_view(request, staff_id):
    """Updates role of an existing staff member."""
    staff = get_object_or_404(StaffProfile, pk=staff_id)
    new_role = request.POST.get('role')
    if new_role in [StaffProfile.ROLE_MANAGER, StaffProfile.ROLE_WAITER, StaffProfile.ROLE_KITCHEN]:
        staff.role = new_role
        staff.save(update_fields=['role'])
        messages.success(request, f"Updated role of {staff.user.username} to {staff.get_role_display()}.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'role': staff.role, 'role_display': staff.get_role_display()})
    return redirect(reverse('orders:manager_dashboard') + '#staff-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_edit_staff_view(request, staff_id):
    """Edits an existing staff member's name, phone and role."""
    staff = get_object_or_404(StaffProfile, pk=staff_id)
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    phone = request.POST.get('phone', '').strip()
    new_role = request.POST.get('role', staff.role)

    staff.user.first_name = first_name
    staff.user.last_name = last_name
    staff.user.save(update_fields=['first_name', 'last_name'])

    staff.phone = phone
    if new_role in [StaffProfile.ROLE_MANAGER, StaffProfile.ROLE_WAITER, StaffProfile.ROLE_KITCHEN]:
        staff.role = new_role
    staff.save(update_fields=['phone', 'role'])

    messages.success(request, f"Staff account '{staff.user.username}' updated successfully.")
    return redirect(reverse('orders:manager_dashboard') + '#staff-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_delete_staff_view(request, staff_id):
    """Deletes a staff member account entirely."""
    staff = get_object_or_404(StaffProfile, pk=staff_id)
    username = staff.user.username
    # Prevent deleting own account
    if staff.user == request.user:
        messages.error(request, "You cannot delete your own staff account.")
        return redirect(reverse('orders:manager_dashboard') + '#staff-pane')
    staff.user.delete()  # cascades to StaffProfile
    messages.success(request, f"Staff account '{username}' has been deleted.")
    return redirect(reverse('orders:manager_dashboard') + '#staff-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_reset_staff_password_view(request, staff_id):
    """Resets the password for a staff member account."""
    staff = get_object_or_404(StaffProfile, pk=staff_id)
    new_password = request.POST.get('new_password', '').strip()
    if not new_password or len(new_password) < 4:
        messages.error(request, "Password must be at least 4 characters long.")
        return redirect(reverse('orders:manager_dashboard') + '#staff-pane')

    staff.user.set_password(new_password)
    staff.user.save(update_fields=['password'])
    messages.success(request, f"Password for staff member '{staff.user.username}' has been reset successfully.")
    return redirect(reverse('orders:manager_dashboard') + '#staff-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_toggle_item_availability_view(request, item_id):
    """Toggles item stock status (In Stock / Out of Stock)."""
    item = get_object_or_404(MenuItem, pk=item_id)
    item.is_available = not item.is_available
    item.save(update_fields=['is_available'])
    status_str = "In Stock" if item.is_available else "Out of Stock"
    messages.info(request, f"{item.name} is now marked as {status_str}.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
        return JsonResponse({
            'success': True,
            'item_id': item.id,
            'is_available': item.is_available,
            'status_str': status_str,
            'message': f"{item.name} is now {status_str}."
        })
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_update_item_price_view(request, item_id):
    """Updates menu item price dynamically."""
    item = get_object_or_404(MenuItem, pk=item_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json'
    try:
        new_price = float(request.POST.get('price', 0))
        if new_price <= 0:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Price must be greater than zero.'}, status=400)
            messages.error(request, "Price must be greater than zero.")
        else:
            item.price = new_price
            item.save(update_fields=['price'])
            messages.success(request, f"Updated price of {item.name} to ₹{item.price}.")
            if is_ajax:
                return JsonResponse({'success': True, 'item_id': item.id, 'price': str(item.price), 'message': f"Price updated to ₹{item.price}."})
    except (ValueError, TypeError):
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Invalid price format.'}, status=400)
        messages.error(request, "Invalid price format.")
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_create_item_view(request):
    """Adds a new food item to the digital menu."""
    category_id = request.POST.get('category_id')
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    price = request.POST.get('price', 0)
    is_veg = request.POST.get('is_veg') == '1'
    image_url = request.POST.get('image_url', '').strip()

    category = get_object_or_404(Category, pk=category_id)
    if not name or float(price) <= 0:
        messages.error(request, "Item name and valid positive price are required.")
        return redirect(reverse('orders:manager_dashboard') + '#menu-pane')

    image_file = request.FILES.get('image')

    item = MenuItem.objects.create(
        category=category,
        name=name,
        description=description,
        price=price,
        is_veg=is_veg,
        is_available=True,
        image=image_file,
        image_url=image_url or None
    )
    messages.success(request, f"Successfully created new menu item: {item.name} (₹{item.price}).")
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_edit_item_view(request, item_id):
    """Updates an existing food item in the digital menu."""
    item = get_object_or_404(MenuItem, pk=item_id)
    category_id = request.POST.get('category_id')
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    price = request.POST.get('price', 0)
    is_veg = request.POST.get('is_veg') == '1'
    image_url = request.POST.get('image_url', '').strip()

    try:
        price_val = float(price)
        if not name or price_val <= 0:
            messages.error(request, "Item name and valid positive price are required.")
            return redirect(reverse('orders:manager_dashboard') + '#menu-pane')
    except (ValueError, TypeError):
        messages.error(request, "Invalid price amount entered.")
        return redirect(reverse('orders:manager_dashboard') + '#menu-pane')

    if category_id:
        item.category = get_object_or_404(Category, pk=category_id)

    item.name = name
    item.description = description
    item.price = price_val
    item.is_veg = is_veg
    item.image_url = image_url or None

    if 'image' in request.FILES:
        item.image = request.FILES['image']
    elif request.POST.get('clear_image_file') == '1':
        item.image = None

    item.save()
    messages.success(request, f"Successfully updated dish: {item.name}.")
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_create_table_view(request):
    """Adds a new dining table."""
    table_number = request.POST.get('table_number', '').strip().upper()
    capacity = request.POST.get('capacity', 4)

    if not table_number:
        messages.error(request, "Table number cannot be empty.")
        return redirect(reverse('orders:manager_dashboard') + '#qr-pane')

    if RestaurantTable.objects.filter(table_number__iexact=table_number).exists():
        messages.error(request, f"Table '{table_number}' already exists.")
        return redirect(reverse('orders:manager_dashboard') + '#qr-pane')

    RestaurantTable.objects.create(table_number=table_number, capacity=capacity)
    messages.success(request, f"Added Table {table_number} with capacity {capacity}.")
    return redirect(reverse('orders:manager_dashboard') + '#qr-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_toggle_table_view(request, table_id):
    """Toggles table active/inactive service status."""
    table = get_object_or_404(RestaurantTable, pk=table_id)
    table.is_active = not table.is_active
    table.save(update_fields=['is_active'])
    status_str = "Active" if table.is_active else "Inactive"
    messages.info(request, f"Table {table.table_number} is now {status_str}.")
    return redirect(reverse('orders:manager_dashboard') + '#qr-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_edit_table_view(request, table_id):
    """Edits a table's number and capacity."""
    table = get_object_or_404(RestaurantTable, pk=table_id)
    new_number = request.POST.get('table_number', '').strip().upper()
    new_capacity = request.POST.get('capacity', table.capacity)

    if not new_number:
        messages.error(request, "Table number cannot be empty.")
        return redirect(reverse('orders:manager_dashboard') + '#qr-pane')

    # Check uniqueness (excluding self)
    if RestaurantTable.objects.filter(table_number__iexact=new_number).exclude(pk=table_id).exists():
        messages.error(request, f"Table '{new_number}' already exists.")
        return redirect(reverse('orders:manager_dashboard') + '#qr-pane')

    table.table_number = new_number
    try:
        table.capacity = int(new_capacity)
    except (ValueError, TypeError):
        pass
    table.save(update_fields=['table_number', 'capacity'])
    messages.success(request, f"Table updated to '{new_number}' with capacity {table.capacity}.")
    return redirect(reverse('orders:manager_dashboard') + '#qr-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_delete_table_view(request, table_id):
    """Deletes a dining table."""
    table = get_object_or_404(RestaurantTable, pk=table_id)
    if table.is_locked:
        messages.error(request, f"Cannot delete Table {table.table_number} while it is occupied.")
        return redirect(reverse('orders:manager_dashboard') + '#qr-pane')
    tnum = table.table_number
    table.delete()
    messages.success(request, f"Table '{tnum}' deleted.")
    return redirect(reverse('orders:manager_dashboard') + '#qr-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_edit_category_view(request, category_id):
    """Edits an existing menu category's name and description."""
    cat = get_object_or_404(Category, pk=category_id)
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    if not name:
        messages.error(request, "Category name cannot be empty.")
        return redirect(reverse('orders:manager_dashboard') + '#menu-pane')
    cat.name = name
    cat.description = description
    cat.save(update_fields=['name', 'description'])
    messages.success(request, f"Category updated to '{cat.name}'.")
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_delete_item_view(request, item_id):
    """Deletes a menu item from the catalog."""
    item = get_object_or_404(MenuItem, pk=item_id)
    name = item.name
    item.delete()
    messages.success(request, f"Menu item '{name}' has been deleted.")
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_create_category_view(request):
    """Adds a new menu category."""
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    if not name:
        messages.error(request, "Category name cannot be empty.")
        return redirect(reverse('orders:manager_dashboard') + '#menu-pane')

    from menu.models import Restaurant
    restaurant = Restaurant.objects.first()
    if not restaurant:
        restaurant = Restaurant.objects.create(name="Spice Garden", address="City Center", phone="+91 98220 12345")

    cat = Category.objects.create(restaurant=restaurant, name=name, description=description)
    messages.success(request, f"Created new category: '{cat.name}'.")
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_delete_category_view(request, category_id):
    """Deletes a menu category."""
    cat = get_object_or_404(Category, pk=category_id)
    name = cat.name
    cat.delete()
    messages.success(request, f"Category '{name}' and associated items removed.")
    return redirect(reverse('orders:manager_dashboard') + '#menu-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_update_order_status_view(request, order_id):
    """Full control to update an order's status to any pipeline state."""
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get('status')
    valid_statuses = [c[0] for c in Order.STATUS_CHOICES]

    if new_status in valid_statuses:
        order.status = new_status
        if new_status == Order.STATUS_COMPLETED:
            order.payment_status = Order.PAYMENT_STATUS_PAID
            Payment.objects.filter(order=order).update(status=Payment.STATUS_PAID)
            if order.session:
                order.session.update_totals()
                if not order.session.orders.filter(payment_status=Order.PAYMENT_STATUS_PENDING).exclude(pk=order.pk).exists():
                    order.session.end_session()
            elif order.table:
                order.table.release_lock()
        elif new_status == Order.STATUS_CANCELLED:
            order.items.update(is_cancelled=True)
            order.recalculate_totals()
            if order.table:
                if not Order.objects.filter(table=order.table).exclude(pk=order.pk).exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).exists():
                    order.table.release_lock()
        order.save(update_fields=['status', 'payment_status'])
        messages.success(request, f"Order #{order.id} status updated to {new_status}.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'status': order.status,
            'status_display': order.get_status_display()
        })
    return redirect(reverse('orders:manager_dashboard') + '#orders-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_update_order_payment_view(request, order_id):
    """Full control to update an order's payment status & settlement."""
    order = get_object_or_404(Order, pk=order_id)
    new_pay_status = request.POST.get('payment_status')

    if new_pay_status in [Order.PAYMENT_STATUS_PAID, Order.PAYMENT_STATUS_PENDING]:
        order.payment_status = new_pay_status
        order.save(update_fields=['payment_status'])

        payment, _ = Payment.objects.get_or_create(
            order=order,
            defaults={'amount': order.total_amount, 'method': Payment.METHOD_CASH_COUNTER}
        )
        payment.status = new_pay_status
        payment.collected_by = request.user
        payment.save()

        if new_pay_status == Order.PAYMENT_STATUS_PAID and order.table:
            if not Order.objects.filter(table=order.table).exclude(status=Order.STATUS_CANCELLED).filter(payment_status=Order.PAYMENT_STATUS_PENDING).exists():
                order.table.release_lock()

        messages.success(request, f"Order #{order.id} payment updated to {new_pay_status}.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'payment_status': order.payment_status
        })
    return redirect(reverse('orders:manager_dashboard') + '#orders-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_cancel_order_view(request, order_id):
    """Emergency cancel an order entirely."""
    order = get_object_or_404(Order, pk=order_id)
    order.status = Order.STATUS_CANCELLED
    order.save(update_fields=['status'])
    order.items.update(is_cancelled=True)
    order.recalculate_totals()
    if order.table:
        if not Order.objects.filter(table=order.table).exclude(pk=order.pk).exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).exists():
            order.table.release_lock()
    messages.warning(request, f"Order #{order.id} was cancelled by Manager override.")
    return redirect(reverse('orders:manager_dashboard') + '#orders-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_delete_review_view(request, review_id):
    """Allows restaurant manager to moderate/delete inappropriate or spam reviews."""
    review = get_object_or_404(Review, pk=review_id)
    dish_name = review.menu_item.name
    cust_name = review.customer.name
    review.delete()
    messages.success(request, f"Review for '{dish_name}' by '{cust_name}' deleted successfully.")
    return redirect(reverse('orders:manager_dashboard') + '#reviews-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_create_customer_view(request):
    """Creates a new customer/user account."""
    username = request.POST.get('username', '').strip().lower()
    email = request.POST.get('email', '').strip().lower()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    phone = request.POST.get('phone', '').strip()
    password = request.POST.get('password', '').strip()

    if not username:
        messages.error(request, "Username is required.")
        return redirect(reverse('orders:manager_dashboard') + '#customers-pane')

    if User.objects.filter(username=username).exists():
        messages.error(request, f"Username '{username}' already exists.")
        return redirect(reverse('orders:manager_dashboard') + '#customers-pane')

    if email and User.objects.filter(email=email).exists():
        messages.error(request, f"Email '{email}' is already registered.")
        return redirect(reverse('orders:manager_dashboard') + '#customers-pane')

    # Default password if none provided
    if not password:
        password = "Customer@" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=False
    )
    customer, _ = Customer.objects.get_or_create(user=user)
    if phone:
        customer.phone = phone
        customer.save(update_fields=['phone'])

    messages.success(request, f"Customer account '{user.username}' created successfully.")
    return redirect(reverse('orders:manager_dashboard') + '#customers-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_edit_customer_view(request, customer_id):
    """Updates customer/user details."""
    customer = get_object_or_404(Customer, pk=customer_id)
    user = customer.user
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip().lower()
    phone = request.POST.get('phone', '').strip()

    if email and User.objects.filter(email=email).exclude(pk=user.pk).exists():
        messages.error(request, f"Email '{email}' is already in use by another user.")
        return redirect(reverse('orders:manager_dashboard') + '#customers-pane')

    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.save(update_fields=['first_name', 'last_name', 'email'])

    customer.phone = phone
    customer.save(update_fields=['phone'])

    messages.success(request, f"Customer '{customer.name}' updated successfully.")
    return redirect(reverse('orders:manager_dashboard') + '#customers-pane')


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
@require_POST
def manager_delete_customer_view(request, customer_id):
    """Deletes a customer/user account."""
    customer = get_object_or_404(Customer, pk=customer_id)
    user = customer.user

    if user == request.user or user.is_superuser:
        messages.error(request, "Cannot delete this user account.")
        return redirect(reverse('orders:manager_dashboard') + '#customers-pane')

    name = customer.name
    # Release any active locks held by customer
    RestaurantTable.objects.filter(current_customer=customer).update(is_locked=False, current_customer=None, locked_at=None)

    user.delete()  # Cascades to customer profile
    messages.success(request, f"Customer '{name}' deleted successfully.")
    return redirect(reverse('orders:manager_dashboard') + '#customers-pane')


# ==============================================================================
# 5. DEDICATED MANAGER ORDER & SESSION DETAILS VIEWS
# ==============================================================================
@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
def manager_session_detail_view(request, session_id):
    """
    Dedicated Executive Details Page for a Dining Session.
    Provides complete breakdown of all tickets, items, payment transactions, customer profile, and audit trail.
    """
    session_obj = get_object_or_404(
        DiningSession.objects.select_related('customer__user', 'table').prefetch_related(
            'orders__items__menu_item__category',
            'orders__payment__collected_by'
        ),
        pk=session_id
    )
    orders = session_obj.orders.all().order_by('order_date')
    payments = session_obj.payments_list
    combined_payments = session_obj.get_combined_payments(status=Payment.STATUS_PAID)
    
    subtotal = sum((o.subtotal for o in orders if o.status != Order.STATUS_CANCELLED), Decimal('0.00'))
    tax_amount = sum((o.tax_amount for o in orders if o.status != Order.STATUS_CANCELLED), Decimal('0.00'))
    total_amount = sum((o.total_amount for o in orders if o.status != Order.STATUS_CANCELLED), Decimal('0.00'))
    total_paid = sum((p.amount for p in payments if p.status == Payment.STATUS_PAID), Decimal('0.00'))
    balance_due = max(Decimal('0.00'), total_amount - total_paid)

    can_relock = False
    if not session_obj.is_active and session_obj.table and not session_obj.table.is_locked:
        latest = DiningSession.objects.filter(table=session_obj.table).order_by('-started_at').first()
        if latest and latest.id == session_obj.id:
            can_relock = True

    context = {
        'session': session_obj,
        'orders': orders,
        'payments': payments,
        'combined_payments': combined_payments,
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'balance_due': balance_due,
        'can_relock': can_relock,
    }
    return render(request, 'staff/manager_session_detail.html', context)


@login_required
@staff_role_required([StaffProfile.ROLE_MANAGER])
def manager_order_detail_view(request, order_id):
    """
    Dedicated Order Details Page.
    If part of a dining session, redirects to manager_session_detail with anchor.
    Otherwise renders direct order details.
    """
    order_obj = get_object_or_404(
        Order.objects.select_related('customer__user', 'table', 'session', 'payment').prefetch_related('items__menu_item__category'),
        pk=order_id
    )
    if order_obj.session_id:
        return redirect(f"{reverse('orders:manager_session_detail', args=[order_obj.session_id])}#order-{order_obj.id}")
    
    return render(request, 'staff/manager_order_detail.html', {
        'order': order_obj,
        'status_choices': Order.STATUS_CHOICES,
    })


@login_required
@require_POST
def staff_change_password_view(request):
    """
    Self-service password change for all staff members (Kitchen, Waiter, Manager).
    Verifies the user's current password, securely hashes the new password with Django's
    built-in PBKDF2 hashing algorithm (never stored in plain text), and updates the session
    auth hash to keep the staff user logged in.
    Supports both AJAX requests (JSON response) and standard form POST (redirect + messages).
    """
    is_staff_user = hasattr(request.user, 'staff_profile') or request.user.is_superuser or request.user.is_staff
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    if not is_staff_user:
        error_msg = "Only staff members can use this password change portal."
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=403)
        messages.error(request, error_msg)
        return redirect('menu:menu_list')

    current_password = request.POST.get('current_password', '')
    new_password = request.POST.get('new_password', '').strip()
    confirm_password = request.POST.get('confirm_password', '').strip()

    def _err_res(msg):
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect(request.META.get('HTTP_REFERER') or 'orders:kitchen_dashboard')

    if not current_password:
        return _err_res("Current password is required.")

    if not request.user.check_password(current_password):
        return _err_res("Current password is incorrect. Please re-enter your existing password.")

    if not new_password or len(new_password) < 4:
        return _err_res("New password must be at least 4 characters long.")

    if new_password != confirm_password:
        return _err_res("New password and confirmation do not match.")

    if current_password == new_password:
        return _err_res("New password must be different from current password.")

    # Securely hash and save new password (PBKDF2 SHA-256, never in plain text)
    request.user.set_password(new_password)
    request.user.save(update_fields=['password'])

    # Keep staff session active without forcing logout
    update_session_auth_hash(request, request.user)

    success_msg = f"Password for '{request.user.username}' changed successfully! Your session remains active."
    if is_ajax:
        return JsonResponse({'success': True, 'message': success_msg})

    messages.success(request, success_msg)
    return redirect(request.META.get('HTTP_REFERER') or 'orders:kitchen_dashboard')


