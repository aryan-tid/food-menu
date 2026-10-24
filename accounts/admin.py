from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum
from .models import Customer, StaffProfile


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_avatar', 'name_display', 'email', 'phone', 'orders_count', 'total_spent_display', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email', 'phone', 'address')
    list_filter = ('created_at',)
    readonly_fields = ('created_at', 'customer_avatar')

    def customer_avatar(self, obj):
        url = obj.avatar_url or f"https://ui-avatars.com/api/?name={obj.name}&background=f59e0b&color=000&size=64"
        return format_html('<img src="{}" style="width: 28px; height: 28px; border-radius: 50%; object-fit: cover;" />', url)
    customer_avatar.short_description = "Avatar"

    def name_display(self, obj):
        return format_html('<strong>{}</strong>', obj.name)
    name_display.short_description = "Customer Name"

    def orders_count(self, obj):
        count = obj.orders.count()
        return format_html('<span class="badge-pill badge-primary">{} orders</span>', count)
    orders_count.short_description = "Total Orders"

    def total_spent_display(self, obj):
        total = obj.orders.filter(payment_status='Paid').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        return format_html('<strong>₹{}</strong>', total)
    total_spent_display.short_description = "Lifetime Spent"


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_display', 'role', 'phone', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone')
    list_editable = ('role',)

    def user_display(self, obj):
        full_name = obj.user.get_full_name()
        display_name = f"{full_name} ({obj.user.username})" if full_name else obj.user.username
        return format_html('<strong>{}</strong>', display_name)
    user_display.short_description = "Staff Member"

    def role_badge(self, obj):
        if obj.role == StaffProfile.ROLE_MANAGER:
            return format_html('<span class="badge-pill badge-dark"><i class="bi bi-shield-fill text-warning"></i> Manager</span>')
        elif obj.role == StaffProfile.ROLE_KITCHEN:
            return format_html('<span class="badge-pill badge-warning"><i class="bi bi-fire"></i> Chef (KDS)</span>')
        return format_html('<span class="badge-pill badge-success"><i class="bi bi-person-badge"></i> Waiter (Floor)</span>')
    role_badge.short_description = "Role"
