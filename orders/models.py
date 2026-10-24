import io
import base64
import qrcode
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from accounts.models import Customer
from menu.models import MenuItem


class RestaurantTable(models.Model):
    """
    RestaurantTable entity representing dining tables in the restaurant.
    Features:
    - Table-specific static QR code generation.
    - Temporary Concurrency Session Lock: When an active order is placed,
      the table is locked to that customer until the bill is settled or unlocked by staff.
    """
    table_number = models.CharField(max_length=20, unique=True, help_text="e.g. T-01, T-02, VIP-1")
    capacity = models.PositiveIntegerField(default=4)
    is_active = models.BooleanField(default=True, db_index=True, help_text="Table is available for service")
    is_locked = models.BooleanField(default=False, db_index=True, help_text="True when occupied by an active ordering customer")
    current_customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_tables',
        help_text="Customer holding the active table lock"
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'restaurant_table'
        verbose_name = 'Restaurant Table'
        verbose_name_plural = 'Restaurant Tables'
        ordering = ['table_number']

    def __str__(self):
        status = f"Locked ({self.current_customer.name})" if self.is_locked and self.current_customer else "Free"
        return f"Table {self.table_number} [{status}]"

    def lock_for(self, customer):
        """Locks the table for an ordering customer."""
        self.is_locked = True
        self.current_customer = customer
        self.locked_at = timezone.now()
        self.save(update_fields=['is_locked', 'current_customer', 'locked_at'])

    def release_lock(self):
        """Releases the table lock so future guests can order."""
        self.is_locked = False
        self.current_customer = None
        self.locked_at = None
        self.save(update_fields=['is_locked', 'current_customer', 'locked_at'])

    def generate_qr_base64(self, host_url="http://127.0.0.1:8000"):
        """Generates a Base64-encoded QR code PNG pointing to the table's digital menu."""
        menu_url = f"{host_url}/menu/?table={self.table_number}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(menu_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1e293b", back_color="#ffffff")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{encoded}"


class DiningSession(models.Model):
    """
    Groups multiple orders from the same customer into a single dining session.
    A table remains locked for the duration of this active session.
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='dining_sessions')
    table = models.ForeignKey(RestaurantTable, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    table_number = models.CharField(max_length=20, blank=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        db_table = 'dining_session'
        verbose_name = 'Dining Session'
        verbose_name_plural = 'Dining Sessions'
        ordering = ['-started_at']

    def __str__(self):
        status = "Active" if self.is_active else "Ended"
        return f"Session #{self.id} - Table {self.table_number or 'Takeaway'} - {self.customer.name} [{status}]"

    def update_totals(self):
        """Updates total spent in this session by summing all non-cancelled orders."""
        orders = self.orders.exclude(status=Order.STATUS_CANCELLED)
        total = sum((order.total_amount for order in orders), Decimal('0.00'))
        self.total_spent = total
        self.save(update_fields=['total_spent'])
        return self.total_spent

    @property
    def active_orders_qs(self):
        """Returns non-cancelled orders belonging to this session."""
        return self.orders.exclude(status=Order.STATUS_CANCELLED)

    @property
    def subtotal_amount(self):
        """Consolidated subtotal of all active orders in this session."""
        return sum((o.subtotal for o in self.active_orders_qs), Decimal('0.00'))

    @property
    def tax_sum(self):
        """Consolidated 5% GST tax of all active orders."""
        return sum((o.tax_amount for o in self.active_orders_qs), Decimal('0.00'))

    @property
    def cgst_sum(self):
        """Central GST (2.5%)."""
        return round(self.tax_sum / Decimal('2.0'), 2)

    @property
    def sgst_sum(self):
        """State GST (2.5%)."""
        return round(self.tax_sum / Decimal('2.0'), 2)

    @property
    def grand_total_amount(self):
        """Consolidated grand total of all active orders."""
        return sum((o.total_amount for o in self.active_orders_qs), Decimal('0.00'))

    @property
    def unpaid_orders_qs(self):
        """Unpaid active orders."""
        return self.active_orders_qs.filter(payment_status=Order.PAYMENT_STATUS_PENDING)

    @property
    def unpaid_total_amount(self):
        """Total pending payment in this session."""
        return sum((o.total_amount for o in self.unpaid_orders_qs), Decimal('0.00'))

    @property
    def paid_total_amount(self):
        """Total paid amount settled in this session."""
        paid_orders = self.active_orders_qs.filter(payment_status=Order.PAYMENT_STATUS_PAID)
        return sum((o.total_amount for o in paid_orders), Decimal('0.00'))

    def end_session(self):
        """Closes the dining session and releases table lock if applicable."""
        self.is_active = False
        self.ended_at = timezone.now()
        self.update_totals()
        self.save(update_fields=['is_active', 'ended_at'])
        if self.table:
            if self.table.current_customer == self.customer or not self.table.current_customer:
                self.table.release_lock()

    @property
    def payments_list(self):
        """Returns all payments across all orders in this session."""
        return Payment.objects.filter(order__session=self).select_related('order', 'collected_by').order_by('payment_date')

    @property
    def paid_payments(self):
        """Returns all paid payments in this session."""
        return self.payments_list.filter(status=Payment.STATUS_PAID)

    @property
    def distinct_transaction_ids(self):
        """Returns list of distinct transaction/payment references recorded in this session."""
        txns = []
        for p in self.paid_payments:
            val = p.transaction_id or f"PAY-{p.id}"
            if val not in txns:
                txns.append(val)
        return txns

    @property
    def duration_display(self):
        end = self.ended_at or timezone.now()
        diff = end - self.started_at
        minutes = max(1, int(diff.total_seconds() // 60))
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        rem_min = minutes % 60
        return f"{hours}h {rem_min}m"

    def get_combined_payments(self, status=None):
        """
        Groups payments by settlement batch / transaction_id into clean, distinct receipts.
        Eliminates duplicate payment rows when multiple orders are settled together.
        Clearly distinguishes multi-installment settlements (e.g. Rounds 1-3 settled first, Rounds 4-5 settled later).
        """
        orders_qs = self.orders.all().order_by('order_date', 'id')
        orders_map = {o.id: o for o in orders_qs}

        # Assign round numbers based on chronological order placement
        round_map = {ord_id: idx for idx, ord_id in enumerate(orders_map.keys(), start=1)}

        qs = self.payments_list
        if status:
            qs = qs.filter(status=status)

        payments = list(qs)
        if not payments:
            return []

        grouped = {}
        for p in payments:
            group_key = p.transaction_id.strip() if p.transaction_id and p.transaction_id.strip() else f"PAY_{p.id}"
            if group_key not in grouped:
                grouped[group_key] = []
            grouped[group_key].append(p)

        combined = []
        for idx, (grp_key, p_list) in enumerate(grouped.items(), start=1):
            total_amount = sum((p.amount for p in p_list), Decimal('0.00'))
            primary_p = p_list[0]

            covered_orders = []
            for p in p_list:
                ord_obj = orders_map.get(p.order_id, p.order)
                round_num = round_map.get(ord_obj.id, 1)
                items_summary = ", ".join([f"{it.quantity}x {it.menu_item.name}" for it in ord_obj.items.all()])
                covered_orders.append({
                    'order': ord_obj,
                    'round_number': round_num,
                    'order_id': ord_obj.id,
                    'amount': p.amount,
                    'items_summary': items_summary or f"Order #{ord_obj.id}",
                })

            round_numbers = [str(co['round_number']) for co in covered_orders]
            order_ids = [f"#{co['order_id']}" for co in covered_orders]
            if len(covered_orders) > 1:
                orders_label = f"Rounds {', '.join(round_numbers)} ({', '.join(order_ids)})"
            else:
                orders_label = f"Round {round_numbers[0]} ({order_ids[0]})"

            all_paid = all(p.status == 'Paid' for p in p_list)
            resolved_status = 'Paid' if all_paid else primary_p.status

            combined.append({
                'receipt_index': idx,
                'receipt_number': f"RCP-SESS-{self.id}-{idx}",
                'transaction_id': primary_p.transaction_id or grp_key,
                'method': primary_p.method,
                'method_display': primary_p.short_method_display,
                'total_amount': total_amount,
                'status': resolved_status,
                'payment_date': primary_p.payment_date,
                'collected_by': primary_p.collected_by,
                'covered_orders': covered_orders,
                'orders_label': orders_label,
                'payments_count': len(p_list),
            })

        return combined


class Order(models.Model):
    """
    Order entity corresponding to ER Diagram:
    Attributes: order_id (PK), customer (FK), table, order_date, total_amount, status
    Fulfillment types: Dine-In (Table locked) and Takeaway
    """
    STATUS_PENDING = 'Pending'
    STATUS_PREPARING = 'Preparing'
    STATUS_READY = 'Ready'
    STATUS_SERVED = 'Served'
    STATUS_COMPLETED = 'Completed'
    STATUS_CANCELLED = 'Cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending (Kitchen Queued)'),
        (STATUS_PREPARING, 'Preparing in Kitchen'),
        (STATUS_READY, 'Ready to Serve / Pickup'),
        (STATUS_SERVED, 'Served to Table'),
        (STATUS_COMPLETED, 'Completed & Settled'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    ORDER_TYPE_DINE_IN = 'Dine-In'
    ORDER_TYPE_TAKEAWAY = 'Takeaway'

    ORDER_TYPE_CHOICES = [
        (ORDER_TYPE_DINE_IN, 'Dine-In (At Table)'),
        (ORDER_TYPE_TAKEAWAY, 'Takeaway (Self-Pickup)'),
    ]

    PAYMENT_METHOD_PAY_LATER = 'PAY_LATER'
    PAYMENT_METHOD_ONLINE = 'ONLINE'

    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_METHOD_PAY_LATER, 'Pay After Dining (Cash / Reception)'),
        (PAYMENT_METHOD_ONLINE, 'Pay Online Now (UPI / Card)'),
    ]

    PAYMENT_STATUS_PENDING = 'Pending'
    PAYMENT_STATUS_PAID = 'Paid'

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_PENDING, 'Pending'),
        (PAYMENT_STATUS_PAID, 'Paid'),
    ]

    session = models.ForeignKey(DiningSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    table = models.ForeignKey(RestaurantTable, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    table_number = models.CharField(max_length=20, blank=True, help_text="Stored snapshot of table number")
    order_date = models.DateTimeField(auto_now_add=True, db_index=True)
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="5% GST")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default=ORDER_TYPE_DINE_IN)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default=PAYMENT_METHOD_PAY_LATER)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_PENDING, db_index=True)
    
    special_instructions = models.TextField(blank=True, help_text="Cooking notes or allergy requests")

    class Meta:
        db_table = 'order'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-order_date']

    def __str__(self):
        return f"Order #{self.id} - Table {self.table_number or 'Takeaway'} - {self.customer.name} [{self.status}]"

    @property
    def can_customer_cancel(self):
        """
        Customer rule:
        Can only cancel if order is still Pending.
        Once it is in Preparing or later, only staff can cancel.
        """
        return self.status == self.STATUS_PENDING and self.payment_status != self.PAYMENT_STATUS_PAID

    @property
    def cgst_amount(self):
        """Central GST (2.5%)."""
        return round(self.tax_amount / Decimal('2.0'), 2)

    @property
    def sgst_amount(self):
        """State GST (2.5%)."""
        return round(self.tax_amount / Decimal('2.0'), 2)

    def recalculate_totals(self):
        """Calculates active items subtotal, 5% GST tax, and total amount."""
        active_items = self.items.filter(is_cancelled=False)
        subtotal = sum((item.subtotal for item in active_items), Decimal('0.00')) if active_items.exists() else Decimal('0.00')
        tax = round(subtotal * Decimal('0.05'), 2)
        self.subtotal = subtotal
        self.tax_amount = tax
        self.total_amount = subtotal + tax
        self.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])
        if self.session:
            self.session.update_totals()
        return self.total_amount


class OrderItem(models.Model):
    """
    OrderItem entity corresponding to ER Diagram:
    Attributes: order_item_id (PK), order (FK), menu_item (FK), quantity, price
    Supports partial item-level cancellation.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='order_items')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=8, decimal_places=2, help_text="Historical price at order time")
    is_cancelled = models.BooleanField(default=False, help_text="True if item was cancelled")

    class Meta:
        db_table = 'order_item'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def __str__(self):
        status = " [CANCELLED]" if self.is_cancelled else ""
        return f"{self.quantity}x {self.menu_item.name} (Order #{self.order.id}){status}"

    @property
    def subtotal(self):
        if self.is_cancelled:
            return Decimal('0.00')
        return self.price * self.quantity


class Payment(models.Model):
    """
    Payment entity corresponding to ER Diagram:
    Attributes: payment_id (PK), order (1-to-1), method, amount, payment_date, status, transaction_id
    """
    METHOD_CASH_COUNTER = 'CASH_COUNTER'
    METHOD_ONLINE_UPI = 'ONLINE_UPI'
    METHOD_ONLINE_CARD = 'ONLINE_CARD'

    METHOD_CHOICES = [
        (METHOD_CASH_COUNTER, 'Cash at Counter / Reception'),
        (METHOD_ONLINE_UPI, 'Online UPI (GPay / PhonePe / Paytm)'),
        (METHOD_ONLINE_CARD, 'Credit / Debit Card'),
    ]

    STATUS_PENDING = 'Pending'
    STATUS_PAID = 'Paid'
    STATUS_FAILED = 'Failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    method = models.CharField(max_length=30, choices=METHOD_CHOICES, default=METHOD_CASH_COUNTER)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    collected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='collected_payments')

    class Meta:
        db_table = 'payment'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self):
        return f"Payment #{self.id} - Order #{self.order.id} [{self.status}] - ₹{self.amount}"

    @property
    def short_method_display(self):
        if self.method == self.METHOD_ONLINE_UPI:
            return 'UPI'
        elif self.method == self.METHOD_CASH_COUNTER:
            return 'Cash'
        elif self.method == self.METHOD_ONLINE_CARD:
            return 'Card'
        return self.get_method_display()


class WaiterAlert(models.Model):
    """
    Alert triggered when a customer clicks 'Call Waiter' from the digital menu.
    """
    table = models.ForeignKey(RestaurantTable, on_delete=models.CASCADE, related_name='waiter_alerts', null=True, blank=True)
    table_number = models.CharField(max_length=20, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='waiter_alerts')
    message = models.CharField(max_length=150, default="Assistance / Service requested")
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_alerts')

    class Meta:
        db_table = 'waiter_alert'
        verbose_name = 'Waiter Alert'
        verbose_name_plural = 'Waiter Alerts'
        ordering = ['-created_at']

    def __str__(self):
        status = "Resolved" if self.is_resolved else "Pending"
        return f"Alert from Table {self.table_number}: {self.message} [{status}]"
