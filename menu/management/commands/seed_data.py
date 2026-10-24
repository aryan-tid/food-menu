from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import Customer, StaffProfile
from menu.models import Restaurant, Category, MenuItem, Review
from orders.models import RestaurantTable


class Command(BaseCommand):
    help = 'Seeds initial sample data for the Online Food Menu System (Tables, Staff, Menu Items)'

    def handle(self, *args, **options):
        self.stdout.write("Seeding sample data...")

        # 1. Superuser / Admin
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@foodmenu.com',
                'is_staff': True,
                'is_superuser': True,
                'first_name': 'Restaurant',
                'last_name': 'Owner'
            }
        )
        admin_user.set_password('admin123')
        admin_user.save()
        StaffProfile.objects.get_or_create(
            user=admin_user,
            defaults={'role': StaffProfile.ROLE_MANAGER, 'phone': '+91 9900011100'}
        )

        # 2. Staff: Manager
        manager_user, _ = User.objects.get_or_create(
            username='manager',
            defaults={
                'email': 'manager@foodmenu.com',
                'is_staff': True,
                'first_name': 'Rajesh',
                'last_name': 'Sharma'
            }
        )
        manager_user.set_password('manager123')
        manager_user.save()
        StaffProfile.objects.update_or_create(
            user=manager_user,
            defaults={'role': StaffProfile.ROLE_MANAGER, 'phone': '+91 9822334455'}
        )

        # 3. Staff: Waiter
        waiter_user, _ = User.objects.get_or_create(
            username='waiter',
            defaults={
                'email': 'waiter@foodmenu.com',
                'is_staff': True,
                'first_name': 'Ramesh',
                'last_name': 'Kadam'
            }
        )
        waiter_user.set_password('waiter123')
        waiter_user.save()
        StaffProfile.objects.update_or_create(
            user=waiter_user,
            defaults={'role': StaffProfile.ROLE_WAITER, 'phone': '+91 9822445566'}
        )

        # 4. Staff: Kitchen Manager
        kitchen_user, _ = User.objects.get_or_create(
            username='kitchen',
            defaults={
                'email': 'chef@foodmenu.com',
                'is_staff': True,
                'first_name': 'Chef Sanjeev',
                'last_name': 'Patil'
            }
        )
        kitchen_user.set_password('kitchen123')
        kitchen_user.save()
        StaffProfile.objects.update_or_create(
            user=kitchen_user,
            defaults={'role': StaffProfile.ROLE_KITCHEN, 'phone': '+91 9822556677'}
        )

        # 5. Customer: Demo User (Google Demo)
        customer_user, _ = User.objects.get_or_create(
            username='siddhivinayak',
            defaults={
                'email': 'siddhi@gmail.com',
                'first_name': 'Siddhivinayak',
                'last_name': 'Tidake'
            }
        )
        customer_user.set_password('customer123')
        customer_user.save()

        Customer.objects.update_or_create(
            user=customer_user,
            defaults={
                'phone': '+91 9876543210',
                'address': 'Hostel Block B, COCSIT Campus, Latur',
                'avatar_url': 'https://lh3.googleusercontent.com/a/default-user=s96-c'
            }
        )

        # 6. Restaurant Tables (T-01 to T-06)
        tables = [
            ("T-01", 2),
            ("T-02", 4),
            ("T-03", 4),
            ("T-04", 6),
            ("T-05", 2),
            ("T-06", 8),
        ]
        for tbl_num, cap in tables:
            RestaurantTable.objects.get_or_create(
                table_number=tbl_num,
                defaults={'capacity': cap, 'is_active': True, 'is_locked': False}
            )

        # 7. Restaurant Details
        restaurant, _ = Restaurant.objects.get_or_create(
            name="Spice Garden Multi-Cuisine",
            defaults={
                'address': "Main Road, Near COCSIT College, Latur, Maharashtra - 413512",
                'phone': "+91 9822001122",
                'rating': 4.8
            }
        )

        # 8. Categories & Menu Items
        categories_data = [
            ("Starters", "Crispy appetizers, tandoori treats, and savory finger foods."),
            ("Main Course", "Hearty curries, rich gravies, and delicious regional specialties."),
            ("Breads & Rice", "Fresh clay oven baked breads, rotis, and aromatic dum biryanis."),
            ("Beverages", "Refreshing mocktails, chilled shakes, and juices."),
            ("Desserts", "Sweet delicacies and ice cream treats.")
        ]

        cat_objs = {}
        for cat_name, desc in categories_data:
            cat, _ = Category.objects.get_or_create(
                restaurant=restaurant,
                name=cat_name,
                defaults={'description': desc}
            )
            cat_objs[cat_name] = cat

        menu_items_data = [
            {"category": cat_objs["Starters"], "name": "Paneer Tikka Angara", "description": "Charcoal grilled cottage cheese in fiery spices.", "price": 240.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Starters"], "name": "Crispy Veg Spring Rolls", "description": "Crispy golden rolls filled with seasoned vegetables.", "price": 180.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Starters"], "name": "Murgh Malai Tikka", "description": "Succulent chicken chunks marinated in cream, cheese & spices.", "price": 320.00, "is_veg": False, "is_available": True},
            {"category": cat_objs["Main Course"], "name": "Paneer Butter Masala", "description": "Cottage cheese in rich buttery tomato cashew gravy.", "price": 280.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Main Course"], "name": "Dal Makhani", "description": "Slow cooked black lentils simmered overnight with butter.", "price": 220.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Main Course"], "name": "Butter Chicken Punjabi", "description": "Tender tandoori chicken cooked in creamy tomato sauce.", "price": 350.00, "is_veg": False, "is_available": True},
            {"category": cat_objs["Breads & Rice"], "name": "Butter Garlic Naan", "description": "Clay oven naan with melted butter and fresh garlic.", "price": 60.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Breads & Rice"], "name": "Hyderabadi Veg Dum Biryani", "description": "Aromatic basmati rice layered with vegetables & saffron.", "price": 260.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Breads & Rice"], "name": "Chicken Dum Biryani", "description": "Layered basmati rice with tender spiced chicken.", "price": 340.00, "is_veg": False, "is_available": True},
            {"category": cat_objs["Beverages"], "name": "Mint Mojito", "description": "Chilled drink with fresh crushed mint, lime, and soda.", "price": 120.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Beverages"], "name": "Mango Lassi", "description": "Thick sweet yogurt blended with Alphonso mango pulp.", "price": 110.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Desserts"], "name": "Gulab Jamun with Ice Cream", "description": "Hot golden milk dumplings with cold vanilla ice cream.", "price": 130.00, "is_veg": True, "is_available": True},
            {"category": cat_objs["Desserts"], "name": "Sizzling Brownie", "description": "Hot chocolate brownie on sizzler plate with vanilla ice cream.", "price": 190.00, "is_veg": True, "is_available": True}
        ]

        for item_data in menu_items_data:
            MenuItem.objects.get_or_create(
                category=item_data["category"],
                name=item_data["name"],
                defaults={
                    "description": item_data["description"],
                    "price": item_data["price"],
                    "is_veg": item_data["is_veg"],
                    "is_available": item_data["is_available"]
                }
            )

        self.stdout.write(self.style.SUCCESS("Database seeded successfully with Staff, Tables, and Menu!"))
