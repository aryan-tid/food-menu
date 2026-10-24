from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import RestaurantTable, Order, OrderItem, Payment, DiningSession, WaiterAlert


@admin.register(RestaurantTable)
class RestaurantTableAdmin(admin.ModelAdmin):
    list_display = ('table_number_display', 'capacity', 'is_active', 'lock_status_badge', 'current_customer', 'locked_at')
    list_filter = ('is_active', 'is_locked')
    search_fields = ('table_number', 'current_customer__user__username')
    actions = ['force_unlock_tables', 'mark_as_active', 'mark_as_inactive']

    def table_number_display(self, obj):
        return format_html('<strong>Table {}</strong>', obj.table_number)
    table_number_display.short_description = "Table"

    def lock_status_badge(self, obj):
        if obj.is_locked and obj.current_customer:
            return format_html(
                '<span class="badge-pill badge-danger"><i class="bi bi-lock-fill"></i> Locked ({})</span>',
                obj.current_customer.name
            )
        elif obj.is_locked:
            return format_html('<span class="badge-pill badge-danger"><i class="bi bi-lock-fill"></i> Locked</span>')
        return format_html('<span class="badge-pill badge-success"><i class="bi bi-unlock-fill"></i> Available</span>')
    lock_status_badge.short_description = "Lock Status"

    def force_unlock_tables(self, request, queryset):
        for table in queryset:
            table.release_lock()
        self.message_user(request, f"Successfully released locks for {queryset.count()} tables.")
    force_unlock_tables.short_description = "Force release session locks on selected tables"

    def mark_as_active(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"Marked {queryset.count()} tables as active for service.")
    mark_as_active.short_description = "Mark tables as active"

    def mark_as_inactive(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"Marked {queryset.count()} tables as inactive.")
    mark_as_inactive.short_description = "Mark tables as inactive"


@admin.register(DiningSession)
class DiningSessionAdmin(admin.ModelAdmin):
    list_display = ('session_display', 'customer_display', 'table_number', 'session_status_badge', 'orders_count', 'total_spent_display', 'started_at', 'ended_at')
    list_filter = ('is_active', 'started_at')
    search_fields = ('customer__user__username', 'customer__user__first_name', 'table_number')

    def session_display(self, obj):
        return format_html('<strong>Session #{}</strong>', obj.id)
    session_display.short_description = "Session"

    def customer_display(self, obj):
        return format_html('{}', obj.customer.name)
    customer_display.short_description = "Customer"

    def session_status_badge(self, obj):
        if obj.is_active:
            return format_html('<span class="badge-pill badge-warning"><i class="bi bi-clock-history"></i> Active Dining</span>')
        return format_html('<span class="badge-pill badge-success"><i class="bi bi-check2-circle"></i> Closed / Settled</span>')
    session_status_badge.short_description = "Session Status"

    def orders_count(self, obj):
        return format_html('<span class="badge-pill badge-dark">{} rounds</span>', obj.orders.count())
    orders_count.short_description = "Rounds"

    def total_spent_display(self, obj):
        return format_html('<strong>₹{}</strong>', obj.total_spent)
    total_spent_display.short_description = "Total Amount"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('price', 'subtotal')
    fields = ('menu_item', 'quantity', 'price', 'subtotal', 'is_cancelled')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_display', 'table_display', 'customer_display', 'status', 'payment_status', 'payment_method', 'total_display', 'order_date')
    list_filter = ('status', 'payment_status', 'payment_method', 'order_type', 'order_date')
    search_fields = ('id', 'customer__user__username', 'customer__user__first_name', 'table_number')
    inlines = [OrderItemInline]
    list_editable = ('status', 'payment_status')
    actions = ['mark_as_preparing', 'mark_as_ready', 'mark_as_served', 'mark_as_completed']

    def order_display(self, obj):
        return format_html('<strong>Order #{}</strong>', obj.id)
    order_display.short_description = "Order ID"

    def table_display(self, obj):
        label = f"Table {obj.table_number}" if obj.table_number and obj.table_number != 'Takeaway' else "Takeaway"
        return format_html('<span class="badge-pill badge-dark">{}</span>', label)
    table_display.short_description = "Location"

    def customer_display(self, obj):
        return obj.customer.name
    customer_display.short_description = "Customer"

    def status_badge(self, obj):
        colors = {
            Order.STATUS_PENDING: 'badge-warning',
            Order.STATUS_PREPARING: 'badge-primary',
            Order.STATUS_READY: 'badge-success',
            Order.STATUS_SERVED: 'badge-dark',
            Order.STATUS_COMPLETED: 'badge-success',
            Order.STATUS_CANCELLED: 'badge-danger',
        }
        cls = colors.get(obj.status, 'badge-dark')
        return format_html('<span class="badge-pill {}">{}</span>', cls, obj.get_status_display())
    status_badge.short_description = "Kitchen Status"

    def payment_status_badge(self, obj):
        if obj.payment_status == Order.PAYMENT_STATUS_PAID:
            return format_html('<span class="badge-pill badge-success"><i class="bi bi-check-circle-fill"></i> Paid</span>')
        return format_html('<span class="badge-pill badge-warning"><i class="bi bi-hourglass-split"></i> Pending</span>')
    payment_status_badge.short_description = "Bill Status"

    def total_display(self, obj):
        return format_html('<strong>₹{}</strong>', obj.total_amount)
    total_display.short_description = "Total"

    def mark_as_preparing(self, request, queryset):
        queryset.update(status=Order.STATUS_PREPARING)
        self.message_user(request, f"Updated {queryset.count()} orders to Preparing.")
    mark_as_preparing.short_description = "Kitchen: Mark as Preparing"

    def mark_as_ready(self, request, queryset):
        queryset.update(status=Order.STATUS_READY)
        self.message_user(request, f"Updated {queryset.count()} orders to Ready.")
    mark_as_ready.short_description = "Kitchen: Mark as Ready"

    def mark_as_served(self, request, queryset):
        queryset.update(status=Order.STATUS_SERVED)
        self.message_user(request, f"Updated {queryset.count()} orders to Served.")
    mark_as_served.short_description = "Floor: Mark as Served"

    def mark_as_completed(self, request, queryset):
        queryset.update(status=Order.STATUS_COMPLETED, payment_status=Order.PAYMENT_STATUS_PAID)
        self.message_user(request, f"Updated {queryset.count()} orders to Completed & Paid.")
    mark_as_completed.short_description = "Manager: Settle & Mark as Completed"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_link', 'menu_item', 'quantity', 'price', 'subtotal_display', 'is_cancelled')
    list_filter = ('is_cancelled', 'order__status')
    search_fields = ('order__id', 'menu_item__name')

    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">Order #{}</a>', url, obj.order.id)
    order_link.short_description = "Order"

    def subtotal_display(self, obj):
        return f"₹{obj.subtotal}"
    subtotal_display.short_description = "Subtotal"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_link', 'method', 'amount_display', 'status_badge', 'transaction_id', 'collected_by', 'payment_date')
    list_filter = ('method', 'status', 'payment_date')
    search_fields = ('transaction_id', 'order__id', 'order__customer__user__username')

    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">Order #{}</a>', url, obj.order.id)
    order_link.short_description = "Order"

    def amount_display(self, obj):
        return format_html('<strong>₹{}</strong>', obj.amount)
    amount_display.short_description = "Amount"

    def status_badge(self, obj):
        if obj.status == Payment.STATUS_PAID:
            return format_html('<span class="badge-pill badge-success"><i class="bi bi-check-all"></i> Paid</span>')
        elif obj.status == Payment.STATUS_FAILED:
            return format_html('<span class="badge-pill badge-danger">Failed</span>')
        return format_html('<span class="badge-pill badge-warning">Pending</span>')
    status_badge.short_description = "Status"


@admin.register(WaiterAlert)
class WaiterAlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'table_display', 'customer', 'message', 'status_badge', 'created_at', 'resolved_by')
    list_filter = ('is_resolved', 'created_at')
    search_fields = ('table_number', 'message', 'customer__user__username')
    actions = ['mark_as_resolved']

    def table_display(self, obj):
        return format_html('<span class="badge-pill badge-dark">Table {}</span>', obj.table_number or 'Floor')
    table_display.short_description = "Table"

    def status_badge(self, obj):
        if obj.is_resolved:
            return format_html('<span class="badge-pill badge-success"><i class="bi bi-check2"></i> Resolved</span>')
        return format_html('<span class="badge-pill badge-danger"><i class="bi bi-bell-fill"></i> Needs Waiter</span>')
    status_badge.short_description = "Alert State"

    def mark_as_resolved(self, request, queryset):
        queryset.update(is_resolved=True, resolved_by=request.user)
        self.message_user(request, f"Marked {queryset.count()} alerts as resolved.")
    mark_as_resolved.short_description = "Mark selected alerts as Resolved"
