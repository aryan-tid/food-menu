import os
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from .models import Customer, StaffProfile


def init_firebase_admin():
    """Initializes Firebase Admin SDK ONLY if a valid service account key file is configured."""
    sa_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_KEY', '')
    if not sa_path or not os.path.exists(sa_path):
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials
        if not firebase_admin._apps:
            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)
        return True
    except Exception:
        return False


@require_POST
def firebase_login_view(request):
    """
    Handles Firebase Google Sign-In:
    - Receives client Firebase ID Token & profile information.
    - Verifies token via Firebase Admin SDK if configured with service account.
    - Synchronizes or provisions Customer & Django User in milliseconds.
    - Establishes authenticated Django session.
    """
    next_url = request.POST.get('next') or request.GET.get('next') or reverse('menu:menu_list')
    id_token = request.POST.get('id_token', '').strip()
    email = request.POST.get('email', '').strip().lower()
    name = request.POST.get('name', '').strip()
    avatar_url = request.POST.get('avatar_url', '').strip()
    uid = request.POST.get('uid', '').strip()

    # Optional server-side verification with Firebase Admin SDK (only if key file is configured)
    if id_token and init_firebase_admin():
        try:
            from firebase_admin import auth as fb_auth
            decoded = fb_auth.verify_id_token(id_token)
            if decoded.get('email'):
                email = decoded.get('email').strip().lower()
                name = decoded.get('name') or name
                avatar_url = decoded.get('picture') or avatar_url
                uid = decoded.get('uid') or uid
        except Exception:
            pass

    if not email or '@' not in email:
        return JsonResponse({'success': False, 'error': 'Valid email is required from Google Auth.'}, status=400)

    parts = name.split(None, 1) if name else ['Customer', '']
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''

    # Get or reuse existing user with matching email (case-insensitive)
    base_username = email.split('@')[0]
    username = base_username
    counter = 1
    user = User.objects.filter(email__iexact=email).order_by('-last_login', '-id').first()
    if not user:
        while User.objects.filter(username__iexact=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        user.set_unusable_password()
        user.save()
    else:
        if not user.first_name and first_name:
            user.first_name = first_name
            user.last_name = last_name
            user.save(update_fields=['first_name', 'last_name'])

    customer, _ = Customer.objects.get_or_create(user=user)
    if uid:
        customer.google_id = uid
    if avatar_url and not customer.avatar_url:
        customer.avatar_url = avatar_url
    customer.save()

    # Log into Django session (Single seamless sign-in & sign-up for all Google users)
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)
    messages.success(request, f"Welcome, {customer.name}! Signed in via Google.")

    # Determine resolved redirect based on role or explicit next_url
    resolved_redirect = next_url
    if hasattr(user, 'staff_profile'):
        role = user.staff_profile.role
        if role == StaffProfile.ROLE_KITCHEN:
            resolved_redirect = reverse('orders:kitchen_dashboard')
        elif role == StaffProfile.ROLE_WAITER:
            resolved_redirect = reverse('orders:waiter_dashboard')
        else:
            resolved_redirect = reverse('orders:manager_dashboard')
    elif user.is_superuser:
        resolved_redirect = reverse('orders:manager_dashboard')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'redirect_url': resolved_redirect,
            'user': {
                'name': customer.name,
                'email': customer.email,
                'avatar': customer.avatar_url or ''
            }
        })

    return redirect(resolved_redirect)


def google_login_view(request):
    """
    Unified Authentication Portal:
    1. Default View: Customer Google Sign-In
       - 1-Click Viva Demo Login button (instant student demo).
       - Custom Google Account prompt (Gmail & Name).
    2. Staff Tab: Staff Credentials Login
       - Username & Password for Kitchen Chef, Waiter, and Restaurant Manager.
       - Quick-fill credentials for college viva evaluation.
    """
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('menu:menu_list')
    active_tab = request.GET.get('tab') or request.GET.get('active_tab') or 'customer'

    # If already logged in, redirect sensibly
    if request.user.is_authenticated:
        if hasattr(request.user, 'staff_profile'):
            role = request.user.staff_profile.role
            if role == StaffProfile.ROLE_KITCHEN:
                return redirect('orders:kitchen_dashboard')
            elif role == StaffProfile.ROLE_WAITER:
                return redirect('orders:waiter_dashboard')
            else:
                return redirect('orders:manager_dashboard')
        elif request.user.is_superuser:
            return redirect('orders:manager_dashboard')
        else:
            return redirect(next_url)

    if request.method == 'POST':
        login_type = request.POST.get('login_type', 'customer')

        # ---------------------------------------------------------
        # Case A: Staff Credentials Sign-In
        # ---------------------------------------------------------
        if login_type == 'staff':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')

            user = authenticate(request, username=username, password=password)
            if user is not None:
                if hasattr(user, 'staff_profile') or user.is_superuser:
                    login(request, user)
                    role_name = getattr(user.staff_profile, 'get_role_display', lambda: 'Administrator')() if hasattr(user, 'staff_profile') else 'Administrator'
                    messages.success(request, f"Welcome, {user.get_full_name() or user.username}! ({role_name})")
                    
                    if hasattr(user, 'staff_profile'):
                        if user.staff_profile.role == StaffProfile.ROLE_KITCHEN:
                            return redirect('orders:kitchen_dashboard')
                        elif user.staff_profile.role == StaffProfile.ROLE_WAITER:
                            return redirect('orders:waiter_dashboard')
                    return redirect('orders:manager_dashboard')
                else:
                    messages.error(request, "This account is not configured with staff privileges.")
                    return render(request, 'accounts/google_login.html', {'next': next_url, 'active_tab': 'staff'})
            else:
                messages.error(request, "Invalid username or password.")
                return render(request, 'accounts/google_login.html', {'next': next_url, 'active_tab': 'staff'})

        # ---------------------------------------------------------
        # Case B: Customer Google Sign-In (Direct / Form)
        # ---------------------------------------------------------
        email = request.POST.get('email', '').strip().lower()
        name = request.POST.get('name', '').strip()
        
        if not email or '@' not in email:
            messages.error(request, "Please enter a valid Google email address.")
            return render(request, 'accounts/google_login.html', {
                'next': next_url,
                'active_tab': 'customer',
                'firebase_config': getattr(settings, 'FIREBASE_CONFIG', {})
            })
        
        parts = name.split(None, 1) if name else ['Customer', '']
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''
        google_id = f"goog_{abs(hash(email))}"
        avatar_url = f"https://ui-avatars.com/api/?name={first_name}+{last_name}&background=4285F4&color=fff&size=128"

        # Retrieve existing user with matching email (case-insensitive) or create new
        user = User.objects.filter(email__iexact=email).order_by('-last_login', '-id').first()
        if not user:
            base_username = email.split('@')[0]
            username = base_username
            counter = 1
            while User.objects.filter(username__iexact=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name
            )
            user.set_unusable_password()
            user.save()
        else:
            if not user.first_name and first_name:
                user.first_name = first_name
                user.last_name = last_name
                user.save(update_fields=['first_name', 'last_name'])

        # Update or create customer profile
        customer, _ = Customer.objects.get_or_create(user=user)
        customer.google_id = google_id
        if avatar_url and not customer.avatar_url:
            customer.avatar_url = avatar_url
        customer.save()

        # Log user into Django session
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        messages.success(request, f"Welcome, {customer.name}! Signed in via Google.")

        if hasattr(user, 'staff_profile'):
            role = user.staff_profile.role
            if role == StaffProfile.ROLE_KITCHEN:
                return redirect('orders:kitchen_dashboard')
            elif role == StaffProfile.ROLE_WAITER:
                return redirect('orders:waiter_dashboard')
            else:
                return redirect('orders:manager_dashboard')
        elif user.is_superuser:
            return redirect('orders:manager_dashboard')

        return redirect(next_url)

    return render(request, 'accounts/google_login.html', {
        'next': next_url,
        'active_tab': active_tab,
        'firebase_config': getattr(settings, 'FIREBASE_CONFIG', {})
    })


def staff_login_view(request):
    """
    Unified Staff Login for:
    - Kitchen Manager (Chef)
    - Waiter (Floor Staff)
    - Restaurant Manager (Admin)
    Automatically redirects to the user's role-specific dashboard.
    """
    if request.user.is_authenticated:
        if hasattr(request.user, 'staff_profile'):
            role = request.user.staff_profile.role
            if role == StaffProfile.ROLE_KITCHEN:
                return redirect('orders:kitchen_dashboard')
            elif role == StaffProfile.ROLE_WAITER:
                return redirect('orders:waiter_dashboard')
            else:
                return redirect('orders:manager_dashboard')
        elif request.user.is_superuser:
            return redirect('orders:manager_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if hasattr(user, 'staff_profile') or user.is_superuser:
                login(request, user)
                messages.success(request, f"Logged in as {user.get_full_name() or user.username} ({getattr(user.staff_profile, 'get_role_display', lambda: 'Manager')()})")
                
                # Role redirect
                if hasattr(user, 'staff_profile'):
                    if user.staff_profile.role == StaffProfile.ROLE_KITCHEN:
                        return redirect('orders:kitchen_dashboard')
                    elif user.staff_profile.role == StaffProfile.ROLE_WAITER:
                        return redirect('orders:waiter_dashboard')
                return redirect('orders:manager_dashboard')
            else:
                messages.error(request, "This account does not have staff permissions.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'accounts/staff_login.html')


def logout_view(request):
    """Logs out customer or staff user."""
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('menu:menu_list')


def profile_view(request):
    """Allows customer to view/edit optional contact phone and address."""
    if not request.user.is_authenticated:
        return redirect('accounts:google_login')

    customer, _ = Customer.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        customer.phone = request.POST.get('phone', '').strip()
        customer.address = request.POST.get('address', '').strip()
        customer.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {'customer': customer})
