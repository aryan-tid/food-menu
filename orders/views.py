import json
import hmac
import hashlib
import random
import string
from decimal import Decimal
import razorpay
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.contrib.auth.decorators import login_required
from menu.models import MenuItem, Restaurant
from accounts.models import Customer, StaffProfile
from .models import RestaurantTable, Order, OrderItem, Payment, DiningSession, WaiterAlert
from .staff_views import staff_role_required


def cart_add_view(request, item_id):
    """Adds a menu item to the session cart."""
    item = get_object_or_404(MenuItem, pk=item_id, is_available=True)
    cart = request.session.get('cart', {})
    item_str = str(item_id)
    cart[item_str] = cart.get(item_str, 0) + 1
    request.session['cart'] = cart
    request.session.modified = True
    messages.success(request, f"Added {item.name} to cart.")

    next_url = request.META.get('HTTP_REFERER') or 'orders:cart'
    return redirect(next_url)


def cart_remove_view(request, item_id):
    """Decrements or removes an item from the session cart."""
    cart = request.session.get('cart', {})
    item_str = str(item_id)
    if item_str in cart:
        if cart[item_str] > 1:
            cart[item_str] -= 1
        else:
            del cart[item_str]
        request.session['cart'] = cart
        request.session.modified = True
    return redirect('orders:cart')


def cart_delete_view(request, item_id):
    """Deletes an item entirely from the session cart."""
    cart = request.session.get('cart', {})
    item_str = str(item_id)
    if item_str in cart:
        del cart[item_str]
        request.session['cart'] = cart
        request.session.modified = True
    return redirect('orders:cart')


def cart_clear_view(request):
    """Clears all items from the cart."""
    request.session['cart'] = {}
    request.session.modified = True
    messages.info(request, "Cart cleared.")
    return redirect('orders:cart')


def cart_view(request):
    """
    Cart & Checkout Review Screen.
    - Displays items, subtotal, 5% tax, total.
    - Validates table concurrency lock before allowing checkout.
    - Requires Google Login to place order.
    """
    cart = request.session.get('cart', {})
    items_data = []
    subtotal = Decimal('0.00')

    if cart:
        menu_items = MenuItem.objects.filter(id__in=cart.keys())
        for item in menu_items:
            qty = cart.get(str(item.id), 0)
            line_total = item.price * qty
            subtotal += line_total
            items_data.append({
                'item': item,
                'quantity': qty,
                'subtotal': line_total,
            })

    tax_amount = round(subtotal * Decimal('0.05'), 2)
    grand_total = subtotal + tax_amount

    # Validate Table Lock
    table_id = request.session.get('table_id')
    current_table = None
    table_locked_by_other = False

    if table_id:
        current_table = RestaurantTable.objects.filter(table_number__iexact=str(table_id).strip()).first()
        if current_table and current_table.is_locked:
            if hasattr(request.user, 'customer_profile'):
                if current_table.current_customer != request.user.customer_profile:
                    table_locked_by_other = True
            else:
                table_locked_by_other = True

    context = {
        'cart_items': items_data,
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'grand_total': grand_total,
        'current_table': current_table,
        'current_table_number': table_id,
        'table_locked_by_other': table_locked_by_other,
    }
    return render(request, 'orders/cart.html', context)


def checkout_view(request):
    """
    Processes Order Placement:
    1. Checks customer login (prompts Google sign-in if guest).
    2. Validates live inventory/availability of all cart items.
    3. Enforces Table Lock Guard (prevents ordering if table is held by another active diner).
    4. Finds or creates an active DiningSession for the customer.
    5. Handles 2 payment options within atomic transaction.
    """
    if not request.user.is_authenticated:
        messages.warning(request, "Please sign in with Google to place your order.")
        return redirect(f"/accounts/login/?next={request.path}")

    customer, _ = Customer.objects.get_or_create(user=request.user)
    cart = request.session.get('cart', {})

    if not cart:
        messages.error(request, "Your cart is empty.")
        return redirect('menu:menu_list')

    # 1. Live inventory & availability validation
    unavailable_items = []
    valid_items = []
    for item_id_str, qty in list(cart.items()):
        try:
            m_item = MenuItem.objects.get(pk=int(item_id_str))
            if not m_item.is_available:
                unavailable_items.append(m_item.name)
                del cart[item_id_str]
            else:
                valid_items.append((m_item, qty))
        except (MenuItem.DoesNotExist, ValueError):
            del cart[item_id_str]

    if unavailable_items:
        request.session['cart'] = cart
        request.session.modified = True
        messages.error(
            request,
            f"The following item(s) are currently out of stock: {', '.join(unavailable_items)}. "
            "They have been removed from your cart."
        )
        return redirect('orders:cart')

    if not valid_items:
        messages.error(request, "All items in your cart were unavailable. Please choose other dishes.")
        return redirect('menu:menu_list')

    # 2. Table validation & Concurrency lock check
    table_num = request.session.get('table_id')
    order_type = Order.ORDER_TYPE_DINE_IN if table_num else Order.ORDER_TYPE_TAKEAWAY
    table_obj = None

    if table_num:
        table_obj = RestaurantTable.objects.filter(table_number__iexact=str(table_num).strip()).first()
        if table_obj:
            if table_obj.is_locked and table_obj.current_customer != customer:
                messages.error(
                    request,
                    f"Table {table_obj.table_number} is currently occupied by an active diner. "
                    "Please verify your table or contact a waiter."
                )
                return redirect('orders:cart')

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', Order.PAYMENT_METHOD_PAY_LATER)
        special_instructions = request.POST.get('special_instructions', '').strip()

        # For table diners: NEVER ask table user to pay now!
        # intermediate orders always defer payment to end of dining session.
        if table_obj:
            payment_method = Order.PAYMENT_METHOD_PAY_LATER

        with transaction.atomic():
            # Get or create active Dining Session
            if table_obj:
                dining_session, _ = DiningSession.objects.get_or_create(
                    customer=customer,
                    table=table_obj,
                    is_active=True,
                    defaults={'table_number': table_obj.table_number}
                )
            else:
                dining_session, _ = DiningSession.objects.get_or_create(
                    customer=customer,
                    table=None,
                    is_active=True,
                    defaults={'table_number': 'Takeaway'}
                )

            # Each ordering round creates a distinct Order ticket under this active session
            order = Order.objects.create(
                session=dining_session,
                customer=customer,
                table=table_obj,
                table_number=table_obj.table_number if table_obj else 'Takeaway',
                order_type=order_type,
                payment_method=payment_method,
                payment_status=Order.PAYMENT_STATUS_PENDING,
                special_instructions=special_instructions,
            )

            for m_item, qty in valid_items:
                OrderItem.objects.create(
                    order=order,
                    menu_item=m_item,
                    quantity=qty,
                    price=m_item.price
                )

            order.recalculate_totals()

            # Create 1-to-1 Payment Record satisfying schema
            Payment.objects.create(
                order=order,
                method=Payment.METHOD_ONLINE_UPI if payment_method == Order.PAYMENT_METHOD_ONLINE else Payment.METHOD_CASH_COUNTER,
                amount=order.total_amount,
                status=Payment.STATUS_PENDING
            )

            # Acquire/Ensure Table Concurrency Lock
            if table_obj:
                table_obj.lock_for(customer)

            if dining_session:
                dining_session.update_totals()

        # Clear cart
        request.session['cart'] = {}
        request.session.modified = True

        if not table_obj and payment_method == Order.PAYMENT_METHOD_ONLINE:
            return redirect('orders:payment_gateway', order_id=order.id)

        messages.success(request, f"Order #{order.id} sent to kitchen! (Table: {order.table_number})")
        return redirect('orders:session_live_detail', session_id=dining_session.id)

    return redirect('orders:cart')


def payment_gateway_view(request, order_id):
    """
    Simulated Payment Gateway (UPI QR Code / Card / Netbanking):
    - Completely self-contained: works offline and in viva without third-party API dependencies.
    - Generates a random Payment ID & Transaction reference.
    - On confirmation: marks payment as Paid, updates order payment status, and releases table lock!
    """
    order = get_object_or_404(Order, pk=order_id)
    payment = get_object_or_404(Payment, order=order)

    if order.payment_status == Order.PAYMENT_STATUS_PAID:
        messages.info(request, "This order is already settled.")
        return redirect('orders:order_live', order_id=order.id)

    # For table dining, intermediate orders cannot be settled before delivery
    if order.table and order.status not in [Order.STATUS_SERVED, Order.STATUS_COMPLETED]:
        messages.warning(request, "This order cannot be settled yet. Food must be delivered to your table before payment.")
        return redirect('orders:order_live', order_id=order.id)

    if request.method == 'POST':
        method_selected = request.POST.get('method', Payment.METHOD_ONLINE_UPI)
        txn_id = "TXN_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))

        with transaction.atomic():
            payment.method = method_selected
            payment.status = Payment.STATUS_PAID
            payment.transaction_id = txn_id
            payment.save(update_fields=['method', 'status', 'transaction_id'])

            order.payment_status = Order.PAYMENT_STATUS_PAID
            order.status = Order.STATUS_COMPLETED
            order.save(update_fields=['payment_status', 'status'])

            # Settle session if all orders settled
            if order.session:
                order.session.update_totals()
                unsettled = order.session.orders.filter(payment_status=Order.PAYMENT_STATUS_PENDING).exclude(pk=order.pk).exists()
                if not unsettled:
                    for s_ord in order.session.orders.exclude(status=Order.STATUS_CANCELLED):
                        s_ord.status = Order.STATUS_COMPLETED
                        s_ord.save(update_fields=['status'])
                    order.session.end_session()
            elif order.table:
                order.table.release_lock()

        messages.success(request, f"Payment of ₹{order.total_amount} successful! Ref: {txn_id}. Table lock released.")
        return redirect('orders:order_live', order_id=order.id)

    return render(request, 'orders/payment_gateway.html', {
        'order': order,
        'payment': payment,
        'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', '')
    })


def order_live_view(request, order_id):
    """
    Delegates single order tracking directly to the consolidated dining session tracker.
    All orders in the visit are shown on one cohesive screen with newest on top.
    """
    order = get_object_or_404(Order, pk=order_id)
    if order.session:
        return redirect('orders:session_live_detail', session_id=order.session.id)
    return render(request, 'orders/order_live.html', {'order': order})


def session_live_view(request, session_id=None):
    """
    Consolidated Real-Time Dining Session Tracker:
    - Displays ALL order tickets placed during this active dining session.
    - Newest order is at the top (Round 2, Round 1 below).
    - Status stepper for each order (Pending -> Preparing -> Ready -> Served).
    - Customer can cancel items or entire order IF order is in Pending status.
    - At the bottom: Consolidated Session Bill (Total items, dishes subtotal, 5% GST, grand total).
    - Action to Settle Session Bill (UPI/Card or Cash at Reception) and release table lock.
    - Printable Consolidated Receipt button.
    """
    if not request.user.is_authenticated:
        return redirect('accounts:google_login')

    customer = getattr(request.user, 'customer_profile', None)
    is_staff = hasattr(request.user, 'staff_profile') or request.user.is_superuser

    if session_id:
        session_obj = get_object_or_404(DiningSession.objects.prefetch_related('orders__items__menu_item'), pk=session_id)
        if not is_staff and session_obj.customer != customer:
            messages.error(request, "Permission denied.")
            return redirect('menu:menu_list')
    else:
        # Resolve active session for customer
        if not customer:
            return redirect('menu:menu_list')
        session_obj = DiningSession.objects.filter(customer=customer, is_active=True).first()
        if not session_obj:
            messages.info(request, "You do not have an active dining session.")
            return redirect('menu:menu_list')

    # All orders in reverse chronological order (newest on top!)
    orders_list = session_obj.orders.prefetch_related('items__menu_item', 'payment').order_by('-order_date')
    active_orders = orders_list.exclude(status=Order.STATUS_CANCELLED)

    consolidated_subtotal = session_obj.subtotal_amount
    consolidated_tax = session_obj.tax_sum
    consolidated_total = session_obj.grand_total_amount
    session_obj.total_spent = consolidated_total
    session_obj.save(update_fields=['total_spent'])

    unpaid_orders = session_obj.unpaid_orders_qs
    unpaid_total = session_obj.unpaid_total_amount
    paid_total = session_obj.paid_total_amount

    all_items = []
    for ord_obj in orders_list:
        for itm in ord_obj.items.all():
            if not itm.is_cancelled:
                all_items.append(itm)

    is_all_served = active_orders.exists() and all(o.status in [Order.STATUS_SERVED, Order.STATUS_COMPLETED] for o in active_orders)
    is_fully_paid = active_orders.exists() and all(o.payment_status == Order.PAYMENT_STATUS_PAID for o in active_orders)
    has_active_cooking = any(o.status in [Order.STATUS_PENDING, Order.STATUS_PREPARING, Order.STATUS_READY] for o in active_orders)
    status_hash = "-".join(f"{o.id}:{o.status}:{o.payment_status}" for o in orders_list)

    context = {
        'session': session_obj,
        'orders': orders_list,
        'active_orders': active_orders,
        'consolidated_subtotal': consolidated_subtotal,
        'consolidated_tax': consolidated_tax,
        'consolidated_total': consolidated_total,
        'unpaid_total': unpaid_total,
        'paid_total': paid_total,
        'unpaid_orders': unpaid_orders,
        'all_items': all_items,
        'is_all_served': is_all_served,
        'is_fully_paid': is_fully_paid,
        'has_active_cooking': has_active_cooking,
        'status_hash': status_hash,
    }
    return render(request, 'orders/session_live.html', context)


def session_payment_gateway_view(request, session_id):
    """
    Consolidated Payment Gateway for the Dining Session:
    - Calculates total unpaid balance for all orders in the session.
    - Prevents settlement until all active dishes have been served/delivered to the table.
    - Provides simulated UPI QR, Card, or Netbanking options.
    - On confirmation: marks all orders as Completed & Paid, records transaction, ends session, and unlocks the table!
    """
    session_obj = get_object_or_404(DiningSession, pk=session_id)

    # Don't allow customer to settle the bill unless all orders are delivered
    active_orders = session_obj.orders.exclude(status=Order.STATUS_CANCELLED)
    has_undelivered = active_orders.exclude(status__in=[Order.STATUS_SERVED, Order.STATUS_COMPLETED]).exists()
    if has_undelivered:
        messages.warning(request, "Your food is still being prepared or delivered! The bill can only be settled once all dishes have arrived at your table.")
        return redirect('orders:session_live_detail', session_id=session_obj.id)

    unpaid_orders = session_obj.orders.exclude(status=Order.STATUS_CANCELLED).filter(payment_status=Order.PAYMENT_STATUS_PENDING)
    amount_due = sum((o.total_amount for o in unpaid_orders), Decimal('0.00'))

    if amount_due <= 0:
        amount_due = session_obj.total_spent

    if request.method == 'POST':
        method_selected = request.POST.get('method', Payment.METHOD_ONLINE_UPI)
        txn_id = "TXN_SESS_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))

        with transaction.atomic():
            # Mark all non-cancelled orders as Completed & Paid upon bill settlement
            for ord_obj in session_obj.orders.exclude(status=Order.STATUS_CANCELLED):
                ord_obj.payment_status = Order.PAYMENT_STATUS_PAID
                ord_obj.status = Order.STATUS_COMPLETED
                ord_obj.save(update_fields=['payment_status', 'status'])

                payment, created = Payment.objects.get_or_create(
                    order=ord_obj,
                    defaults={'amount': ord_obj.total_amount, 'status': Payment.STATUS_PAID, 'method': method_selected, 'transaction_id': txn_id}
                )
                if not created and payment.status != Payment.STATUS_PAID:
                    payment.status = Payment.STATUS_PAID
                    payment.method = method_selected
                    if not payment.transaction_id:
                        payment.transaction_id = txn_id
                    payment.save()

            session_obj.update_totals()
            session_obj.end_session()

        messages.success(request, f"Consolidated bill of ₹{amount_due} settled successfully! Table {session_obj.table_number} is now released.")
        return redirect('orders:session_live_detail', session_id=session_obj.id)

    return render(request, 'orders/session_payment.html', {
        'session': session_obj,
        'amount_due': amount_due,
        'unpaid_orders': unpaid_orders,
        'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', '')
    })


def session_invoice_view(request, session_id):
    """Printable Consolidated Tax Invoice for all orders in a Dining Session."""
    session_obj = get_object_or_404(DiningSession.objects.prefetch_related('orders__items__menu_item'), pk=session_id)
    orders = session_obj.orders.exclude(status=Order.STATUS_CANCELLED).prefetch_related('items__menu_item', 'payment')
    
    all_items = []
    for ord_obj in orders:
        for itm in ord_obj.items.filter(is_cancelled=False):
            all_items.append(itm)

    subtotal = session_obj.subtotal_amount
    tax = session_obj.tax_sum
    total = session_obj.grand_total_amount

    # Collect distinct transaction IDs and all payments
    txn_ids = []
    payments = []
    for o in orders:
        if hasattr(o, 'payment') and o.payment.status == Payment.STATUS_PAID:
            payments.append(o.payment)
            ref = o.payment.transaction_id or f"PAY-{o.payment.id}"
            if ref not in txn_ids:
                txn_ids.append(ref)

    txn_id_str = ", ".join(txn_ids) if txn_ids else None
    combined_payments = session_obj.get_combined_payments(status=Payment.STATUS_PAID)

    return render(request, 'orders/session_invoice.html', {
        'session': session_obj,
        'orders': orders,
        'all_items': all_items,
        'subtotal': subtotal,
        'tax': tax,
        'cgst': session_obj.cgst_sum,
        'sgst': session_obj.sgst_sum,
        'total': total,
        'txn_id': txn_id_str,
        'txn_ids': txn_ids,
        'payments': payments,
        'combined_payments': combined_payments,
    })


def session_status_api(request, session_id):
    """Real-time live JSON status poller for customer live session screen."""
    session_obj = get_object_or_404(DiningSession, pk=session_id)
    orders = session_obj.orders.all().order_by('-order_date')
    active_orders = orders.exclude(status=Order.STATUS_CANCELLED)
    is_all_served = active_orders.exists() and all(o.status in [Order.STATUS_SERVED, Order.STATUS_COMPLETED] for o in active_orders)
    status_hash = "-".join(f"{o.id}:{o.status}:{o.payment_status}" for o in orders)

    return JsonResponse({
        'session_id': session_obj.id,
        'is_active': session_obj.is_active,
        'is_all_served': is_all_served,
        'status_hash': status_hash,
        'orders': [
            {
                'id': o.id,
                'status': o.status,
                'status_display': o.get_status_display(),
                'total_amount': float(o.total_amount),
                'can_cancel': o.can_customer_cancel,
                'items_count': o.items.filter(is_cancelled=False).count()
            } for o in orders
        ]
    })


@login_required
@require_POST
def order_cancel_customer_view(request, order_id):
    """
    Customer Full Order Cancellation:
    Allowed ONLY if order.status == 'Pending'.
    """
    order = get_object_or_404(Order, pk=order_id)

    if hasattr(request.user, 'customer_profile') and order.customer != request.user.customer_profile:
        messages.error(request, "Permission denied.")
        return redirect('menu:menu_list')

    if not order.can_customer_cancel:
        messages.error(
            request,
            "This order is already being prepared in the kitchen and cannot be cancelled by customer. "
            "Please ask restaurant staff for assistance."
        )
        if order.session:
            return redirect('orders:session_live_detail', session_id=order.session.id)
        return redirect('orders:order_live', order_id=order.id)

    with transaction.atomic():
        order.status = Order.STATUS_CANCELLED
        order.save(update_fields=['status'])

        order.items.update(is_cancelled=True)
        order.recalculate_totals()

        if hasattr(order, 'payment') and order.payment.status == Payment.STATUS_PENDING:
            order.payment.status = Payment.STATUS_FAILED
            order.payment.amount = Decimal('0.00')
            order.payment.save(update_fields=['status', 'amount'])

        if order.session:
            order.session.update_totals()
            if not order.session.orders.exclude(status=Order.STATUS_CANCELLED).exists():
                order.session.end_session()
        elif order.table and order.table.current_customer == order.customer:
            order.table.release_lock()

    messages.info(request, f"Order #{order.id} has been cancelled.")
    if order.session:
        return redirect('orders:session_live_detail', session_id=order.session.id)
    return redirect('orders:order_live', order_id=order.id)


@login_required
@require_POST
def order_item_cancel_customer_view(request, order_id, item_id):
    """
    Customer Partial Cancellation: Cancel or remove an individual line item.
    Allowed ONLY if order.status == 'Pending'.
    """
    order = get_object_or_404(Order, pk=order_id)
    order_item = get_object_or_404(OrderItem, pk=item_id, order=order)

    if hasattr(request.user, 'customer_profile') and order.customer != request.user.customer_profile:
        messages.error(request, "Permission denied.")
        return redirect('menu:menu_list')

    if not order.can_customer_cancel:
        messages.error(request, "Items cannot be removed once the order has begun preparing in the kitchen.")
        if order.session:
            return redirect('orders:session_live_detail', session_id=order.session.id)
        return redirect('orders:order_live', order_id=order.id)

    with transaction.atomic():
        order_item.is_cancelled = True
        order_item.save(update_fields=['is_cancelled'])
        order.recalculate_totals()

        if hasattr(order, 'payment') and order.payment.status == Payment.STATUS_PENDING:
            order.payment.amount = order.total_amount
            order.payment.save(update_fields=['amount'])

        # If all items cancelled, cancel order and release table lock
        if not order.items.filter(is_cancelled=False).exists():
            order.status = Order.STATUS_CANCELLED
            order.save(update_fields=['status'])
            if hasattr(order, 'payment'):
                order.payment.status = Payment.STATUS_FAILED
                order.payment.save(update_fields=['status'])

            if order.session:
                order.session.update_totals()
                if not order.session.orders.exclude(status=Order.STATUS_CANCELLED).exists():
                    order.session.end_session()
            elif order.table and order.table.current_customer == order.customer:
                order.table.release_lock()
            messages.info(request, "All items were cancelled. Order is now cancelled.")
        else:
            messages.success(request, f"Removed {order_item.menu_item.name} from Order #{order.id}.")

    if order.session:
        return redirect('orders:session_live_detail', session_id=order.session.id)
    return redirect('orders:order_live', order_id=order.id)


def my_orders_view(request):
    """
    Customer order history grouped session-wise with active session at top.
    Excludes sessions where customer never placed any orders.
    Retains sessions with cancelled orders for auditing and tracking.
    """
    if not request.user.is_authenticated or not hasattr(request.user, 'customer_profile'):
        return redirect('accounts:google_login')

    customer = request.user.customer_profile
    sessions = DiningSession.objects.filter(
        customer=customer,
        orders__isnull=False
    ).distinct().prefetch_related(
        'orders__items__menu_item',
        'orders__payment'
    ).order_by('-started_at')
    standalone_orders = Order.objects.filter(
        customer=customer,
        session__isnull=True
    ).prefetch_related('items__menu_item', 'payment').order_by('-order_date')

    return render(request, 'orders/my_orders.html', {
        'dining_sessions': sessions,
        'standalone_orders': standalone_orders
    })


def order_invoice_view(request, order_id):
    """Printable / Downloadable Digital Receipt / Invoice."""
    order = get_object_or_404(Order.objects.prefetch_related('items__menu_item'), pk=order_id)
    payment = getattr(order, 'payment', None)
    return render(request, 'orders/invoice.html', {'order': order, 'payment': payment})


def order_status_api(request, order_id):
    """Lightweight JSON API for real-time live status polling in JS."""
    order = get_object_or_404(Order, pk=order_id)
    return JsonResponse({
        'id': order.id,
        'status': order.status,
        'status_display': order.get_status_display(),
        'payment_status': order.payment_status,
        'total_amount': float(order.total_amount),
        'can_customer_cancel': order.can_customer_cancel,
    })


# ==============================================================================
# AJAX APIS FOR MODERN DYNAMIC FRONTEND (NO PAGE RELOAD)
# ==============================================================================

def api_my_active_order(request):
    """
    Returns the current active order / session summary for the logged-in customer.
    Powers the persistent LiveOrderBar across the entire website.
    Dynamically updates when dishes are cooking, served, or bill is pending settlement.
    """
    if not request.user.is_authenticated or not hasattr(request.user, 'customer_profile'):
        return JsonResponse({'has_active_order': False})

    customer = request.user.customer_profile

    # Priority 1: Check customer's active dining session
    active_session = DiningSession.objects.filter(customer=customer, is_active=True).first()
    if active_session:
        active_orders = active_session.orders.exclude(status=Order.STATUS_CANCELLED)
        if not active_orders.exists():
            return JsonResponse({'has_active_order': False})

        session_total = sum((o.total_amount for o in active_orders), Decimal('0.00'))

        # Check latest cooking order
        cooking_order = active_orders.filter(status__in=[Order.STATUS_PENDING, Order.STATUS_PREPARING, Order.STATUS_READY]).order_by('-order_date').first()
        if cooking_order:
            status_text = f"Round #{cooking_order.id} • {cooking_order.get_status_display()}"
            status_val = cooking_order.status
        else:
            # All dishes in the session are Served!
            status_text = "🍽️ Food Served — Enjoy your meal!"
            status_val = "Served"

        return JsonResponse({
            'has_active_order': True,
            'order_id': active_session.id,
            'status': status_val,
            'status_display': status_text,
            'table_number': active_session.table_number or 'Takeaway',
            'total_amount': float(session_total),
            'live_url': reverse('orders:session_live_detail', args=[active_session.id]),
        })

    # Priority 2: Standalone active order fallback (strictly for non-session orders, e.g. takeaway)
    order = Order.objects.filter(
        customer=customer,
        session__isnull=True,
        status__in=[Order.STATUS_PENDING, Order.STATUS_PREPARING, Order.STATUS_READY, Order.STATUS_SERVED]
    ).order_by('-order_date').first()

    if not order:
        return JsonResponse({'has_active_order': False})

    status_display = f"Order #{order.id} • {order.get_status_display()}" if order.status != Order.STATUS_SERVED else "🍽️ Food Served — Enjoy your meal!"

    return JsonResponse({
        'has_active_order': True,
        'order_id': order.id,
        'status': order.status,
        'status_display': status_display,
        'table_number': order.table_number or 'Takeaway',
        'total_amount': float(order.total_amount),
        'items_count': order.items.filter(is_cancelled=False).count(),
        'payment_status': order.payment_status,
        'live_url': reverse('orders:order_live', args=[order.id]),
    })


@require_POST
def api_cart_add(request, item_id):
    """Adds item to session cart via AJAX and returns updated count without page reload."""
    item = get_object_or_404(MenuItem, pk=item_id, is_available=True)
    cart = request.session.get('cart', {})
    item_str = str(item_id)
    cart[item_str] = cart.get(item_str, 0) + 1
    request.session['cart'] = cart
    request.session.modified = True
    cart_count = sum(cart.values())
    return JsonResponse({
        'success': True,
        'cart_count': cart_count,
        'item_id': item.id,
        'item_qty': cart[item_str],
        'item_name': item.name,
    })


@require_POST
def api_cart_update(request, item_id):
    """Adjusts item quantity (+/-) via AJAX."""
    action = request.POST.get('action')
    cart = request.session.get('cart', {})
    item_str = str(item_id)

    if action == 'increase':
        cart[item_str] = cart.get(item_str, 0) + 1
    elif action == 'decrease':
        if item_str in cart:
            if cart[item_str] > 1:
                cart[item_str] -= 1
            else:
                del cart[item_str]

    request.session['cart'] = cart
    request.session.modified = True
    cart_count = sum(cart.values())
    new_qty = cart.get(item_str, 0)

    return JsonResponse({
        'success': True,
        'cart_count': cart_count,
        'item_id': item_id,
        'item_qty': new_qty,
    })


@require_POST
def api_call_waiter(request):
    """
    Submits a waiter assistance call from table.
    STRICT REQUIREMENT: Allowed ONLY by the authenticated customer who holds the active lock for that table.
    """
    if not request.user.is_authenticated or not hasattr(request.user, 'customer_profile'):
        return JsonResponse({
            'success': False,
            'error': 'Please log in to request staff assistance.'
        }, status=401)

    customer = request.user.customer_profile
    table_num = request.session.get('table_id')

    if not table_num:
        locked_table = customer.locked_tables.filter(is_locked=True).first()
        if locked_table:
            table_num = locked_table.table_number
        else:
            return JsonResponse({
                'success': False,
                'error': 'You do not have an active table lock. Staff assistance is reserved for seated diners.'
            }, status=400)

    table_obj = RestaurantTable.objects.filter(table_number__iexact=str(table_num).strip()).first()
    if not table_obj:
        return JsonResponse({
            'success': False,
            'error': f"Table {table_num} was not found."
        }, status=404)

    # Only allow the user locked for that table
    if not table_obj.is_locked or table_obj.current_customer != customer:
        return JsonResponse({
            'success': False,
            'error': f"Only the diner holding the active lock for Table {table_obj.table_number} can call staff."
        }, status=403)

    message = request.POST.get('message', 'Assistance requested at table').strip()
    WaiterAlert.objects.create(
        table=table_obj,
        table_number=table_obj.table_number,
        customer=customer,
        message=message or 'Service assistance requested'
    )
    return JsonResponse({
        'success': True,
        'message': f"Staff has been notified for Table {table_obj.table_number} and is on the way!"
    })


@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
def api_waiter_alerts(request):
    """Polls pending waiter alerts for Waiter dashboard."""
    alerts = WaiterAlert.objects.filter(is_resolved=False).order_by('-created_at')[:10]
    alerts_data = [{
        'id': a.id,
        'table_number': a.table_number,
        'message': a.message,
        'customer_name': a.customer.name if a.customer else 'Guest',
        'time': a.created_at.strftime('%I:%M %p')
    } for a in alerts]
    return JsonResponse({'alerts': alerts_data, 'count': len(alerts_data)})


@login_required
@staff_role_required([StaffProfile.ROLE_WAITER, StaffProfile.ROLE_MANAGER])
@require_POST
def api_resolve_waiter_alert(request, alert_id):
    """Marks a waiter alert as resolved."""
    alert = get_object_or_404(WaiterAlert, pk=alert_id)
    alert.is_resolved = True
    alert.resolved_by = request.user
    alert.save(update_fields=['is_resolved', 'resolved_by'])
    return JsonResponse({'success': True})


def api_tables_status(request):
    """
    Returns real-time status of all active dining tables.
    Called dynamically whenever the customer opens the table selection modal,
    ensuring live occupancy/lock status without stale page data.
    """
    current_customer = request.user.customer_profile if request.user.is_authenticated and hasattr(request.user, 'customer_profile') else None
    current_table_num = request.session.get('table_id')

    tables = RestaurantTable.objects.filter(is_active=True).order_by('table_number')
    tables_data = []

    for tbl in tables:
        is_locked_by_me = bool(tbl.is_locked and current_customer and tbl.current_customer == current_customer)
        is_locked_by_other = bool(tbl.is_locked and not is_locked_by_me)
        can_select = not is_locked_by_other

        tables_data.append({
            'id': tbl.id,
            'table_number': tbl.table_number,
            'capacity': tbl.capacity,
            'is_locked': tbl.is_locked,
            'is_locked_by_me': is_locked_by_me,
            'is_locked_by_other': is_locked_by_other,
            'can_select': can_select,
            'status_label': 'Occupied' if is_locked_by_other else ('My Table' if is_locked_by_me else 'Free'),
            'is_current': bool(current_table_num and current_table_num.upper() == tbl.table_number.upper()),
        })

    return JsonResponse({
        'success': True,
        'tables': tables_data,
        'current_table_number': current_table_num or '',
    })


def get_razorpay_client():
    """Initializes and returns an authenticated Razorpay Client."""
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not key_id or not key_secret:
        raise ValueError("Razorpay credentials not configured in settings/environment.")
    return razorpay.Client(auth=(key_id, key_secret))


@csrf_exempt
@require_POST
def razorpay_create_order_view(request):
    """
    Razorpay Standard Web Checkout - Step 1: Create Order
    Endpoint: POST /api/create-order/ or /api/razorpay/create-order/
    - Accepts JSON payload or form-encoded POST
    - Request: { amount (paise or INR), currency, receipt, order_id, session_id }
    - Minimum amount: 100 paise (₹1.00)
    - Calls Razorpay API: POST https://api.razorpay.com/v1/orders
    - Returns JSON: { 'success': True, 'order_id': rzp_order_id, 'amount': paise, 'currency': 'INR', 'key_id': KEY_ID }
    """
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST
    except Exception:
        data = request.POST

    session_id = data.get('session_id')
    order_id = data.get('order_id')
    raw_amount = data.get('amount')
    currency = data.get('currency', 'INR')

    restaurant = Restaurant.objects.first()
    rest_name = restaurant.name if restaurant else "Spice Garden"
    description = "Restaurant Dining Bill"
    prefill = {
        'name': '',
        'email': '',
        'contact': ''
    }

    amount_paise = 0
    receipt = f"rcpt_{int(timezone.now().timestamp())}"

    if session_id:
        try:
            session_obj = DiningSession.objects.get(pk=session_id)
        except DiningSession.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Dining Session #{session_id} not found.'}, status=404)

        if not session_obj.is_active:
            return JsonResponse({'success': False, 'error': 'This dining session is already settled and closed.'}, status=400)

        # Check for undelivered food
        active_orders = session_obj.orders.exclude(status=Order.STATUS_CANCELLED)
        has_undelivered = active_orders.exclude(status__in=[Order.STATUS_SERVED, Order.STATUS_COMPLETED]).exists()
        if has_undelivered:
            return JsonResponse({
                'success': False,
                'error': 'Food is still being prepared or delivered! The bill can only be settled once all dishes have arrived at your table.'
            }, status=400)

        unpaid_orders = active_orders.filter(payment_status=Order.PAYMENT_STATUS_PENDING)
        if not unpaid_orders.exists():
            return JsonResponse({'success': False, 'error': 'All orders in this dining session are already settled.'}, status=400)
        amount_due = sum((o.total_amount for o in unpaid_orders), Decimal('0.00'))
        if amount_due <= 0:
            amount_due = session_obj.total_spent
        amount_paise = int(amount_due * 100)
        receipt = f"sess_{session_obj.id}_{int(timezone.now().timestamp())}"[:40]
        description = f"Dining Session #{session_obj.id} (Table {session_obj.table_number})"
        if session_obj.customer and session_obj.customer.user:
            prefill['name'] = session_obj.customer.user.get_full_name() or session_obj.customer.user.username
            prefill['email'] = session_obj.customer.user.email
            prefill['contact'] = getattr(session_obj.customer, 'phone', '')

    elif order_id:
        try:
            order_obj = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Order #{order_id} not found.'}, status=404)

        if order_obj.payment_status == Order.PAYMENT_STATUS_PAID:
            return JsonResponse({'success': False, 'error': f'Order #{order_id} is already settled.'}, status=400)

        if order_obj.table and order_obj.status not in [Order.STATUS_SERVED, Order.STATUS_COMPLETED]:
            return JsonResponse({
                'success': False,
                'error': 'This order cannot be settled yet. Food must be delivered to your table before payment.'
            }, status=400)

        amount_paise = int(order_obj.total_amount * 100)
        receipt = f"ord_{order_obj.id}_{int(timezone.now().timestamp())}"[:40]
        description = f"Order #{order_obj.id} ({order_obj.table_number or 'Takeaway'})"
        if order_obj.customer and order_obj.customer.user:
            prefill['name'] = order_obj.customer.user.get_full_name() or order_obj.customer.user.username
            prefill['email'] = order_obj.customer.user.email
            prefill['contact'] = getattr(order_obj.customer, 'phone', '')

    elif raw_amount is not None:
        try:
            val = float(raw_amount)
            if data.get('is_paise') or (val >= 100 and val == int(val) and '.' not in str(raw_amount)):
                amount_paise = int(val)
            else:
                amount_paise = int(val * 100)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid amount parameter.'}, status=400)
    else:
        return JsonResponse({'success': False, 'error': 'Either session_id, order_id, or amount parameter is required.'}, status=400)

    # Validate minimum amount: 100 paise (₹1.00)
    if amount_paise < 100:
        return JsonResponse({
            'success': False,
            'error': f'Amount must be at least 100 paise (₹1.00). Received {amount_paise} paise.'
        }, status=400)

    try:
        client = get_razorpay_client()
        order_params = {
            'amount': amount_paise,
            'currency': currency,
            'receipt': receipt,
            'payment_capture': 1,
            'notes': {
                'description': description,
                'session_id': str(session_id) if session_id else '',
                'order_id': str(order_id) if order_id else ''
            }
        }
        razorpay_order = client.order.create(data=order_params)
        return JsonResponse({
            'success': True,
            'order_id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
            'name': rest_name,
            'description': description,
            'prefill': prefill
        })
    except razorpay.errors.AuthenticationError:
        return JsonResponse({'success': False, 'error': 'Razorpay authentication failed. Check API keys.'}, status=401)
    except razorpay.errors.BadRequestError as e:
        return JsonResponse({'success': False, 'error': f'Razorpay Bad Request: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Failed to create Razorpay order: {str(e)}'}, status=500)


@csrf_exempt
@require_POST
def razorpay_verify_payment_view(request):
    """
    Razorpay Standard Web Checkout - Step 3: Verify Signature
    Endpoint: POST /api/verify-payment/ or /api/razorpay/verify-payment/
    - Receives razorpay_payment_id, razorpay_order_id, razorpay_signature
    - Algorithm: HMAC-SHA256(order_id + "|" + payment_id, KEY_SECRET)
    - Compares generated signature with razorpay_signature
    - Return success only if signatures match
    - Signature mismatch: returns 400, does NOT mark as paid
    - Missing fields: returns 400
    """
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST
    except Exception:
        data = request.POST

    payment_id = data.get('razorpay_payment_id')
    order_id = data.get('razorpay_order_id')
    signature = data.get('razorpay_signature')
    session_id = data.get('session_id')
    internal_order_id = data.get('order_id')

    # Missing fields check
    if not (payment_id and order_id and signature):
        return JsonResponse({
            'success': False,
            'error': 'Missing required fields. razorpay_payment_id, razorpay_order_id, and razorpay_signature are all mandatory.'
        }, status=400)

    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not key_secret:
        return JsonResponse({'success': False, 'error': 'Razorpay secret key not configured on server.'}, status=500)

    # 1. Verify HMAC-SHA256 Signature
    msg = f"{order_id}|{payment_id}"
    generated_signature = hmac.new(
        key_secret.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(generated_signature, signature):
        return JsonResponse({
            'success': False,
            'error': 'Payment signature mismatch! Potential security tampering detected.'
        }, status=400)

    # 2. Verify with Razorpay SDK utility as additional security validation
    try:
        client = get_razorpay_client()
        client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Signature verification failed: {str(e)}'}, status=400)

    # 3. Signature matched! Update DB atomically
    redirect_url = reverse('menu:menu_list')

    if session_id:
        try:
            session_obj = DiningSession.objects.get(pk=session_id)
            with transaction.atomic():
                for ord_obj in session_obj.orders.exclude(status=Order.STATUS_CANCELLED):
                    ord_obj.payment_status = Order.PAYMENT_STATUS_PAID
                    ord_obj.status = Order.STATUS_COMPLETED
                    ord_obj.save(update_fields=['payment_status', 'status'])

                    payment, created = Payment.objects.get_or_create(
                        order=ord_obj,
                        defaults={
                            'amount': ord_obj.total_amount,
                            'status': Payment.STATUS_PAID,
                            'method': Payment.METHOD_ONLINE_RAZORPAY,
                            'transaction_id': payment_id
                        }
                    )
                    if not created:
                        payment.status = Payment.STATUS_PAID
                        payment.method = Payment.METHOD_ONLINE_RAZORPAY
                        payment.transaction_id = payment_id
                        payment.save()

                session_obj.update_totals()
                session_obj.end_session()

            messages.success(request, f"Payment of ₹{session_obj.total_spent} verified successfully via Razorpay! Ref: {payment_id}")
            redirect_url = reverse('orders:session_invoice', args=[session_obj.id])
        except DiningSession.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Dining Session #{session_id} not found.'}, status=404)

    elif internal_order_id:
        try:
            ord_obj = Order.objects.get(pk=internal_order_id)
            with transaction.atomic():
                payment, created = Payment.objects.get_or_create(
                    order=ord_obj,
                    defaults={
                        'amount': ord_obj.total_amount,
                        'status': Payment.STATUS_PAID,
                        'method': Payment.METHOD_ONLINE_RAZORPAY,
                        'transaction_id': payment_id
                    }
                )
                if not created:
                    payment.status = Payment.STATUS_PAID
                    payment.method = Payment.METHOD_ONLINE_RAZORPAY
                    payment.transaction_id = payment_id
                    payment.save()

                ord_obj.payment_status = Order.PAYMENT_STATUS_PAID
                ord_obj.status = Order.STATUS_COMPLETED
                ord_obj.save(update_fields=['payment_status', 'status'])

                if ord_obj.session:
                    ord_obj.session.update_totals()
                    unsettled = ord_obj.session.orders.filter(payment_status=Order.PAYMENT_STATUS_PENDING).exclude(pk=ord_obj.pk).exists()
                    if not unsettled:
                        for s_ord in ord_obj.session.orders.exclude(status=Order.STATUS_CANCELLED):
                            s_ord.status = Order.STATUS_COMPLETED
                            s_ord.save(update_fields=['status'])
                        ord_obj.session.end_session()
                elif ord_obj.table:
                    ord_obj.table.release_lock()

            messages.success(request, f"Payment of ₹{ord_obj.total_amount} verified successfully via Razorpay! Ref: {payment_id}")
            redirect_url = reverse('orders:order_invoice', args=[ord_obj.id])
        except Order.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Order #{internal_order_id} not found.'}, status=404)

    return JsonResponse({
        'success': True,
        'message': 'Payment signature verified successfully.',
        'payment_id': payment_id,
        'order_id': order_id,
        'redirect_url': redirect_url
    })

