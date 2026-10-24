from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from accounts.models import Customer, StaffProfile
from menu.models import Restaurant, Category, MenuItem, Review
from orders.models import RestaurantTable, DiningSession, Order, OrderItem, Payment, WaiterAlert


class RealDiningFlowTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Seed Restaurant & Menu
        self.restaurant = Restaurant.objects.create(
            name="Spice Garden",
            address="COCSIT Campus, Latur",
            phone="9822001122"
        )
        self.category = Category.objects.create(restaurant=self.restaurant, name="Beverages")
        self.item1 = MenuItem.objects.create(
            category=self.category,
            name="Mango Lassi",
            price=Decimal("120.00"),
            is_veg=True,
            is_available=True
        )
        self.item2 = MenuItem.objects.create(
            category=self.category,
            name="Paneer Butter Masala",
            price=Decimal("250.00"),
            is_veg=True,
            is_available=True
        )

        # 2. Seed Table
        self.table = RestaurantTable.objects.create(table_number="T-03", capacity=4)

        # 3. Seed Staff
        self.chef_user = User.objects.create_user(username='chef1', password='password123', first_name='Chef')
        StaffProfile.objects.create(user=self.chef_user, role=StaffProfile.ROLE_KITCHEN)

        self.waiter_user = User.objects.create_user(username='waiter1', password='password123', first_name='Waiter')
        StaffProfile.objects.create(user=self.waiter_user, role=StaffProfile.ROLE_WAITER)

    def test_menu_item_curated_image_fallback(self):
        """Tests that items without uploaded images automatically provide curated food photos."""
        lassi_url = self.item1.get_image_url
        self.assertIn("unsplash.com", lassi_url)
        paneer_url = self.item2.get_image_url
        self.assertIn("unsplash.com", paneer_url)

    def test_unified_login_portal(self):
        """Tests Customer login and Staff credential login on the unified login page."""
        # 1. Customer Email / Google Login
        res_cust = self.client.post(reverse('accounts:google_login'), {
            'login_type': 'customer',
            'email': 'siddhi.google@gmail.com',
            'name': 'Siddhivinayak Tidake'
        })
        self.assertEqual(res_cust.status_code, 302)
        customer = Customer.objects.get(user__email='siddhi.google@gmail.com')
        self.assertEqual(customer.name, "Siddhivinayak Tidake")

        self.client.logout()

        # 2. Staff Login on the same portal redirects to role dashboard
        res_staff = self.client.post(reverse('accounts:google_login'), {
            'login_type': 'staff',
            'username': 'chef1',
            'password': 'password123'
        })
        self.assertRedirects(res_staff, reverse('orders:kitchen_dashboard'))

    def test_multi_round_table_session_and_settlement(self):
        """
        Tests the entire real-world dining lifecycle:
        1. Customer sets table T-03.
        2. Customer orders Round 1 (Never asked to pay now).
        3. Table T-03 is locked.
        4. Customer orders Round 2 (Appends new ticket in same DiningSession).
        5. Chef / Waiter serves food.
        6. Persistent glance bar reports "Food Served - Enjoy your meal!".
        7. Customer settles consolidated session bill.
        8. Table T-03 is unlocked!
        """
        # Login customer
        self.client.post(reverse('accounts:google_login'), {
            'login_type': 'customer',
            'email': 'siddhi.google@gmail.com',
            'name': 'Siddhivinayak Tidake'
        })
        customer = Customer.objects.get(user__email='siddhi.google@gmail.com')

        # Set Table T-03
        session = self.client.session
        session['table_id'] = 'T-03'
        session.save()

        # Round 1: Add Mango Lassi to Cart & Checkout
        self.client.post(f"/api/cart/add/{self.item1.id}/")
        res_checkout1 = self.client.post(reverse('orders:checkout'), {
            'special_instructions': 'Less sugar'
        })
        
        # Verify Session & Order 1
        dining_session = DiningSession.objects.get(customer=customer, is_active=True)
        self.assertEqual(dining_session.table_number, 'T-03')
        self.assertRedirects(res_checkout1, reverse('orders:session_live_detail', args=[dining_session.id]))

        order1 = dining_session.orders.first()
        self.assertEqual(order1.payment_method, Order.PAYMENT_METHOD_PAY_LATER)
        self.assertEqual(order1.payment_status, Order.PAYMENT_STATUS_PENDING)

        # Verify Table Lock
        self.table.refresh_from_db()
        self.assertTrue(self.table.is_locked)
        self.assertEqual(self.table.current_customer, customer)

        # Round 2: Add Paneer Masala to Cart & Checkout (Second round in same session)
        self.client.post(f"/api/cart/add/{self.item2.id}/")
        res_checkout2 = self.client.post(reverse('orders:checkout'), {
            'special_instructions': 'Medium spicy'
        })
        self.assertRedirects(res_checkout2, reverse('orders:session_live_detail', args=[dining_session.id]))

        # Verify 2 distinct order tickets under same session
        self.assertEqual(dining_session.orders.count(), 2)
        orders = dining_session.orders.order_by('-order_date')
        order2 = orders.first()
        self.assertEqual(order2.items.first().menu_item, self.item2)

        # Glance bar while cooking
        res_api = self.client.get(reverse('orders:api_my_active_order'))
        data_api = res_api.json()
        self.assertTrue(data_api['has_active_order'])
        self.assertIn("Queued", data_api['status_display'])

        # Kitchen / Floor marks all orders as SERVED
        for ord_obj in dining_session.orders.all():
            ord_obj.status = Order.STATUS_SERVED
            ord_obj.save(update_fields=['status'])

        # Glance bar when all food is served!
        res_served_api = self.client.get(reverse('orders:api_my_active_order'))
        data_served = res_served_api.json()
        self.assertEqual(data_served['status'], 'Served')
        self.assertIn("Food Served", data_served['status_display'])

        # Settle Consolidated Session Bill via session payment gateway
        res_pay = self.client.post(reverse('orders:session_payment_gateway', args=[dining_session.id]), {
            'method': Payment.METHOD_ONLINE_UPI
        })
        self.assertRedirects(res_pay, reverse('orders:session_live_detail', args=[dining_session.id]))

        # Verify Session Ended and Table Unlocked
        dining_session.refresh_from_db()
        self.assertFalse(dining_session.is_active)
        for ord_obj in dining_session.orders.all():
            self.assertEqual(ord_obj.payment_status, Order.PAYMENT_STATUS_PAID)

        self.table.refresh_from_db()
        self.assertFalse(self.table.is_locked)
        self.assertIsNone(self.table.current_customer)

    def test_firebase_google_login_endpoint(self):
        """Tests that Firebase Auth Google Sign-In endpoint provisions customer and creates session."""
        res = self.client.post(reverse('accounts:firebase_login'), {
            'email': 'aryan.student@gmail.com',
            'name': 'Aryan Gupta',
            'uid': 'fb_uid_1234567890',
            'avatar_url': 'https://lh3.googleusercontent.com/a/test-avatar'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['email'], 'aryan.student@gmail.com')

        # Check DB
        customer = Customer.objects.get(user__email='aryan.student@gmail.com')
        self.assertEqual(customer.name, 'Aryan Gupta')
        self.assertEqual(customer.google_id, 'fb_uid_1234567890')
        self.assertEqual(customer.avatar_url, 'https://lh3.googleusercontent.com/a/test-avatar')

    def test_custom_django_admin_panel(self):
        """Tests that Django Admin renders with custom Spice Garden branding & operations suite."""
        admin_user = User.objects.create_superuser(username='superadmin', password='adminpassword123', email='admin@spicegarden.com')
        self.client.login(username='superadmin', password='adminpassword123')

        res = self.client.get('/admin/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn("Spice Garden", content)
        self.assertIn("custom_admin.css", content)
        self.assertIn("Restaurant Operations Launchpad", content)

    def test_manager_menu_and_category_controls(self):
        """Tests manager adding/deleting categories and menu items."""
        manager_user = User.objects.create_user(username='manager1', password='password123', first_name='Manager')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='manager1', password='password123')

        # 1. Create Category
        res_cat = self.client.post(reverse('orders:manager_create_category'), {
            'name': 'Desserts & Sweets',
            'description': 'Traditional sweets and ice creams'
        })
        self.assertEqual(res_cat.status_code, 302)
        new_cat = Category.objects.get(name='Desserts & Sweets')
        self.assertEqual(new_cat.description, 'Traditional sweets and ice creams')

        # 2. Create Menu Item under category with optional image_url
        res_item = self.client.post(reverse('orders:manager_create_item'), {
            'category_id': new_cat.id,
            'name': 'Gulab Jamun with Ice Cream',
            'description': 'Warm jamuns with vanilla scoop',
            'price': '140.00',
            'is_veg': '1',
            'image_url': 'https://images.unsplash.com/photo-1589119908995-c6837fa14d48'
        })
        self.assertEqual(res_item.status_code, 302)
        new_item = MenuItem.objects.get(name='Gulab Jamun with Ice Cream')
        self.assertEqual(new_item.price, Decimal('140.00'))
        self.assertTrue(new_item.is_veg)
        self.assertEqual(new_item.image_url, 'https://images.unsplash.com/photo-1589119908995-c6837fa14d48')
        self.assertEqual(new_item.get_image_url, 'https://images.unsplash.com/photo-1589119908995-c6837fa14d48')

        # 2b. Edit Menu Item (edit name, price, and update image_url)
        res_edit_item = self.client.post(reverse('orders:manager_edit_item', args=[new_item.id]), {
            'category_id': new_cat.id,
            'name': 'Royal Gulab Jamun with Ice Cream',
            'description': 'Warm jamuns with vanilla scoop & pistachios',
            'price': '160.00',
            'is_veg': '1',
            'image_url': 'https://images.unsplash.com/photo-updated'
        })
        self.assertEqual(res_edit_item.status_code, 302)
        new_item.refresh_from_db()
        self.assertEqual(new_item.name, 'Royal Gulab Jamun with Ice Cream')
        self.assertEqual(new_item.price, Decimal('160.00'))
        self.assertEqual(new_item.image_url, 'https://images.unsplash.com/photo-updated')

        # 3. Delete Menu Item
        res_del_item = self.client.post(reverse('orders:manager_delete_item', args=[new_item.id]))
        self.assertEqual(res_del_item.status_code, 302)
        self.assertFalse(MenuItem.objects.filter(id=new_item.id).exists())

        # 4. Delete Category
        res_del_cat = self.client.post(reverse('orders:manager_delete_category', args=[new_cat.id]))
        self.assertEqual(res_del_cat.status_code, 302)
        self.assertFalse(Category.objects.filter(id=new_cat.id).exists())

    def test_manager_order_status_and_payment_controls(self):
        """Tests manager full control on orders: status change, payment settlement, and emergency cancellation."""
        manager_user = User.objects.create_user(username='manager2', password='password123', first_name='Manager')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='manager2', password='password123')

        # Create customer & order
        cust_user = User.objects.create_user(username='cust_test', email='test@gmail.com')
        customer = cust_user.customer_profile
        order = Order.objects.create(
            customer=customer,
            table=self.table,
            table_number=self.table.table_number,
            status=Order.STATUS_PENDING,
            payment_status=Order.PAYMENT_STATUS_PENDING,
            total_amount=Decimal('250.00')
        )
        self.table.lock_for(customer)

        # 1. Update status to Preparing
        res_status = self.client.post(reverse('orders:manager_update_order_status', args=[order.id]), {
            'status': Order.STATUS_PREPARING
        })
        self.assertEqual(res_status.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PREPARING)

        # 2. Update status to Completed -> Table lock released, payment marked Paid
        res_complete = self.client.post(reverse('orders:manager_update_order_status', args=[order.id]), {
            'status': Order.STATUS_COMPLETED
        })
        self.assertEqual(res_complete.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(order.payment_status, Order.PAYMENT_STATUS_PAID)
        self.table.refresh_from_db()
        self.assertFalse(self.table.is_locked)

        # 3. Create another order and emergency cancel it
        order2 = Order.objects.create(
            customer=customer,
            table=self.table,
            table_number=self.table.table_number,
            status=Order.STATUS_PENDING,
            payment_status=Order.PAYMENT_STATUS_PENDING,
            total_amount=Decimal('120.00')
        )
        self.table.lock_for(customer)

        res_cancel = self.client.post(reverse('orders:manager_cancel_order', args=[order2.id]))
        self.assertEqual(res_cancel.status_code, 302)
        order2.refresh_from_db()
        self.assertEqual(order2.status, Order.STATUS_CANCELLED)
        self.table.refresh_from_db()
        self.assertFalse(self.table.is_locked)

        # 4. Manager dashboard view with order_filter=active and order_filter=all
        res_dash_active = self.client.get(reverse('orders:manager_dashboard') + '?order_filter=active')
        self.assertEqual(res_dash_active.status_code, 200)
        res_dash_all = self.client.get(reverse('orders:manager_dashboard') + '?order_filter=all')
        self.assertEqual(res_dash_all.status_code, 200)
        self.assertIn(b"Floor & Session Orders", res_dash_all.content)

    def test_manager_ajax_in_place_actions_and_tab_preservation(self):
        """Tests that manager stock toggle and price update support in-place AJAX and preserve tab."""
        manager_user = User.objects.create_user(username='manager_tab', password='password123')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='manager_tab', password='password123')

        # 1. AJAX Stock Toggle
        res_stock = self.client.post(
            reverse('orders:manager_toggle_stock', args=[self.item1.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_stock.status_code, 200)
        data = res_stock.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['is_available'])
        self.item1.refresh_from_db()
        self.assertFalse(self.item1.is_available)

        # 2. AJAX Price Update
        res_price = self.client.post(
            reverse('orders:manager_update_price', args=[self.item1.id]),
            {'price': '135.00'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_price.status_code, 200)
        data_p = res_price.json()
        self.assertTrue(data_p['success'])
        self.assertEqual(data_p['price'], '135.0')
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.price, Decimal('135.00'))

        # 3. Non-AJAX redirect retains #menu-pane anchor
        res_redirect = self.client.post(reverse('orders:manager_toggle_stock', args=[self.item1.id]))
        self.assertEqual(res_redirect.status_code, 302)
        self.assertTrue(res_redirect.url.endswith('#menu-pane'))

    def test_customer_cannot_settle_bill_until_all_orders_delivered(self):
        """Tests that dining table guests cannot pay/settle the bill until all orders are delivered (Served)."""
        cust_user = User.objects.create_user(username='diner_settle', email='diner@gmail.com')
        customer = cust_user.customer_profile
        self.client.force_login(cust_user)

        session = DiningSession.objects.create(
            customer=customer,
            table=self.table,
            table_number=self.table.table_number,
            is_active=True
        )
        self.table.lock_for(customer)

        order = Order.objects.create(
            session=session,
            customer=customer,
            table=self.table,
            table_number=self.table.table_number,
            status=Order.STATUS_PREPARING, # Still cooking!
            payment_status=Order.PAYMENT_STATUS_PENDING,
            total_amount=Decimal('250.00')
        )

        # 1. Attempt to settle bill while food is still preparing -> MUST be rejected!
        res_pay = self.client.post(reverse('orders:session_payment_gateway', args=[session.id]), {
            'method': Payment.METHOD_ONLINE_UPI
        })
        self.assertEqual(res_pay.status_code, 302) # Redirects back with warning
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_STATUS_PENDING)
        self.assertTrue(session.is_active)
        self.assertTrue(self.table.is_locked)

        # 2. Mark order as SERVED (delivered to table)
        order.status = Order.STATUS_SERVED
        order.save(update_fields=['status'])

        # 3. Now settle bill -> MUST succeed and unlock table!
        res_pay_success = self.client.post(reverse('orders:session_payment_gateway', args=[session.id]), {
            'method': Payment.METHOD_ONLINE_UPI
        })
        self.assertEqual(res_pay_success.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_STATUS_PAID)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.table.refresh_from_db()
        self.assertFalse(self.table.is_locked)

    def test_manager_live_orders_poll(self):
        """Tests that manager dashboard poll endpoint returns real-time orders snapshot and counts."""
        manager_user = User.objects.create_user(username='manager_poll', password='password123')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='manager_poll', password='password123')

        res = self.client.get(reverse('orders:manager_dashboard') + '?poll=1', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertIn('active_orders_count', data)
        self.assertIn('status_hash', data)

    def test_waiter_relock_table_and_multiple_payments_per_session(self):
        """
        Tests the requirement:
        1. Guest sits at table, orders food, and settles early (before/as eating).
        2. Bill settlement marks all orders as Completed & Settled, table is unlocked.
        3. Waiter re-locks the table to the last customer under the same session ID.
        4. Customer orders another round under the reactivated session.
        5. Customer settles the second round: multiple payments for 1 session are recorded neatly.
        """
        # Create Customer
        user = User.objects.create_user(username='diner1', email='diner@example.com', first_name='Rajesh', last_name='Patil')
        customer = Customer.objects.get(user=user)

        # Start Session 1 on Table
        session = DiningSession.objects.create(
            customer=customer,
            table=self.table,
            table_number=self.table.table_number,
            is_active=True
        )
        self.table.lock_for(customer)

        # Round 1 Order
        order1 = Order.objects.create(
            session=session,
            customer=customer,
            table=self.table,
            table_number=self.table.table_number,
            status=Order.STATUS_SERVED,
            payment_status=Order.PAYMENT_STATUS_PENDING,
            total_amount=Decimal('200.00')
        )
        Payment.objects.create(order=order1, amount=Decimal('200.00'), status=Payment.STATUS_PENDING)

        # Settle Round 1 via session payment
        self.client.login(username='diner1', password='password123') # Not needed if session payment allows
        res_pay1 = self.client.post(reverse('orders:session_payment_gateway', args=[session.id]), {
            'method': Payment.METHOD_ONLINE_UPI
        })
        self.assertEqual(res_pay1.status_code, 302)

        # Verify Round 1 order is Completed & Paid, and table unlocked
        order1.refresh_from_db()
        self.assertEqual(order1.status, Order.STATUS_COMPLETED)
        self.assertEqual(order1.payment_status, Order.PAYMENT_STATUS_PAID)
        p1 = Payment.objects.get(order=order1)
        self.assertEqual(p1.status, Payment.STATUS_PAID)
        txn_round1 = p1.transaction_id
        self.assertTrue(txn_round1)

        self.table.refresh_from_db()
        self.assertFalse(self.table.is_locked)
        session.refresh_from_db()
        self.assertFalse(session.is_active)

        # 3. Waiter Re-Locks Table to continue same session
        self.client.login(username='waiter1', password='password123')
        res_relock = self.client.post(reverse('orders:waiter_relock_table', args=[self.table.id]), {
            'session_id': session.id
        })
        self.assertEqual(res_relock.status_code, 302)

        # Verify table is locked again and session is active
        self.table.refresh_from_db()
        self.assertTrue(self.table.is_locked)
        self.assertEqual(self.table.current_customer, customer)
        session.refresh_from_db()
        self.assertTrue(session.is_active)
        self.assertIsNone(session.ended_at)

        # 4. Customer orders Round 2 under same session
        order2 = Order.objects.create(
            session=session,
            customer=customer,
            table=self.table,
            table_number=self.table.table_number,
            status=Order.STATUS_SERVED,
            payment_status=Order.PAYMENT_STATUS_PENDING,
            total_amount=Decimal('150.00')
        )
        Payment.objects.create(order=order2, amount=Decimal('150.00'), status=Payment.STATUS_PENDING)

        # Settle Round 2
        res_pay2 = self.client.post(reverse('orders:session_payment_gateway', args=[session.id]), {
            'method': Payment.METHOD_ONLINE_UPI
        })
        self.assertEqual(res_pay2.status_code, 302)

        # Verify Round 2 completed & paid, and both payments are preserved
        order2.refresh_from_db()
        self.assertEqual(order2.status, Order.STATUS_COMPLETED)
        self.assertEqual(order2.payment_status, Order.PAYMENT_STATUS_PAID)
        p2 = Payment.objects.get(order=order2)
        self.assertEqual(p2.status, Payment.STATUS_PAID)
        txn_round2 = p2.transaction_id
        self.assertTrue(txn_round2)
        self.assertNotEqual(txn_round1, txn_round2) # Distinct payment IDs

        # Verify session has 2 payments
        p1.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(p1.transaction_id, txn_round1)
        self.assertEqual(session.payments_list.count(), 2)
        self.assertEqual(len(session.distinct_transaction_ids), 2)
        self.assertEqual(session.total_spent, Decimal('350.00'))

    def test_manager_session_grouped_orders_and_customer_directory(self):
        """Tests that manager dashboard organizes 'All Orders' per session and provides customer directory tab."""
        manager_user = User.objects.create_user(username='admin_boss', password='password123')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='admin_boss', password='password123')

        # Create a customer and session
        user_cust = User.objects.create_user(username='vip_diner', email='vip@example.com', first_name='Pooja', last_name='Deshmukh')
        cust = Customer.objects.get(user=user_cust)
        sess = DiningSession.objects.create(customer=cust, table=self.table, table_number='T-03', is_active=False, total_spent=Decimal('300.00'))
        ord_obj = Order.objects.create(session=sess, customer=cust, table=self.table, table_number='T-03', status=Order.STATUS_COMPLETED, payment_status=Order.PAYMENT_STATUS_PAID, total_amount=Decimal('300.00'))
        Payment.objects.create(order=ord_obj, amount=Decimal('300.00'), status=Payment.STATUS_PAID, transaction_id='TXN_VIP_999')

        # Request Manager Dashboard with All Orders filter
        res = self.client.get(reverse('orders:manager_dashboard') + '?order_filter=all')
        self.assertEqual(res.status_code, 200)

        # Verify context
        self.assertIn('sessions_list', res.context)
        self.assertIn('customers', res.context)
        self.assertTrue(len(res.context['sessions_list']) >= 1)

        # Check content contains session id, customer name, payment ref, and customer directory
        content = res.content.decode('utf-8')
        self.assertIn(f"Session #SESS-{sess.id}", content)
        self.assertIn("TXN_VIP_999", content)
        self.assertIn("Customer Directory", content)
        self.assertIn("Pooja Deshmukh", content)
        self.assertIn("vip@example.com", content)

    def test_strictly_only_last_session_can_be_relocked(self):
        """
        Tests that:
        1. Only the single most recent session on a table can be resumed/re-locked.
        2. Older sessions on the same table are strictly blocked from being resumed.
        3. Manager dashboard does not show re-lock button for older sessions.
        4. Re-locking while table is currently locked is rejected.
        """
        user = User.objects.create_user(username='customer_a', email='a@example.com', first_name='Anil')
        cust_a = Customer.objects.get(user=user)

        user_b = User.objects.create_user(username='customer_b', email='b@example.com', first_name='Bhavesh')
        cust_b = Customer.objects.get(user=user_b)

        # Session 1 (Older session)
        sess1 = DiningSession.objects.create(customer=cust_a, table=self.table, table_number=self.table.table_number, is_active=False)

        # Session 2 (Latest session)
        sess2 = DiningSession.objects.create(customer=cust_b, table=self.table, table_number=self.table.table_number, is_active=False)

        self.client.login(username='waiter1', password='password123')

        # 1. Attempt to resume older Session 1 -> MUST BE BLOCKED!
        res_old = self.client.post(reverse('orders:waiter_relock_table', args=[self.table.id]), {
            'session_id': sess1.id
        })
        self.assertEqual(res_old.status_code, 302)
        sess1.refresh_from_db()
        self.assertFalse(sess1.is_active)
        self.table.refresh_from_db()
        self.assertFalse(self.table.is_locked)

        # 2. Resume latest Session 2 -> MUST SUCCEED!
        res_latest = self.client.post(reverse('orders:waiter_relock_table', args=[self.table.id]), {
            'session_id': sess2.id
        })
        self.assertEqual(res_latest.status_code, 302)
        sess2.refresh_from_db()
        self.assertTrue(sess2.is_active)
        self.table.refresh_from_db()
        self.assertTrue(self.table.is_locked)
        self.assertEqual(self.table.current_customer, cust_b)

        # 3. Attempt to re-lock while table is already locked -> MUST BE BLOCKED!
        res_while_locked = self.client.post(reverse('orders:waiter_relock_table', args=[self.table.id]), {
            'session_id': sess2.id
        })
        self.assertEqual(res_while_locked.status_code, 302)

        # 4. In Manager Dashboard, verify older Session 1 does NOT have re-lock button
        manager_user = User.objects.create_user(username='manager_check', password='password123')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='manager_check', password='password123')

        # Unlock table first to test visibility
        self.table.release_lock()
        sess2.is_active = False
        sess2.save()

        res_mgr = self.client.get(reverse('orders:manager_dashboard') + '?order_filter=all')
        self.assertEqual(res_mgr.status_code, 200)
        self.assertIn('latest_session_ids', res_mgr.context)
        self.assertIn(sess2.id, res_mgr.context['latest_session_ids'])
        self.assertNotIn(sess1.id, res_mgr.context['latest_session_ids'])

    def test_waiter_lock_unoccupied_table_for_offline_users(self):
        """
        Tests that waiters can lock unoccupied tables for offline/walk-in users:
        1. Table is unoccupied.
        2. Waiter locks table for 'Mr. Ramesh (Offline)'.
        3. Table is marked as occupied/locked and an active session is established.
        4. Online users are blocked from placing orders on this locked table.
        5. Waiter can unlock/release table when offline diner finishes.
        """
        self.client.login(username='waiter1', password='password123')

        # 1. Lock table for offline user
        res_lock = self.client.post(reverse('orders:waiter_lock_offline_table', args=[self.table.id]), {
            'guest_name': 'Mr. Ramesh',
            'phone': '9876543210',
            'notes': 'Table for 3, offline ordering'
        })
        self.assertEqual(res_lock.status_code, 302)

        # 2. Check table is locked
        self.table.refresh_from_db()
        self.assertTrue(self.table.is_locked)
        self.assertIn("Mr. Ramesh", self.table.current_customer.name)
        self.assertEqual(self.table.current_customer.phone, '9876543210')

        # 3. Active dining session created
        active_sess = DiningSession.objects.get(table=self.table, is_active=True)
        self.assertEqual(active_sess.customer, self.table.current_customer)

        # 4. Online customer visits and attempts to checkout on this table -> BLOCKED!
        user_online = User.objects.create_user(username='online_intruder', email='intruder@gmail.com')
        Customer.objects.get(user=user_online)
        self.client.login(username='online_intruder', password='password123')

        session_state = self.client.session
        session_state['table_id'] = self.table.table_number
        session_state.save()

        self.client.post(f"/api/cart/add/{self.item1.id}/")
        res_checkout = self.client.post(reverse('orders:checkout'))
        # Must be redirected to cart because table is locked
        self.assertRedirects(res_checkout, reverse('orders:cart'))

        # 5. Waiter releases lock
        self.client.login(username='waiter1', password='password123')
        res_unlock = self.client.post(reverse('orders:staff_unlock_table', args=[self.table.id]))
        self.assertEqual(res_unlock.status_code, 302)

        self.table.refresh_from_db()
        self.assertFalse(self.table.is_locked)
        active_sess.refresh_from_db()
        self.assertFalse(active_sess.is_active)

    def test_call_staff_restricted_to_locked_table_customer(self):
        """
        Tests that calling staff/waiter is strictly allowed ONLY by the authenticated customer
        who holds the active concurrency lock for that specific table.
        """
        diner_a = User.objects.create_user(username='diner_a', email='diner_a@gmail.com')
        cust_a = Customer.objects.get(user=diner_a)

        diner_b = User.objects.create_user(username='diner_b', email='diner_b@gmail.com')
        cust_b = Customer.objects.get(user=diner_b)

        # Lock table for Diner A
        self.table.lock_for(cust_a)

        # 1. Unauthenticated user calls staff -> 401 Unauthorized
        self.client.logout()
        res_unauth = self.client.post(reverse('orders:api_call_waiter'), {'message': 'Need water'})
        self.assertEqual(res_unauth.status_code, 401)

        # 2. Diner B (intruder / another customer) attempts to call staff for Diner A's locked table -> 403 Forbidden!
        self.client.force_login(diner_b)
        sess = self.client.session
        sess['table_id'] = self.table.table_number
        sess.save()

        res_intruder = self.client.post(reverse('orders:api_call_waiter'), {'message': 'Need bill'})
        self.assertEqual(res_intruder.status_code, 403)
        self.assertFalse(res_intruder.json()['success'])

        # 3. Diner A (legitimate locked customer) calls staff -> 200 OK!
        self.client.force_login(diner_a)
        sess = self.client.session
        sess['table_id'] = self.table.table_number
        sess.save()

        res_owner = self.client.post(reverse('orders:api_call_waiter'), {'message': 'Please bring napkins'})
        self.assertEqual(res_owner.status_code, 200)
        self.assertTrue(res_owner.json()['success'])
        self.assertTrue(WaiterAlert.objects.filter(customer=cust_a, table=self.table).exists())

    def test_ended_session_cleared_from_active_and_restored_on_resumption(self):
        """
        Tests that:
        1. When a session ends, it is removed from active sessions (live tracker redirects, api_my_active_order returns false).
        2. When waiter resumes/re-locks the table, the active session is immediately restored for the diner.
        """
        diner = User.objects.create_user(username='diner_sess', email='diner_sess@gmail.com')
        cust = Customer.objects.get(user=diner)
        self.table.lock_for(cust)

        # Create active dining session with order
        sess = DiningSession.objects.create(customer=cust, table=self.table, table_number=self.table.table_number, is_active=True)
        ord1 = Order.objects.create(customer=cust, table=self.table, table_number=self.table.table_number, session=sess, status=Order.STATUS_SERVED, payment_status=Order.PAYMENT_STATUS_PENDING, subtotal=Decimal('200.00'), total_amount=Decimal('210.00'))

        self.client.force_login(diner)

        # 1. While session is active:
        res_live = self.client.get(reverse('orders:session_live'))
        self.assertEqual(res_live.status_code, 200)
        self.assertEqual(res_live.context['session'].id, sess.id)

        res_active_order = self.client.get(reverse('orders:api_my_active_order'))
        self.assertEqual(res_active_order.status_code, 200)
        self.assertTrue(res_active_order.json()['has_active_order'])

        # 2. Session ends (bill settled, table unlocked)
        sess.end_session()
        ord1.status = Order.STATUS_COMPLETED
        ord1.payment_status = Order.PAYMENT_STATUS_PAID
        ord1.save()

        # Check live tracker without session_id -> MUST redirect to menu with info (not load ended session!)
        res_live_ended = self.client.get(reverse('orders:session_live'))
        self.assertEqual(res_live_ended.status_code, 302)
        self.assertRedirects(res_live_ended, reverse('menu:menu_list'))

        # Check api_my_active_order -> MUST return has_active_order: False
        res_active_ended = self.client.get(reverse('orders:api_my_active_order'))
        self.assertEqual(res_active_ended.status_code, 200)
        self.assertFalse(res_active_ended.json()['has_active_order'])

        # 3. Waiter resumes session
        self.client.login(username='waiter1', password='password123')
        res_resume = self.client.post(reverse('orders:waiter_relock_table', args=[self.table.id]), {'session_id': sess.id})
        self.assertEqual(res_resume.status_code, 302)

        sess.refresh_from_db()
        self.assertTrue(sess.is_active)
        self.table.refresh_from_db()
        self.assertTrue(self.table.is_locked)

        # 4. Diner accesses again -> Active session is BACK!
        self.client.force_login(diner)
        res_live_restored = self.client.get(reverse('orders:session_live'))
        self.assertEqual(res_live_restored.status_code, 200)
        self.assertEqual(res_live_restored.context['session'].id, sess.id)

        res_active_restored = self.client.get(reverse('orders:api_my_active_order'))
        self.assertEqual(res_active_restored.status_code, 200)
        self.assertTrue(res_active_restored.json()['has_active_order'])

    def test_customer_reviews_crud_and_manager_moderation(self):
        """
        Tests customer review submission, viewing under My Reviews, editing, deleting,
        and manager dashboard review analytics and moderation.
        """
        diner = User.objects.create_user(username='diner_rev', email='diner_rev@gmail.com')
        cust = Customer.objects.get(user=diner)

        self.client.force_login(diner)

        # 1. Submit review
        res_post = self.client.post(reverse('menu:submit_review', args=[self.item1.id]), {
            'rating': 5,
            'comment': 'Best butter chicken in town!'
        })
        self.assertEqual(res_post.status_code, 302)

        rev = Review.objects.get(customer=cust, menu_item=self.item1)
        self.assertEqual(rev.rating, 5)
        self.assertEqual(rev.comment, 'Best butter chicken in town!')

        # 2. View under My Reviews tab
        res_my_rev = self.client.get(reverse('menu:my_reviews'))
        self.assertEqual(res_my_rev.status_code, 200)
        self.assertContains(res_my_rev, 'Best butter chicken in town!')

        # 3. Edit review
        res_edit = self.client.post(reverse('menu:edit_review', args=[rev.id]), {
            'rating': 4,
            'comment': 'Very good butter chicken, highly recommended!'
        })
        self.assertEqual(res_edit.status_code, 302)
        rev.refresh_from_db()
        self.assertEqual(rev.rating, 4)
        self.assertEqual(rev.comment, 'Very good butter chicken, highly recommended!')

        # 4. Public API for dish reviews
        res_api = self.client.get(reverse('menu:api_item_reviews', args=[self.item1.id]))
        self.assertEqual(res_api.status_code, 200)
        api_data = res_api.json()
        self.assertEqual(api_data['review_count'], 1)
        self.assertEqual(api_data['reviews'][0]['rating'], 4)

        # 5. Manager Dashboard views reviews
        manager_user = User.objects.create_user(username='manager_rev', password='password123')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='manager_rev', password='password123')

        res_mgr = self.client.get(reverse('orders:manager_dashboard'))
        self.assertEqual(res_mgr.status_code, 200)
        self.assertIn('reviews_list', res_mgr.context)
        self.assertEqual(res_mgr.context['reviews_count'], 1)
        self.assertEqual(res_mgr.context['avg_rating'], 4.0)

        # 6. Manager moderates/deletes inappropriate review
        res_del = self.client.post(reverse('orders:manager_delete_review', args=[rev.id]))
        self.assertEqual(res_del.status_code, 302)
        self.assertFalse(Review.objects.filter(pk=rev.id).exists())

    def test_manager_crud_staff_tables_users_categories(self):
        """Tests Manager CRUD operations for Staff, Tables, Categories, and Customers."""
        manager_user = User.objects.create_user(username='top_manager', password='password123', first_name='Boss')
        StaffProfile.objects.create(user=manager_user, role=StaffProfile.ROLE_MANAGER)
        self.client.login(username='top_manager', password='password123')

        # 1. Staff CRUD
        # Create
        res_st_create = self.client.post(reverse('orders:manager_create_staff'), {
            'username': 'waiter_new',
            'first_name': 'Ramesh',
            'last_name': 'Patil',
            'password': 'password123',
            'role': StaffProfile.ROLE_WAITER,
            'phone': '9811122233'
        })
        self.assertEqual(res_st_create.status_code, 302)
        new_staff = StaffProfile.objects.get(user__username='waiter_new')
        self.assertEqual(new_staff.user.first_name, 'Ramesh')

        # Edit
        res_st_edit = self.client.post(reverse('orders:manager_edit_staff', args=[new_staff.id]), {
            'first_name': 'Rameshwar',
            'last_name': 'Patil',
            'phone': '9899988877',
            'role': StaffProfile.ROLE_KITCHEN
        })
        self.assertEqual(res_st_edit.status_code, 302)
        new_staff.refresh_from_db()
        self.assertEqual(new_staff.user.first_name, 'Rameshwar')
        self.assertEqual(new_staff.role, StaffProfile.ROLE_KITCHEN)

        # Reset Password
        res_st_pwd = self.client.post(reverse('orders:manager_reset_staff_password', args=[new_staff.id]), {
            'new_password': 'BrandNewPassword123'
        })
        self.assertEqual(res_st_pwd.status_code, 302)
        new_staff.user.refresh_from_db()
        self.assertTrue(new_staff.user.check_password('BrandNewPassword123'))

        # Delete
        res_st_del = self.client.post(reverse('orders:manager_delete_staff', args=[new_staff.id]))
        self.assertEqual(res_st_del.status_code, 302)
        self.assertFalse(User.objects.filter(username='waiter_new').exists())

        # 2. Table CRUD
        # Create
        res_tbl_create = self.client.post(reverse('orders:manager_create_table'), {
            'table_number': 'T-99',
            'capacity': 6
        })
        self.assertEqual(res_tbl_create.status_code, 302)
        tbl = RestaurantTable.objects.get(table_number='T-99')
        self.assertEqual(tbl.capacity, 6)

        # Edit
        res_tbl_edit = self.client.post(reverse('orders:manager_edit_table', args=[tbl.id]), {
            'table_number': 'T-100',
            'capacity': 8
        })
        self.assertEqual(res_tbl_edit.status_code, 302)
        tbl.refresh_from_db()
        self.assertEqual(tbl.table_number, 'T-100')
        self.assertEqual(tbl.capacity, 8)

        # Delete
        res_tbl_del = self.client.post(reverse('orders:manager_delete_table', args=[tbl.id]))
        self.assertEqual(res_tbl_del.status_code, 302)
        self.assertFalse(RestaurantTable.objects.filter(table_number='T-100').exists())

        # 3. Category CRUD
        # Create
        res_cat_create = self.client.post(reverse('orders:manager_create_category'), {
            'name': 'Desserts Special',
            'description': 'Delicious Indian sweets'
        })
        self.assertEqual(res_cat_create.status_code, 302)
        new_cat = Category.objects.get(name='Desserts Special')

        # Edit
        res_cat_edit = self.client.post(reverse('orders:manager_edit_category', args=[new_cat.id]), {
            'name': 'Royal Desserts',
            'description': 'Handcrafted gourmet sweets'
        })
        self.assertEqual(res_cat_edit.status_code, 302)
        new_cat.refresh_from_db()
        self.assertEqual(new_cat.name, 'Royal Desserts')

        # Delete
        res_cat_del = self.client.post(reverse('orders:manager_delete_category', args=[new_cat.id]))
        self.assertEqual(res_cat_del.status_code, 302)
        self.assertFalse(Category.objects.filter(id=new_cat.id).exists())

        # 4. Customer / User CRUD
        # Create
        res_cust_create = self.client.post(reverse('orders:manager_create_customer'), {
            'username': 'diner_priya',
            'first_name': 'Priya',
            'last_name': 'Sharma',
            'email': 'priya.sharma@example.com',
            'phone': '9876543210'
        })
        self.assertEqual(res_cust_create.status_code, 302)
        cust = Customer.objects.get(user__username='diner_priya')
        self.assertEqual(cust.name, 'Priya Sharma')
        self.assertEqual(cust.phone, '9876543210')

        # Edit
        res_cust_edit = self.client.post(reverse('orders:manager_edit_customer', args=[cust.id]), {
            'first_name': 'Priyanka',
            'last_name': 'Sharma',
            'email': 'priyanka.s@example.com',
            'phone': '9876543219'
        })
        self.assertEqual(res_cust_edit.status_code, 302)
        cust.refresh_from_db()
        self.assertEqual(cust.name, 'Priyanka Sharma')
        self.assertEqual(cust.email, 'priyanka.s@example.com')
        self.assertEqual(cust.phone, '9876543219')

        # Delete
        res_cust_del = self.client.post(reverse('orders:manager_delete_customer', args=[cust.id]))
        self.assertEqual(res_cust_del.status_code, 302)
        self.assertFalse(User.objects.filter(username='diner_priya').exists())


class DynamicTableCombinedPaymentAndStaffSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Seed Restaurant, Category & Item
        self.restaurant = Restaurant.objects.create(name="Spice Garden", address="COCSIT Campus", phone="9822001122")
        self.category = Category.objects.create(restaurant=self.restaurant, name="Main Course")
        self.item = MenuItem.objects.create(
            category=self.category,
            name="Dal Tadka",
            price=Decimal("150.00"),
            is_veg=True,
            is_available=True
        )

        # Seed Tables
        self.table_t1 = RestaurantTable.objects.create(table_number="T-01", capacity=4)
        self.table_t2 = RestaurantTable.objects.create(table_number="T-02", capacity=6)

        # Seed Users
        self.user_a = User.objects.create_user(username='diner_a', email='diner_a@test.com', password='passA')
        self.customer_a = getattr(self.user_a, 'customer_profile', None) or Customer.objects.get(user=self.user_a)

        self.user_b = User.objects.create_user(username='diner_b', email='diner_b@test.com', password='passB')
        self.customer_b = getattr(self.user_b, 'customer_profile', None) or Customer.objects.get(user=self.user_b)

        # Staff Users
        self.waiter_user = User.objects.create_user(username='waiter_ravi', password='waiterPass123', is_staff=True)
        self.waiter_profile = StaffProfile.objects.create(user=self.waiter_user, role=StaffProfile.ROLE_WAITER)

        self.manager_user = User.objects.create_user(username='manager_amit', password='mgrPass123', is_staff=True)
        self.manager_profile = StaffProfile.objects.create(user=self.manager_user, role=StaffProfile.ROLE_MANAGER)

    def test_dynamic_table_status_api_and_concurrency_lock(self):
        """
        Tests:
        1. /api/tables/status/ dynamic real-time reporting.
        2. Single-user lock enforcement: if Table T-01 is locked by Diner A, Diner B cannot select it.
        3. Clear error message directing user to waiter.
        """
        # Lock T-01 for Customer A
        self.table_t1.lock_for(self.customer_a)

        # Diner B opens table selection modal -> calls /api/tables/status/
        self.client.force_login(self.user_b)
        res = self.client.get(reverse('orders:api_tables_status'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])

        t1_info = next(t for t in data['tables'] if t['table_number'] == 'T-01')
        self.assertFalse(t1_info['can_select'])
        self.assertTrue(t1_info['is_locked_by_other'])
        self.assertEqual(t1_info['status_label'], 'Occupied')

        t2_info = next(t for t in data['tables'] if t['table_number'] == 'T-02')
        self.assertTrue(t2_info['can_select'])
        self.assertFalse(t2_info['is_locked_by_other'])
        self.assertEqual(t2_info['status_label'], 'Free')

        # Diner B tries to select locked T-01 -> rejected
        res_set = self.client.post(reverse('menu:set_table'), {'table_number': 'T-01'}, follow=True)
        self.assertContains(res_set, "currently occupied and locked by another diner")
        self.assertContains(res_set, "talk with a waiter to uplift the lock")
        self.assertNotEqual(self.client.session.get('table_id'), 'T-01')

        # Diner A calls /api/tables/status/ -> T-01 is marked 'My Table' and selectable
        self.client.force_login(self.user_a)
        res_a = self.client.get(reverse('orders:api_tables_status'))
        data_a = res_a.json()
        t1_a = next(t for t in data_a['tables'] if t['table_number'] == 'T-01')
        self.assertTrue(t1_a['can_select'])
        self.assertTrue(t1_a['is_locked_by_me'])
        self.assertEqual(t1_a['status_label'], 'My Table')

        # Diner A selects T-01 -> accepted
        res_set_a = self.client.post(reverse('menu:set_table'), {'table_number': 'T-01'}, follow=True)
        self.assertEqual(self.client.session.get('table_id'), 'T-01')

    def test_order_history_filtering_empty_sessions(self):
        """
        Tests:
        1. Customer dining session with 0 orders is excluded from order history.
        2. Session with a cancelled order is preserved in order history for audit.
        3. Manager floor history excludes 0-order sessions.
        """
        # Session 1: 0 orders (abandoned table selection)
        sess_empty = DiningSession.objects.create(
            customer=self.customer_a,
            table=self.table_t1,
            table_number="T-01",
            is_active=False
        )

        # Session 2: Placed and cancelled order
        sess_cancelled = DiningSession.objects.create(
            customer=self.customer_a,
            table=self.table_t2,
            table_number="T-02",
            is_active=False
        )
        ord_cancelled = Order.objects.create(
            customer=self.customer_a,
            table=self.table_t2,
            table_number="T-02",
            session=sess_cancelled,
            status=Order.STATUS_CANCELLED,
            subtotal=Decimal("150.00"),
            tax_amount=Decimal("7.50"),
            total_amount=Decimal("157.50")
        )

        # Check Customer My Orders view
        self.client.force_login(self.user_a)
        res = self.client.get(reverse('orders:my_orders'))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, f"#sessOrders{sess_empty.id}")
        self.assertContains(res, f"#sessOrders{sess_cancelled.id}")
        self.assertContains(res, "Table T-02")

        # Check Manager Dashboard Floor Orders pane
        self.client.force_login(self.manager_user)
        res_mgr = self.client.get(reverse('orders:manager_dashboard') + '?order_filter=all')
        self.assertEqual(res_mgr.status_code, 200)
        self.assertNotContains(res_mgr, f"Session #SESS-{sess_empty.id}")
        self.assertContains(res_mgr, f"Session #SESS-{sess_cancelled.id}")

    def test_session_combined_payments_and_installment_distinction(self):
        """
        Tests:
        1. 3 orders in a session settled in 1 payment -> returns 1 combined receipt.
        2. 5 orders in a session settled across 2 installments (Rounds 1-3 then Rounds 4-5) -> returns 2 distinct receipts.
        3. Manager session detail displays both installments without duplicate clutter.
        """
        session = DiningSession.objects.create(
            customer=self.customer_a,
            table=self.table_t1,
            table_number="T-01",
            is_active=True
        )

        # Create 5 orders across multiple rounds
        orders = []
        for i in range(1, 6):
            ord_obj = Order.objects.create(
                customer=self.customer_a,
                table=self.table_t1,
                table_number="T-01",
                session=session,
                status=Order.STATUS_COMPLETED,
                payment_status=Order.PAYMENT_STATUS_PAID,
                subtotal=Decimal("100.00"),
                tax_amount=Decimal("5.00"),
                total_amount=Decimal("105.00")
            )
            OrderItem.objects.create(order=ord_obj, menu_item=self.item, quantity=1, price=Decimal("100.00"))
            orders.append(ord_obj)

        # Installment 1: Settle Orders 1, 2, 3 together with TXN_BATCH_1
        txn1 = "TXN_BATCH_1"
        for ord_obj in orders[:3]:
            Payment.objects.create(
                order=ord_obj,
                amount=ord_obj.total_amount,
                method=Payment.METHOD_ONLINE_UPI,
                status=Payment.STATUS_PAID,
                transaction_id=txn1
            )

        # Installment 2: Settle Orders 4, 5 later with TXN_BATCH_2 (Cash)
        txn2 = "CASH_BATCH_2"
        for ord_obj in orders[3:]:
            Payment.objects.create(
                order=ord_obj,
                amount=ord_obj.total_amount,
                method=Payment.METHOD_CASH_COUNTER,
                status=Payment.STATUS_PAID,
                transaction_id=txn2,
                collected_by=self.waiter_user
            )

        # Call get_combined_payments()
        combined = session.get_combined_payments(status=Payment.STATUS_PAID)
        self.assertEqual(len(combined), 2)

        # Verify Installment 1
        rcp1 = combined[0]
        self.assertEqual(rcp1['receipt_index'], 1)
        self.assertEqual(rcp1['transaction_id'], txn1)
        self.assertEqual(rcp1['method_display'], 'UPI')
        self.assertEqual(rcp1['total_amount'], Decimal("315.00")) # 3 x 105.00
        self.assertEqual(rcp1['payments_count'], 3)
        self.assertIn("Rounds 1, 2, 3", rcp1['orders_label'])

        # Verify Installment 2
        rcp2 = combined[1]
        self.assertEqual(rcp2['receipt_index'], 2)
        self.assertEqual(rcp2['transaction_id'], txn2)
        self.assertEqual(rcp2['method_display'], 'Cash')
        self.assertEqual(rcp2['total_amount'], Decimal("210.00")) # 2 x 105.00
        self.assertEqual(rcp2['payments_count'], 2)
        self.assertIn("Rounds 4, 5", rcp2['orders_label'])
        self.assertEqual(rcp2['collected_by'], self.waiter_user)

        # Test Manager Session Detail page
        self.client.force_login(self.manager_user)
        res_detail = self.client.get(reverse('orders:manager_session_detail', args=[session.id]))
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "Receipt #1")
        self.assertContains(res_detail, "Receipt #2")
        self.assertContains(res_detail, "TXN_BATCH_1")
        self.assertContains(res_detail, "CASH_BATCH_2")
        self.assertContains(res_detail, "Rounds 1, 2, 3")
        self.assertContains(res_detail, "Rounds 4, 5")

    def test_staff_self_service_password_change(self):
        """
        Tests:
        1. Staff members can change password using current password.
        2. Non-staff rejection.
        3. Wrong current password rejection.
        4. Password mismatch rejection.
        5. Successful secure change (PBKDF2 hash, not plain text) and active session.
        """
        url = reverse('orders:staff_change_password')

        # 1. Non-staff customer tries -> 403 Forbidden
        self.client.force_login(self.user_a)
        res_nonstaff = self.client.post(url, {
            'current_password': 'passA',
            'new_password': 'newPassA123',
            'confirm_password': 'newPassA123'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_nonstaff.status_code, 403)

        # 2. Waiter tries with wrong current password -> 400 Bad Request
        self.client.force_login(self.waiter_user)
        res_wrong = self.client.post(url, {
            'current_password': 'wrongPassword',
            'new_password': 'newSecretPass123',
            'confirm_password': 'newSecretPass123'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_wrong.status_code, 400)
        self.assertIn("Current password is incorrect", res_wrong.json()['error'])

        # 3. Waiter tries with mismatching confirmation -> 400 Bad Request
        res_mismatch = self.client.post(url, {
            'current_password': 'waiterPass123',
            'new_password': 'newSecretPass123',
            'confirm_password': 'differentPass123'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_mismatch.status_code, 400)
        self.assertIn("do not match", res_mismatch.json()['error'])

        # 4. Waiter successfully changes password
        res_success = self.client.post(url, {
            'current_password': 'waiterPass123',
            'new_password': 'freshSecureWaiterPass99',
            'confirm_password': 'freshSecureWaiterPass99'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_success.status_code, 200)
        self.assertTrue(res_success.json()['success'])

        # Verify password in DB is securely hashed (starts with pbkdf2_sha256$), NEVER plain text!
        self.waiter_user.refresh_from_db()
        self.assertTrue(self.waiter_user.password.startswith('pbkdf2_sha256$'))
        self.assertNotIn('freshSecureWaiterPass99', self.waiter_user.password)
        self.assertTrue(self.waiter_user.check_password('freshSecureWaiterPass99'))

        # Verify user can log in with new password
        self.client.logout()
        res_login = self.client.post(reverse('accounts:staff_login'), {
            'username': 'waiter_ravi',
            'password': 'freshSecureWaiterPass99'
        })
        self.assertRedirects(res_login, reverse('orders:waiter_dashboard'))






