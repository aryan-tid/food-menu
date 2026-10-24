import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db.models import Avg, Count
from .models import Restaurant, Category, MenuItem, Review
from orders.models import RestaurantTable
from accounts.models import Customer, StaffProfile


def home_view(request):
    """
    Restaurant Landing Page:
    - If staff is logged in: jumps directly to role-specific staff dashboard!
    - If QR scan with ?table=T-01: captures table to session and redirects directly to digital menu.
    - If direct visit: displays high-end hero, how-it-works, category cards, and table selector.
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

    table_param = request.GET.get('table')
    if table_param:
        clean_table = table_param.strip().upper()
        table_obj = RestaurantTable.objects.filter(table_number__iexact=clean_table, is_active=True).first()
        customer = request.user.customer_profile if request.user.is_authenticated and hasattr(request.user, 'customer_profile') else None
        if table_obj and table_obj.is_locked and table_obj.current_customer != customer:
            messages.error(request, f"Table {table_obj.table_number} is currently occupied and locked by another diner. Please talk with a waiter to uplift the lock.")
        else:
            resolved_num = table_obj.table_number if table_obj else clean_table
            request.session['table_id'] = resolved_num
            messages.success(request, f"Welcome! Table {resolved_num} is selected.")
        return redirect('menu:menu_list')

    restaurant = Restaurant.objects.first()
    categories = Category.objects.all().order_by('name')
    featured_items = MenuItem.objects.filter(is_available=True).select_related('category').annotate(
        avg_rating=Avg('reviews__rating'),
        rev_count=Count('reviews')
    )[:6]
    tables = RestaurantTable.objects.filter(is_active=True).order_by('table_number')
    
    current_table_id = request.session.get('table_id')
    current_table = None
    if current_table_id:
        current_table = RestaurantTable.objects.filter(table_number__iexact=str(current_table_id)).first()
    has_table = bool(current_table_id)

    # High-rated customer reviews for social proof
    customer_reviews = Review.objects.select_related('customer', 'menu_item').order_by('-review_date')[:4]
    total_dishes_count = MenuItem.objects.filter(is_available=True).count()

    # Active session check for authenticated diner
    active_session = None
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        from orders.models import DiningSession
        active_session = DiningSession.objects.filter(customer=request.user.customer_profile, is_active=True).first()

    cart = request.session.get('cart', {})

    context = {
        'restaurant': restaurant,
        'categories': categories,
        'featured_items': featured_items,
        'tables': tables,
        'has_table': has_table,
        'current_table': current_table,
        'current_table_number': current_table.table_number if current_table else current_table_id,
        'customer_reviews': customer_reviews,
        'total_dishes_count': total_dishes_count,
        'active_session': active_session,
        'cart': cart,
        'cart_count': sum(cart.values()) if cart else 0,
        'cart_json': json.dumps(cart),
    }
    return render(request, 'menu/home.html', context)


def menu_list_view(request):
    """
    Public Digital Menu View:
    - Captures table query parameter from static QR code (?table=T-01) and saves to session.
    - Displays categorized food items with dynamic filters (Category, Search, Veg/Non-Veg).
    - Publicly accessible to any customer without requiring login.
    """
    # 1. Capture Table from QR Code query param (?table=T-01) if accessed here directly
    table_param = request.GET.get('table')
    if table_param:
        clean_table = table_param.strip().upper()
        table_obj = RestaurantTable.objects.filter(table_number__iexact=clean_table).first()
        if table_obj:
            request.session['table_id'] = table_obj.table_number
        else:
            request.session['table_id'] = clean_table

    current_table_id = request.session.get('table_id')
    current_table = None
    if current_table_id:
        current_table = RestaurantTable.objects.filter(table_number__iexact=str(current_table_id)).first()

    # 2. Filtering Menu Items
    selected_category_id = request.GET.get('category')
    search_query = request.GET.get('q', '').strip()
    veg_only = request.GET.get('veg') == '1'

    items_qs = MenuItem.objects.select_related('category').annotate(
        avg_rating=Avg('reviews__rating'),
        rev_count=Count('reviews')
    ).filter(is_available=True)

    if selected_category_id and selected_category_id.isdigit():
        items_qs = items_qs.filter(category_id=int(selected_category_id))

    if search_query:
        items_qs = items_qs.filter(name__icontains=search_query) | items_qs.filter(description__icontains=search_query)

    if veg_only:
        items_qs = items_qs.filter(is_veg=True)

    categories = Category.objects.all().order_by('name')
    restaurant = Restaurant.objects.first()

    # De-clutter: Group by Category when "All Dishes" is viewed without search
    categorized_menu = []
    if not selected_category_id and not search_query:
        items_list = list(items_qs)
        for cat in categories:
            cat_items = [it for it in items_list if it.category_id == cat.id]
            if cat_items:
                categorized_menu.append({
                    'category': cat,
                    'items': cat_items
                })

    # Pass cart items mapping for inline stepper state
    cart = request.session.get('cart', {})

    context = {
        'restaurant': restaurant,
        'categories': categories,
        'menu_items': items_qs,
        'categorized_menu': categorized_menu if categorized_menu else None,
        'selected_category_id': int(selected_category_id) if selected_category_id and selected_category_id.isdigit() else None,
        'search_query': search_query,
        'veg_only': veg_only,
        'current_table': current_table,
        'current_table_number': current_table.table_number if current_table else current_table_id,
        'cart': cart,
        'cart_count': sum(cart.values()) if cart else 0,
        'cart_json': json.dumps(cart),
    }
    return render(request, 'menu/menu_list.html', context)


def set_table_view(request):
    """
    Allows customer to switch or manually choose their table number.
    Ensures concurrency lock: if a table is locked by another diner,
    selection is blocked and user is prompted to talk with a waiter.
    """
    if request.method == 'POST':
        table_num = request.POST.get('table_number', '').strip().upper()
        if table_num:
            table_obj = RestaurantTable.objects.filter(table_number__iexact=table_num, is_active=True).first()
            customer = request.user.customer_profile if request.user.is_authenticated and hasattr(request.user, 'customer_profile') else None
            if table_obj and table_obj.is_locked and table_obj.current_customer != customer:
                messages.error(
                    request,
                    f"Table {table_obj.table_number} is currently occupied and locked by another diner. "
                    "Please choose an available table or talk with a waiter to uplift the lock."
                )
            else:
                resolved_table_num = table_obj.table_number if table_obj else table_num
                request.session['table_id'] = resolved_table_num
                messages.success(request, f"Table set to {resolved_table_num}.")
        else:
            request.session.pop('table_id', None)
            messages.info(request, "Table cleared. Switched to Takeaway.")
    next_url = request.META.get('HTTP_REFERER') or 'menu:menu_list'
    return redirect(next_url)


def item_detail_view(request, item_id):
    """View details and reviews of a specific menu item."""
    item = get_object_or_404(MenuItem.objects.select_related('category'), pk=item_id)
    reviews = item.reviews.select_related('customer').all()
    user_review = None
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        user_review = reviews.filter(customer=request.user.customer_profile).first()

    return render(request, 'menu/item_detail.html', {
        'item': item,
        'reviews': reviews,
        'user_review': user_review
    })


@login_required
@require_POST
def submit_review_view(request, item_id):
    """
    Module 5: Feedback and Rating Module.
    Allows authenticated customer to submit a star rating (1-5) and review comment.
    Supports both traditional POST redirect and modern AJAX JSON responses.
    """
    item = get_object_or_404(MenuItem, pk=item_id)
    customer, _ = Customer.objects.get_or_create(user=request.user)

    try:
        rating = int(request.POST.get('rating', 5))
        rating = max(1, min(5, rating))
    except (ValueError, TypeError):
        rating = 5

    comment = request.POST.get('comment', '').strip()

    review, _ = Review.objects.update_or_create(
        customer=customer,
        menu_item=item,
        defaults={
            'rating': rating,
            'comment': comment
        }
    )

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('format') == 'json'
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': f"Thank you for rating {item.name} ({rating}★)!",
            'review': {
                'id': review.id,
                'rating': review.rating,
                'comment': review.comment,
                'date': review.review_date.strftime('%d %b %Y'),
                'customer_name': customer.name,
            },
            'average_rating': item.average_rating,
            'review_count': item.review_count,
        })

    messages.success(request, f"Thank you for rating {item.name} ({rating}★)!")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or f"/item/{item.id}/"
    return redirect(next_url)


def api_item_reviews(request, item_id):
    """
    Returns JSON list of reviews for a given menu item, indicating which one is by the current user.
    """
    item = get_object_or_404(MenuItem, pk=item_id)
    reviews = item.reviews.select_related('customer__user').order_by('-review_date')
    current_customer = getattr(request.user, 'customer_profile', None) if request.user.is_authenticated else None

    reviews_data = []
    for r in reviews:
        reviews_data.append({
            'id': r.id,
            'customer_name': r.customer.name,
            'avatar_url': r.customer.avatar_url,
            'rating': r.rating,
            'comment': r.comment,
            'date': r.review_date.strftime('%d %b %Y, %I:%M %p'),
            'is_mine': (current_customer is not None and r.customer_id == current_customer.id),
        })

    return JsonResponse({
        'item_id': item.id,
        'item_name': item.name,
        'average_rating': item.average_rating,
        'review_count': item.review_count,
        'reviews': reviews_data
    })


@login_required
def my_reviews_view(request):
    """
    Customer portal tab: View, edit, and manage all posted reviews.
    """
    customer, _ = Customer.objects.get_or_create(user=request.user)
    user_reviews = Review.objects.filter(customer=customer).select_related('menu_item__category').order_by('-review_date')
    
    return render(request, 'menu/my_reviews.html', {
        'reviews': user_reviews,
        'total_reviews': user_reviews.count(),
    })


@login_required
@require_POST
def edit_review_view(request, review_id):
    """Allows customer to edit their previously posted review."""
    review = get_object_or_404(Review, pk=review_id, customer__user=request.user)
    try:
        rating = int(request.POST.get('rating', review.rating))
        rating = max(1, min(5, rating))
    except (ValueError, TypeError):
        rating = review.rating

    comment = request.POST.get('comment', '').strip()
    if comment:
        review.comment = comment
    review.rating = rating
    review.save()

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('format') == 'json'
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': 'Review updated successfully!',
            'rating': review.rating,
            'comment': review.comment,
        })

    messages.success(request, f"Updated review for {review.menu_item.name}!")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'menu:my_reviews'
    return redirect(next_url)


@login_required
@require_POST
def delete_review_view(request, review_id):
    """Allows customer to delete their own review."""
    review = get_object_or_404(Review, pk=review_id, customer__user=request.user)
    item_name = review.menu_item.name
    review.delete()

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('format') == 'json'
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': f"Review for {item_name} has been deleted."
        })

    messages.success(request, f"Your review for {item_name} was deleted.")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'menu:my_reviews'
    return redirect(next_url)
