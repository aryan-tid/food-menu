from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import Customer


class Restaurant(models.Model):
    """
    Restaurant entity corresponding to ER Diagram:
    Attributes: restaurant_id (PK), name, address, phone, rating
    """
    name = models.CharField(max_length=150)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=4.50,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'restaurant'
        verbose_name = 'Restaurant'
        verbose_name_plural = 'Restaurants'

    def __str__(self):
        return self.name


class Category(models.Model):
    """
    Category entity corresponding to ER Diagram:
    Attributes: category_id (PK), restaurant (FK), name, description
    """
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'category'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    """
    MenuItem entity corresponding to ER Diagram:
    Attributes: item_id (PK), category (FK), name, description, price, image
    Additional practical fields: is_veg, is_available
    """
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0.01)])
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True, help_text="Upload dish photo (optional)")
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Direct image URL (optional)")
    is_veg = models.BooleanField(default=True, help_text="True for Vegetarian, False for Non-Vegetarian")
    is_available = models.BooleanField(default=True, help_text="Stock availability status")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'menu_item'
        verbose_name = 'Menu Item'
        verbose_name_plural = 'Menu Items'
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} - ₹{self.price}"

    @property
    def get_image_url(self):
        """
        Returns uploaded image URL if exists, else returns a high-quality,
        appetizing category-specific curated food photo.
        """
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass

        if self.image_url and self.image_url.strip():
            return self.image_url.strip()

        name_lower = self.name.lower()
        cat_lower = self.category.name.lower() if self.category else ""

        # 1. Specific dish name matches (highest priority)
        if 'jamun' in name_lower or 'gulab' in name_lower or 'rasgulla' in name_lower or 'kulfi' in name_lower or 'halwa' in name_lower or 'sweet' in name_lower:
            return "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=600&auto=format&fit=crop&q=80"
        elif 'lassi' in name_lower or 'mojito' in name_lower or 'shake' in name_lower or 'soda' in name_lower or 'juice' in name_lower or 'tea' in name_lower or 'coffee' in name_lower:
            return "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?w=600&auto=format&fit=crop&q=80"
        elif 'paneer' in name_lower or 'kadai' in name_lower or 'curry' in name_lower or 'gravy' in name_lower or 'dal' in name_lower:
            return "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=600&auto=format&fit=crop&q=80"
        elif 'biryani' in name_lower or 'pulao' in name_lower or 'rice' in name_lower or 'jeera' in name_lower:
            return "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=600&auto=format&fit=crop&q=80"
        elif 'tikka' in name_lower or 'tandoor' in name_lower or 'kebab' in name_lower or 'manchurian' in name_lower or 'spring roll' in name_lower:
            return "https://images.unsplash.com/photo-1599488615731-7e5c2823ff28?w=600&auto=format&fit=crop&q=80"
        elif 'naan' in name_lower or 'roti' in name_lower or 'paratha' in name_lower or 'kulcha' in name_lower:
            return "https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?w=600&auto=format&fit=crop&q=80"
        elif 'pizza' in name_lower:
            return "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=600&auto=format&fit=crop&q=80"
        elif 'burger' in name_lower or 'sandwich' in name_lower:
            return "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=600&auto=format&fit=crop&q=80"

        # 2. Category-level fallbacks if dish name wasn't matched
        if 'dessert' in cat_lower or 'sweet' in cat_lower:
            return "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=600&auto=format&fit=crop&q=80"
        elif 'beverage' in cat_lower or 'drink' in cat_lower:
            return "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?w=600&auto=format&fit=crop&q=80"
        elif 'starter' in cat_lower or 'appetizer' in cat_lower:
            return "https://images.unsplash.com/photo-1599488615731-7e5c2823ff28?w=600&auto=format&fit=crop&q=80"
        elif 'bread' in cat_lower:
            return "https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?w=600&auto=format&fit=crop&q=80"
        elif 'rice' in cat_lower or 'biryani' in cat_lower:
            return "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=600&auto=format&fit=crop&q=80"
        
        # General culinary fallback
        return "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&auto=format&fit=crop&q=80"

    @property
    def average_rating(self):
        avg = self.reviews.aggregate(models.Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else None

    @property
    def review_count(self):
        return self.reviews.count()


class Review(models.Model):
    """
    Review entity corresponding to ER Diagram:
    Attributes: review_id (PK), customer (FK), menu_item (FK), rating, comment, review_date
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='reviews')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        choices=[(i, f"{i} Stars") for i in range(1, 6)],
        default=5
    )
    comment = models.TextField()
    review_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'review'
        verbose_name = 'Review'
        verbose_name_plural = 'Reviews'
        ordering = ['-review_date']

    def __str__(self):
        return f"Review by {self.customer.name} on {self.menu_item.name} ({self.rating}★)"
