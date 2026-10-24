from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from accounts.models import Customer, StaffProfile


class GoogleAuthAccountLinkingTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Create an existing customer with email and phone
        self.existing_user = User.objects.create_user(
            username='siddhivinayak',
            email='siddhivinayaktidake04@gmail.com',
            first_name='Siddhivinayak',
            last_name='Tidake'
        )
        self.customer = Customer.objects.get_or_create(user=self.existing_user)[0]
        self.customer.phone = '+91 9876543210'
        self.customer.save()

        # Create a manager staff user
        self.manager_user = User.objects.create_user(
            username='manager_rajesh',
            email='manager@royalspice.com',
            first_name='Rajesh',
            last_name='Sharma'
        )
        StaffProfile.objects.create(
            user=self.manager_user,
            role=StaffProfile.ROLE_MANAGER,
            phone='9811122233'
        )

    def test_firebase_login_reuses_existing_account_by_email(self):
        """If user already exists with matching email, Firebase Google login must reuse that account and link google_id."""
        response = self.client.post(reverse('accounts:firebase_login'), {
            'email': 'siddhivinayaktidake04@gmail.com',
            'name': 'Siddhivinayak Tidake',
            'uid': 'firebase_uid_12345',
            'avatar_url': 'https://lh3.googleusercontent.com/avatar123.jpg'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Verify only 1 user exists with this email
        users = User.objects.filter(email='siddhivinayaktidake04@gmail.com')
        self.assertEqual(users.count(), 1)
        user = users.first()
        self.assertEqual(user.id, self.existing_user.id)
        self.assertEqual(user.username, 'siddhivinayak')

        # Verify google_id is linked to existing customer profile, preserving phone
        cust = user.customer_profile
        self.assertEqual(cust.google_id, 'firebase_uid_12345')
        self.assertEqual(cust.phone, '+91 9876543210')

        # Verify logged in as this user
        self.assertEqual(int(self.client.session['_auth_user_id']), self.existing_user.id)

    def test_firebase_login_staff_redirects_to_staff_dashboard(self):
        """Staff user signing in via Google should be routed to their staff dashboard."""
        response = self.client.post(reverse('accounts:firebase_login'), {
            'email': 'manager@royalspice.com',
            'name': 'Rajesh Sharma',
            'uid': 'manager_uid_999'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect_url'], reverse('orders:manager_dashboard'))

    def test_form_google_login_reuses_existing_account(self):
        """Fallback direct Google login reuses account if email matches."""
        response = self.client.post(reverse('accounts:google_login'), {
            'login_type': 'customer',
            'email': 'SIDDHIVINAYAKTIDAKE04@GMAIL.COM',  # Case-insensitive
            'name': 'Siddhivinayak Tidake',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.existing_user.id)

        cust = Customer.objects.get(user=self.existing_user)
        self.assertTrue(cust.google_id.startswith('goog_'))
        self.assertEqual(cust.phone, '+91 9876543210')
