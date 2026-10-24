from django.urls import path
from . import views, staff_views

app_name = 'orders'

urlpatterns = [
    # Customer Cart & Checkout
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:item_id>/', views.cart_add_view, name='cart_add'),
    path('cart/remove/<int:item_id>/', views.cart_remove_view, name='cart_remove'),
    path('cart/delete/<int:item_id>/', views.cart_delete_view, name='cart_delete'),
    path('cart/clear/', views.cart_clear_view, name='cart_clear'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('payment/<int:order_id>/', views.payment_gateway_view, name='payment_gateway'),
    path('order/<int:order_id>/live/', views.order_live_view, name='order_live'),
    path('order/<int:order_id>/cancel/', views.order_cancel_customer_view, name='order_cancel'),
    path('order/<int:order_id>/item/<int:item_id>/cancel/', views.order_item_cancel_customer_view, name='order_item_cancel'),
    path('order/<int:order_id>/invoice/', views.order_invoice_view, name='order_invoice'),
    path('order/<int:order_id>/api/status/', views.order_status_api, name='order_status_api'),
    
    # Consolidated Real-Time Dining Session Tracking & Payment
    path('session/live/', views.session_live_view, name='session_live'),
    path('session/<int:session_id>/live/', views.session_live_view, name='session_live_detail'),
    path('session/<int:session_id>/payment/', views.session_payment_gateway_view, name='session_payment_gateway'),
    path('session/<int:session_id>/invoice/', views.session_invoice_view, name='session_invoice'),
    path('session/<int:session_id>/api/status/', views.session_status_api, name='session_status_api'),

    # Backward-compatible routes for cached scripts or bookmarks
    path('orders/session/<int:session_id>/api/status/', views.session_status_api),
    path('orders/session/<int:session_id>/live/', views.session_live_view),
    path('orders/session/live/', views.session_live_view),
    path('orders/order/<int:order_id>/live/', views.order_live_view),
    path('orders/order/<int:order_id>/api/status/', views.order_status_api),
    path('orders/order/<int:order_id>/invoice/', views.order_invoice_view),
    path('orders/staff/kitchen/', staff_views.kitchen_dashboard_view),
    
    path('my-orders/', views.my_orders_view, name='my_orders'),

    # AJAX APIs for modern dynamic frontend
    path('api/tables/status/', views.api_tables_status, name='api_tables_status'),
    path('api/my-active-order/', views.api_my_active_order, name='api_my_active_order'),
    path('api/cart/add/<int:item_id>/', views.api_cart_add, name='api_cart_add'),
    path('api/cart/update/<int:item_id>/', views.api_cart_update, name='api_cart_update'),
    path('api/call-waiter/', views.api_call_waiter, name='api_call_waiter'),
    path('api/waiter-alerts/', views.api_waiter_alerts, name='api_waiter_alerts'),
    path('api/waiter-alerts/<int:alert_id>/resolve/', views.api_resolve_waiter_alert, name='api_resolve_waiter_alert'),

    # Staff Account Self-Service
    path('staff/change-password/', staff_views.staff_change_password_view, name='staff_change_password'),

    # Staff: Kitchen Dashboard
    path('staff/kitchen/', staff_views.kitchen_dashboard_view, name='kitchen_dashboard'),
    path('staff/kitchen/order/<int:order_id>/status/', staff_views.kitchen_update_status_view, name='kitchen_update_status'),
    path('staff/kitchen/item/<int:item_id>/cancel/', staff_views.kitchen_cancel_item_view, name='kitchen_cancel_item'),

    # Staff: Waiter Dashboard
    path('staff/waiter/', staff_views.waiter_dashboard_view, name='waiter_dashboard'),
    path('staff/waiter/order/<int:order_id>/serve/', staff_views.waiter_mark_served_view, name='waiter_mark_served'),
    path('staff/waiter/order/<int:order_id>/settle-cash/', staff_views.waiter_settle_cash_view, name='waiter_settle_cash'),
    path('staff/table/<int:table_id>/unlock/', staff_views.staff_unlock_table_view, name='staff_unlock_table'),
    path('staff/table/<int:table_id>/relock/', staff_views.waiter_relock_table_view, name='waiter_relock_table'),
    path('staff/table/<int:table_id>/lock-offline/', staff_views.waiter_lock_offline_table_view, name='waiter_lock_offline_table'),

    # Staff: Manager Dashboard
    path('staff/manager/', staff_views.manager_dashboard_view, name='manager_dashboard'),
    path('staff/manager/staff/create/', staff_views.manager_create_staff_view, name='manager_create_staff'),
    path('staff/manager/staff/<int:staff_id>/role/', staff_views.manager_update_staff_role_view, name='manager_update_staff_role'),
    path('staff/manager/staff/<int:staff_id>/edit/', staff_views.manager_edit_staff_view, name='manager_edit_staff'),
    path('staff/manager/staff/<int:staff_id>/reset-password/', staff_views.manager_reset_staff_password_view, name='manager_reset_staff_password'),
    path('staff/manager/staff/<int:staff_id>/delete/', staff_views.manager_delete_staff_view, name='manager_delete_staff'),
    path('staff/manager/item/<int:item_id>/toggle-stock/', staff_views.manager_toggle_item_availability_view, name='manager_toggle_stock'),
    path('staff/manager/item/<int:item_id>/price/', staff_views.manager_update_item_price_view, name='manager_update_price'),
    path('staff/manager/item/<int:item_id>/delete/', staff_views.manager_delete_item_view, name='manager_delete_item'),
    path('staff/manager/item/<int:item_id>/edit/', staff_views.manager_edit_item_view, name='manager_edit_item'),
    path('staff/manager/item/create/', staff_views.manager_create_item_view, name='manager_create_item'),
    path('staff/manager/category/create/', staff_views.manager_create_category_view, name='manager_create_category'),
    path('staff/manager/category/<int:category_id>/delete/', staff_views.manager_delete_category_view, name='manager_delete_category'),
    path('staff/manager/order/<int:order_id>/status/', staff_views.manager_update_order_status_view, name='manager_update_order_status'),
    path('staff/manager/order/<int:order_id>/payment/', staff_views.manager_update_order_payment_view, name='manager_update_order_payment'),
    path('staff/manager/order/<int:order_id>/cancel/', staff_views.manager_cancel_order_view, name='manager_cancel_order'),
    path('staff/manager/table/create/', staff_views.manager_create_table_view, name='manager_create_table'),
    path('staff/manager/table/<int:table_id>/toggle/', staff_views.manager_toggle_table_view, name='manager_toggle_table'),
    path('staff/manager/table/<int:table_id>/edit/', staff_views.manager_edit_table_view, name='manager_edit_table'),
    path('staff/manager/table/<int:table_id>/delete/', staff_views.manager_delete_table_view, name='manager_delete_table'),
    path('staff/manager/category/<int:category_id>/edit/', staff_views.manager_edit_category_view, name='manager_edit_category'),
    path('staff/manager/review/<int:review_id>/delete/', staff_views.manager_delete_review_view, name='manager_delete_review'),
    path('staff/manager/customer/create/', staff_views.manager_create_customer_view, name='manager_create_customer'),
    path('staff/manager/customer/<int:customer_id>/edit/', staff_views.manager_edit_customer_view, name='manager_edit_customer'),
    path('staff/manager/customer/<int:customer_id>/delete/', staff_views.manager_delete_customer_view, name='manager_delete_customer'),
    path('staff/manager/session/<int:session_id>/', staff_views.manager_session_detail_view, name='manager_session_detail'),
    path('staff/manager/order/<int:order_id>/', staff_views.manager_order_detail_view, name='manager_order_detail'),
]
