from django.contrib import admin
from django.utils.html import format_html
from .models import Restaurant, Category, MenuItem, Review


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name_display', 'phone', 'rating_badge', 'address', 'created_at')
    search_fields = ('name', 'phone', 'address')

    def name_display(self, obj):
        return format_html('<strong>{}</strong>', obj.name)
    name_display.short_description = "Restaurant Name"

    def rating_badge(self, obj):
        return format_html('<span class="badge-pill badge-warning">★ {} / 5.0</span>', obj.rating)
    rating_badge.short_description = "Rating"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name_display', 'restaurant', 'items_count')
    list_filter = ('restaurant',)
    search_fields = ('name',)

    def name_display(self, obj):
        return format_html('<strong>{}</strong>', obj.name)
    name_display.short_description = "Category Name"

    def items_count(self, obj):
        count = obj.items.count()
        return format_html('<span class="badge-pill badge-primary">{} dishes</span>', count)
    items_count.short_description = "Dishes Count"


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('image_thumbnail', 'name_display', 'category', 'price', 'veg_badge', 'is_available', 'reviews_count', 'average_rating')
    list_filter = ('category', 'is_veg', 'is_available')
    search_fields = ('name', 'description')
    list_editable = ('price', 'is_available')
    actions = ['mark_in_stock', 'mark_out_of_stock']

    def image_thumbnail(self, obj):
        url = obj.get_image_url
        return format_html(
            '<img src="{}" style="width: 44px; height: 44px; border-radius: 8px; object-fit: cover; border: 1px solid #e2e8f0;" />',
            url
        )
    image_thumbnail.short_description = "Dish"

    def name_display(self, obj):
        return format_html('<strong>{}</strong>', obj.name)
    name_display.short_description = "Item Name"

    def veg_badge(self, obj):
        if obj.is_veg:
            return format_html('<span class="badge-pill badge-success"><i class="bi bi-record-circle"></i> VEG</span>')
        return format_html('<span class="badge-pill badge-danger"><i class="bi bi-caret-up-square-fill"></i> NON-VEG</span>')
    veg_badge.short_description = "Dietary"

    def reviews_count(self, obj):
        count = obj.reviews.count()
        return format_html('<span class="badge-pill badge-dark">{} reviews</span>', count)
    reviews_count.short_description = "Feedback"

    def mark_in_stock(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f"Marked {updated} items as In Stock.")
    mark_in_stock.short_description = "Mark selected dishes as In Stock"

    def mark_out_of_stock(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f"Marked {updated} items as Out of Stock.")
    mark_out_of_stock.short_description = "Mark selected dishes as Out of Stock"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'menu_item', 'customer', 'stars_display', 'comment_snippet', 'review_date')
    list_filter = ('rating', 'review_date')
    search_fields = ('customer__user__username', 'menu_item__name', 'comment')

    def stars_display(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: #f59e0b; font-weight: bold;">{} ({})</span>', stars, obj.rating)
    stars_display.short_description = "Rating"

    def comment_snippet(self, obj):
        return obj.comment[:60] + "..." if len(obj.comment) > 60 else obj.comment
    comment_snippet.short_description = "Comment"
