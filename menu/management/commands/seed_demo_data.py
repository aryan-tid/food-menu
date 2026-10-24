import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User

from accounts.models import Customer, StaffProfile
from menu.models import Restaurant, Category, MenuItem, Review
from orders.models import (
    RestaurantTable,
    DiningSession,
    Order,
    OrderItem,
    Payment,
    WaiterAlert
)


class Command(BaseCommand):
    help = 'Seeds full realistic demo data (Menu, Customers, Staff, Tables, Orders, Payments, Reviews) with optional database reset.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Wipes all existing business data (orders, menu items, reviews, tables, customers, non-superuser staff) before seeding.'
        )

    def handle(self, *args, **options):
        clear_existing = options.get('clear', False)

        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE("  🍽️  RESTAURANT DEMO DATA SEEDER"))
        self.stdout.write(self.style.NOTICE("=" * 70))

        with transaction.atomic():
            if clear_existing:
                self.stdout.write(self.style.WARNING("--> Clearing existing application data..."))
                WaiterAlert.objects.all().delete()
                Payment.objects.all().delete()
                OrderItem.objects.all().delete()
                Order.objects.all().delete()
                DiningSession.objects.all().delete()
                RestaurantTable.objects.all().delete()
                Review.objects.all().delete()
                MenuItem.objects.all().delete()
                Category.objects.all().delete()
                Restaurant.objects.all().delete()
                Customer.objects.all().delete()
                StaffProfile.objects.all().delete()
                
                # Delete existing demo/test users (keep superusers or recreate)
                demo_usernames = [
                    'manager', 'waiter', 'waiter2', 'waiter3',
                    'kitchen', 'chef2', 'siddhivinayak', 'aditi_s',
                    'rohit_v', 'neha_k', 'arjun_m', 'priya_d',
                    'karan_j', 'tanvi_p'
                ]
                User.objects.filter(username__in=demo_usernames).delete()
                self.stdout.write(self.style.SUCCESS("--> ✅ Old data cleared successfully."))

            # -------------------------------------------------------------
            # 1. Restaurant Setup
            # -------------------------------------------------------------
            self.stdout.write("--> Setting up Restaurant profile...")
            restaurant, _ = Restaurant.objects.get_or_create(
                id=1,
                defaults={
                    'name': 'Royal Spice Multi-Cuisine & Fine Dine',
                    'address': 'Plot 42, Heritage Boulevard, Civil Lines, Latur, Maharashtra - 413512',
                    'phone': '+91 9822001122',
                    'rating': Decimal('4.85')
                }
            )
            restaurant.name = 'Royal Spice Multi-Cuisine & Fine Dine'
            restaurant.address = 'Plot 42, Heritage Boulevard, Civil Lines, Latur, Maharashtra - 413512'
            restaurant.phone = '+91 9822001122'
            restaurant.rating = Decimal('4.85')
            restaurant.save()

            # -------------------------------------------------------------
            # 2. Staff Accounts
            # -------------------------------------------------------------
            self.stdout.write("--> Creating Staff Accounts (Admin, Manager, Waiters, Kitchen Chefs)...")

            # A. Admin / Superuser
            admin_user, _ = User.objects.get_or_create(
                username='admin',
                defaults={
                    'email': 'admin@royalspice.com',
                    'is_staff': True,
                    'is_superuser': True,
                    'first_name': 'Restaurant',
                    'last_name': 'Owner'
                }
            )
            admin_user.set_password('admin123')
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save()
            StaffProfile.objects.update_or_create(
                user=admin_user,
                defaults={'role': StaffProfile.ROLE_MANAGER, 'phone': '+91 9900011100'}
            )

            # B. Restaurant Manager
            manager_user, _ = User.objects.get_or_create(
                username='manager',
                defaults={
                    'email': 'manager@royalspice.com',
                    'is_staff': True,
                    'first_name': 'Rajesh',
                    'last_name': 'Sharma'
                }
            )
            manager_user.set_password('manager123')
            manager_user.is_staff = True
            manager_user.save()
            StaffProfile.objects.update_or_create(
                user=manager_user,
                defaults={'role': StaffProfile.ROLE_MANAGER, 'phone': '+91 9822334455'}
            )

            # C. Waiters (Floor Staff)
            waiter_creds = [
                ('waiter', 'waiter123', 'Ramesh', 'Kadam', 'ramesh.waiter@royalspice.com', '+91 9822445566'),
                ('waiter2', 'waiter123', 'Pooja', 'Patil', 'pooja.waiter@royalspice.com', '+91 9822445577'),
                ('waiter3', 'waiter123', 'Anil', 'Shinde', 'anil.waiter@royalspice.com', '+91 9822445588'),
            ]
            waiter_objs = []
            for u_name, pwd, f_name, l_name, email, phone in waiter_creds:
                w_user, _ = User.objects.get_or_create(
                    username=u_name,
                    defaults={'email': email, 'is_staff': True, 'first_name': f_name, 'last_name': l_name}
                )
                w_user.set_password(pwd)
                w_user.is_staff = True
                w_user.first_name = f_name
                w_user.last_name = l_name
                w_user.save()
                StaffProfile.objects.update_or_create(
                    user=w_user,
                    defaults={'role': StaffProfile.ROLE_WAITER, 'phone': phone}
                )
                waiter_objs.append(w_user)

            # D. Kitchen Managers / Chefs
            kitchen_creds = [
                ('kitchen', 'kitchen123', 'Chef Sanjeev', 'Patil', 'chef.sanjeev@royalspice.com', '+91 9822556677'),
                ('chef2', 'kitchen123', 'Chef Vikas', 'Khanna', 'chef.vikas@royalspice.com', '+91 9822556688'),
            ]
            for u_name, pwd, f_name, l_name, email, phone in kitchen_creds:
                k_user, _ = User.objects.get_or_create(
                    username=u_name,
                    defaults={'email': email, 'is_staff': True, 'first_name': f_name, 'last_name': l_name}
                )
                k_user.set_password(pwd)
                k_user.is_staff = True
                k_user.first_name = f_name
                k_user.last_name = l_name
                k_user.save()
                StaffProfile.objects.update_or_create(
                    user=k_user,
                    defaults={'role': StaffProfile.ROLE_KITCHEN, 'phone': phone}
                )

            # -------------------------------------------------------------
            # 3. Customer Accounts & Profiles
            # -------------------------------------------------------------
            self.stdout.write("--> Creating Customer Accounts...")
            customers_data = [
                ('siddhivinayak', 'customer123', 'Siddhivinayak', 'Tidake', 'siddhivinayaktidake04@gmail.com', '+91 9876543210', 'Hostel Block B, COCSIT Campus, Latur', 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150&auto=format&fit=crop&q=80'),
                ('aditi_s', 'customer123', 'Aditi', 'Sharma', 'aditi.sharma@example.com', '+91 9823123456', 'Kothrud, Pune, Maharashtra', 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150&auto=format&fit=crop&q=80'),
                ('rohit_v', 'customer123', 'Rohit', 'Verma', 'rohit.verma@example.com', '+91 9834567890', 'Andheri West, Mumbai, Maharashtra', 'https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=150&auto=format&fit=crop&q=80'),
                ('neha_k', 'customer123', 'Neha', 'Kulkarni', 'neha.k@example.com', '+91 9845671234', 'Jubilee Hills, Hyderabad, Telangana', 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=150&auto=format&fit=crop&q=80'),
                ('arjun_m', 'customer123', 'Arjun', 'Mehta', 'arjun.mehta@example.com', '+91 9856782345', 'Indiranagar, Bangalore, Karnataka', 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80'),
                ('priya_d', 'customer123', 'Priya', 'Deshmukh', 'priya.deshmukh@example.com', '+91 9867893456', 'Aadarsh Nagar, Latur, Maharashtra', 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=150&auto=format&fit=crop&q=80'),
                ('karan_j', 'customer123', 'Karan', 'Joshi', 'karan.joshi@example.com', '+91 9878904567', 'College Road, Nashik, Maharashtra', 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150&auto=format&fit=crop&q=80'),
                ('tanvi_p', 'customer123', 'Tanvi', 'Pawar', 'tanvi.pawar@example.com', '+91 9889015678', 'Cidco, Chhatrapati Sambhajinagar', 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80'),
            ]

            customer_map = {}
            for u_name, pwd, f_name, l_name, email, phone, addr, avatar in customers_data:
                u, _ = User.objects.get_or_create(
                    username=u_name,
                    defaults={'email': email, 'first_name': f_name, 'last_name': l_name}
                )
                u.set_password(pwd)
                u.first_name = f_name
                u.last_name = l_name
                u.save()

                c_prof, _ = Customer.objects.update_or_create(
                    user=u,
                    defaults={'phone': phone, 'address': addr, 'avatar_url': avatar}
                )
                customer_map[u_name] = c_prof

            # -------------------------------------------------------------
            # 4. Dining Tables
            # -------------------------------------------------------------
            self.stdout.write("--> Setting up Restaurant Tables...")
            tables_data = [
                ("T-01", 2),
                ("T-02", 2),
                ("T-03", 4),
                ("T-04", 4),
                ("T-05", 4),
                ("T-06", 6),
                ("T-07", 6),
                ("T-08", 8),
                ("VIP-1", 4),
                ("VIP-2", 6),
                ("Terrace-1", 4),
                ("Terrace-2", 6),
            ]
            table_objs = {}
            for t_num, cap in tables_data:
                tbl, _ = RestaurantTable.objects.update_or_create(
                    table_number=t_num,
                    defaults={'capacity': cap, 'is_active': True, 'is_locked': False, 'current_customer': None}
                )
                table_objs[t_num] = tbl

            # -------------------------------------------------------------
            # 5. Categories & Menu Items
            # -------------------------------------------------------------
            self.stdout.write("--> Creating Menu Categories and 40+ authentic dishes...")
            categories_def = [
                ("Starters & Appetizers", "Crispy appetizers, sizzling tandoori treats, and savory finger foods."),
                ("Main Course - Veg", "Rich traditional gravies, slow-simmered dals, and paneer delicacies."),
                ("Main Course - Non-Veg", "Clay-oven roasted chicken gravies, royal mutton rogan josh, and coastal seafood."),
                ("Tandoori Breads & Biryanis", "Aromatic dum-cooked basmati biryanis, fresh clay oven tandoori rotis, and naans."),
                ("Desserts & Delicacies", "Decadent Indian mithais, ice cream sundaes, and sizzling hot brownies."),
                ("Beverages & Mocktails", "Chilled tropical mocktails, creamy lassis, and hot gourmet brews.")
            ]

            cat_objs = {}
            for cat_name, cat_desc in categories_def:
                c, _ = Category.objects.get_or_create(
                    restaurant=restaurant,
                    name=cat_name,
                    defaults={'description': cat_desc}
                )
                cat_objs[cat_name] = c

            items_def = [
                # Starters & Appetizers
                ("Starters & Appetizers", "Paneer Tikka Angara", "Charcoal-grilled cottage cheese cubes marinated in fiery tandoori spices and mustard oil.", Decimal('260.00'), True, "https://images.unsplash.com/photo-1599488615731-7e5c2823ff28?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Crispy Corn Salt & Pepper", "Tender sweet corn tossed with freshly cracked black pepper, scallions, and roasted garlic.", Decimal('190.00'), True, "https://images.unsplash.com/photo-1551782450-a2132b4ba21d?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Crispy Veg Spring Rolls", "Golden crunchy rolls stuffed with shredded vegetables, served with sweet chili dip.", Decimal('180.00'), True, "https://images.unsplash.com/photo-1544025162-d76694265947?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Hara Bhara Kebab", "Delicate pan-fried patties crafted with fresh spinach, green peas, mashed potatoes, and herbs.", Decimal('210.00'), True, "https://images.unsplash.com/photo-1601050690597-df0568f70950?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Dahi Ke Kebab", "Melt-in-the-mouth shallow fried kebabs made with hung curd, paneer, cardamom, and fresh coriander.", Decimal('230.00'), True, "https://images.unsplash.com/photo-1567188040759-fb8a883dc6d8?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Murgh Malai Tikka", "Succulent chicken chunks marinated in heavy cream, hung curd, cheese, and crushed green cardamom.", Decimal('330.00'), False, "https://images.unsplash.com/photo-1610057099443-fde8c4d50f91?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Tandoori Chicken (Half)", "Classic tandoor-roasted chicken with bone, marinated in hung curd, Kashmiri deggi mirch, and ginger.", Decimal('290.00'), False, "https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Chicken Seekh Kebab", "Juicy minced chicken infused with roasted cumin, mint, ginger, and skewered to perfection over coals.", Decimal('310.00'), False, "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Chilli Chicken Dry", "Wok-tossed battered crispy chicken cubes tossed with diced bell peppers, onions, and spicy soya glaze.", Decimal('280.00'), False, "https://images.unsplash.com/photo-1562967914-608f82629710?w=800&auto=format&fit=crop&q=80"),
                ("Starters & Appetizers", "Amritsari Fish Tikka", "Fresh fish fillets dipped in carom seed (ajwain) and gram flour batter, deep fried until crisp.", Decimal('360.00'), False, "https://images.unsplash.com/photo-1534422298391-e4f8c172dddb?w=800&auto=format&fit=crop&q=80"),

                # Main Course - Veg
                ("Main Course - Veg", "Paneer Butter Masala", "Soft cottage cheese simmered in a velvet-smooth, buttery tomato and cashew nut gravy.", Decimal('280.00'), True, "https://images.unsplash.com/photo-1631452180519-c014fe946bc7?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Veg", "Dal Makhani", "Slow-cooked black lentils and kidney beans simmered overnight on slow charcoal with churned butter.", Decimal('240.00'), True, "https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Veg", "Dal Tadka Double Rassa", "Yellow toor dal tempered with roasted cumin seeds, garlic, dried red chilies, and pure ghee.", Decimal('190.00'), True, "https://images.unsplash.com/photo-1585937421612-70a008356fbe?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Veg", "Kadai Paneer Special", "Cottage cheese and crunchy bell peppers tossed in a rustic freshly ground coriander-chili spice mix.", Decimal('290.00'), True, "https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Veg", "Shahi Malai Kofta", "Dumplings made of paneer and dry fruits bathed in a royal cashew and fresh cream gravy.", Decimal('295.00'), True, "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Veg", "Veg Kolhapuri Spicy", "Medley of seasonal vegetables cooked in a spicy, roasted coconut and red chili Kolhapuri masala.", Decimal('240.00'), True, "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Veg", "Mushroom Masala", "Fresh button mushrooms cooked with caramelized onion, tomato gravy, and aromatic whole garam masalas.", Decimal('270.00'), True, "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Veg", "Palak Paneer", "Fresh spinach purée mildly spiced with roasted garlic and cooked with soft paneer cubes.", Decimal('260.00'), True, "https://images.unsplash.com/photo-1613292443284-8d10ef9383fe?w=800&auto=format&fit=crop&q=80"),

                # Main Course - Non-Veg
                ("Main Course - Non-Veg", "Butter Chicken Punjabi", "Tender tandoor-roasted chicken pieces cooked in our legendary sweet and tangy buttery tomato gravy.", Decimal('360.00'), False, "https://images.unsplash.com/photo-1588166524941-3bf61a9c41db?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Non-Veg", "Mutton Rogan Josh Kashmiri", "Slow-braised lamb shanks cooked with Kashmiri chilies, mace, fennel powder, and ratan jot.", Decimal('460.00'), False, "https://images.unsplash.com/photo-1545247181-516773cae754?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Non-Veg", "Chicken Tikka Lababdar", "Charcoal-grilled chicken tikka finished in a rich, chunky onion-tomato gravy with grated paneer.", Decimal('350.00'), False, "https://images.unsplash.com/photo-1606471191009-63994c53433b?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Non-Veg", "Chicken Sukka Saoji", "Traditional Vidarbha specialty: fiery dry chicken roasted with toasted poppy seeds and black pepper.", Decimal('340.00'), False, "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Non-Veg", "Malabar Fish Curry", "Tender fish steaks gently simmered in a mildly spiced coconut milk gravy with fresh curry leaves.", Decimal('390.00'), False, "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?w=800&auto=format&fit=crop&q=80"),
                ("Main Course - Non-Veg", "Homestyle Egg Curry", "Boiled fried eggs simmered in a hearty onion-tomato masala flavored with crushed peppercorns.", Decimal('210.00'), False, "https://images.unsplash.com/photo-1582878826629-29b7ad1cdc43?w=800&auto=format&fit=crop&q=80"),

                # Tandoori Breads & Biryanis
                ("Tandoori Breads & Biryanis", "Butter Garlic Naan", "Clay oven baked refined flour bread topped with minced roasted garlic, coriander, and churned butter.", Decimal('65.00'), True, "https://images.unsplash.com/photo-1601050690597-df0568f70950?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Cheese Garlic Naan", "Stuffed with melted mozzarella cheese, garlic, and fresh herbs, baked until golden blistered.", Decimal('90.00'), True, "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Tandoori Butter Roti", "Whole wheat flatbread baked directly on the clay oven walls and brushed with pure amul butter.", Decimal('30.00'), True, "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Laccha Paratha", "Flaky multi-layered whole wheat bread baked in tandoor with crispy edges and soft layers.", Decimal('50.00'), True, "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Hyderabadi Veg Dum Biryani", "Aromatic aged basmati rice layered with seasoned vegetables, saffron milk, and fried onions.", Decimal('270.00'), True, "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Hyderabadi Chicken Dum Biryani", "Royal kacchi dum biryani featuring tender marinated chicken, saffron, mint, and long-grain rice.", Decimal('350.00'), False, "https://images.unsplash.com/photo-1589302168068-964664d93dc0?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Lucknowi Mutton Dum Biryani", "Awadhi dum biryani with fragrant rose water, mace, aromatic spices, and tender baby goat meat.", Decimal('440.00'), False, "https://images.unsplash.com/photo-1633945274405-b6c8069047b0?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Jeera Rice with Fried Onions", "Steamed basmati rice tempered with golden roasted cumin seeds and topped with crispy fried onions.", Decimal('160.00'), True, "https://images.unsplash.com/photo-1536304993881-ff6e9eefa2a6?w=800&auto=format&fit=crop&q=80"),
                ("Tandoori Breads & Biryanis", "Steamed Basmati Rice", "Fluffy long-grain premium fragrant basmati rice.", Decimal('120.00'), True, "https://images.unsplash.com/photo-1516684732162-798a0062be99?w=800&auto=format&fit=crop&q=80"),

                # Desserts & Delicacies
                ("Desserts & Delicacies", "Gulab Jamun with Ice Cream", "Warm khoya dumplings soaked in saffron-rose syrup, served with creamy chilled vanilla bean ice cream.", Decimal('140.00'), True, "https://images.unsplash.com/photo-1589119908995-c6837fa14d48?w=800&auto=format&fit=crop&q=80"),
                ("Desserts & Delicacies", "Sizzling Hot Brownie with Vanilla", "Fudgy walnut brownie served on a piping hot cast-iron sizzler with vanilla ice cream and chocolate sauce.", Decimal('195.00'), True, "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=800&auto=format&fit=crop&q=80"),
                ("Desserts & Delicacies", "Royal Kesar Rasmalai (2 pcs)", "Delicate flattened cottage cheese discs steeped in thickened saffron and pistachio milk.", Decimal('150.00'), True, "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=800&auto=format&fit=crop&q=80"),
                ("Desserts & Delicacies", "Kulfi Falooda Royal", "Traditional malai kulfi sliced over chilled falooda noodles, sabja seeds, and rose syrup.", Decimal('160.00'), True, "https://images.unsplash.com/photo-1563805042-7684c019e1cb?w=800&auto=format&fit=crop&q=80"),
                ("Desserts & Delicacies", "Molten Chocolate Lava Cake", "Warm baked chocolate sponge with a luscious molten cocoa center, dusted with icing sugar.", Decimal('180.00'), True, "https://images.unsplash.com/photo-1624353365286-3f8d62daad51?w=800&auto=format&fit=crop&q=80"),
                ("Desserts & Delicacies", "Matka Rabdi Kheer", "Slow-reduced creamy rice pudding enriched with slivered almonds, pistachios, and saffron.", Decimal('130.00'), True, "https://images.unsplash.com/photo-1579954115545-a95591f28bfc?w=800&auto=format&fit=crop&q=80"),

                # Beverages & Mocktails
                ("Beverages & Mocktails", "Royal Mango Lassi", "Thick churned creamy yogurt blended with sweet Ratnagiri Alphonso mango pulp and cardamom.", Decimal('120.00'), True, "https://images.unsplash.com/photo-1571006687898-3bfd4b4a1b02?w=800&auto=format&fit=crop&q=80"),
                ("Beverages & Mocktails", "Virgin Mint Mojito", "Muddled fresh mint sprigs, tangy Persian lime chunks, and cane sugar charged with bubbly club soda.", Decimal('130.00'), True, "https://images.unsplash.com/photo-1551538827-9c037cb4f32a?w=800&auto=format&fit=crop&q=80"),
                ("Beverages & Mocktails", "Blue Lagoon Fizz", "Vibrant blue curacao syrup, lemon juice, sprite, and crushed ice garnished with a lemon wheel.", Decimal('140.00'), True, "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?w=800&auto=format&fit=crop&q=80"),
                ("Beverages & Mocktails", "Fresh Lime Soda (Sweet & Salt)", "Freshly squeezed lime juice with balanced sweet syrup and rock salt, topped with chilled soda.", Decimal('80.00'), True, "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?w=800&auto=format&fit=crop&q=80"),
                ("Beverages & Mocktails", "Cold Coffee with Ice Cream", "Rich espresso shaken with chilled milk and topped with a scoop of chocolate vanilla swirl.", Decimal('150.00'), True, "https://images.unsplash.com/photo-1517701550927-30cf4ba1dba5?w=800&auto=format&fit=crop&q=80"),
                ("Beverages & Mocktails", "Peach Iced Tea", "Brewed black tea infused with natural peach nectar and served over cracked ice cubes.", Decimal('110.00'), True, "https://images.unsplash.com/photo-1499638673689-79a0b5115d87?w=800&auto=format&fit=crop&q=80"),
                ("Beverages & Mocktails", "Masala Buttermilk (Chaas)", "Light spiced buttermilk churned with roasted cumin, rock salt, ginger, and fresh mint leaves.", Decimal('60.00'), True, "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=800&auto=format&fit=crop&q=80"),
                ("Beverages & Mocktails", "Kadak Masala Cutting Chai", "Strong aromatic tea boiled with crushed green cardamom, cloves, ginger, and buffalo milk.", Decimal('40.00'), True, "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=800&auto=format&fit=crop&q=80"),
            ]

            menu_item_objs = {}
            for cat_name, item_name, desc, price, is_veg, img_url in items_def:
                item, _ = MenuItem.objects.get_or_create(
                    category=cat_objs[cat_name],
                    name=item_name,
                    defaults={
                        'description': desc,
                        'price': price,
                        'is_veg': is_veg,
                        'is_available': True,
                        'image_url': img_url
                    }
                )
                item.description = desc
                item.price = price
                item.is_veg = is_veg
                item.image_url = img_url
                item.save(update_fields=['description', 'price', 'is_veg', 'image_url'])
                menu_item_objs[item_name] = item

            # -------------------------------------------------------------
            # 6. Customer Ratings & Reviews (25+ authentic reviews)
            # -------------------------------------------------------------
            self.stdout.write("--> Creating authentic Customer Reviews...")
            reviews_def = [
                ('siddhivinayak', "Butter Chicken Punjabi", 5, "Hands down the best Butter Chicken in Latur! The gravy is so creamy, perfectly balanced, and the chicken melts in your mouth."),
                ('aditi_s', "Dal Makhani", 5, "Authentic slow-cooked Dal Makhani. You can really taste the overnight simmered flavor and the richness of butter. Highly recommended!"),
                ('rohit_v', "Paneer Tikka Angara", 5, "Superb smoky aroma and generous portion size. The paneer was incredibly soft. Loved the mint chutney served with it."),
                ('neha_k', "Hyderabadi Chicken Dum Biryani", 5, "As someone from Hyderabad, I can vouch for the authenticity of this biryani! Long grain basmati, succulent chicken, and perfect spice balance."),
                ('arjun_m', "Butter Garlic Naan", 5, "The garlic naan was fresh, soft inside with crispy edges. Best companion with Dal Makhani and Butter Chicken."),
                ('priya_d', "Sizzling Hot Brownie with Vanilla", 5, "The sizzling brownie is pure bliss! The hot chocolate sauce on the cold vanilla ice cream made our dinner unforgettable."),
                ('karan_j', "Mutton Rogan Josh Kashmiri", 5, "Magnificent Rogan Josh. The meat fell off the bone effortlessly and the Kashmiri spice blend is top notch."),
                ('tanvi_p', "Royal Mango Lassi", 5, "Thick, rich, and truly Alphonso mango flavor. Not overly sweet, just perfect."),
                ('siddhivinayak', "Virgin Mint Mojito", 5, "Very refreshing drink to start your dinner with. Plentiful mint and lime!"),
                ('aditi_s', "Kadai Paneer Special", 4, "Crunchy capsicum and aromatic freshly pounded spices. Went wonderfully with the Laccha Paratha."),
                ('rohit_v', "Crispy Corn Salt & Pepper", 5, "Crispy and addictive! Everyone at the table couldn't stop snacking on this."),
                ('neha_k', "Gulab Jamun with Ice Cream", 5, "Hot gulab jamun with cold vanilla ice cream is a timeless dessert. They do it best here."),
                ('arjun_m', "Murgh Malai Tikka", 5, "Creamy, juicy, and mildly spiced. Extremely good for kids and adults alike."),
                ('priya_d', "Cheese Garlic Naan", 5, "So much cheese pulled when hot! Worth every rupee."),
                ('karan_j', "Amritsari Fish Tikka", 4, "Fresh fish, very crispy batter with the nice aroma of ajwain. Delicious starter."),
                ('tanvi_p', "Shahi Malai Kofta", 5, "Velvety smooth cashew gravy and delicate koftas. Truly royal dining experience."),
                ('siddhivinayak', "Lucknowi Mutton Dum Biryani", 5, "Aromatic and royal taste. The saffron aroma fills the entire table."),
                ('aditi_s', "Dahi Ke Kebab", 5, "Crispy exterior and creamy inside. One of the best veg starters in the menu."),
                ('rohit_v', "Chicken Seekh Kebab", 4, "Juicy and packed with herbs. Squeeze some fresh lime on it and it's perfect."),
                ('neha_k', "Molten Chocolate Lava Cake", 5, "Oozing warm molten chocolate center. A chocolate lover's dream!"),
                ('arjun_m', "Hyderabadi Veg Dum Biryani", 4, "Great veg biryani option with fresh veggies and royal aroma."),
                ('priya_d', "Kulfi Falooda Royal", 5, "Rich traditional malai kulfi with plenty of falooda and sabja seeds."),
                ('karan_j', "Chicken Sukka Saoji", 5, "Authentic spicy Vidarbha flavor! For spicy food lovers, this is heaven."),
                ('tanvi_p', "Cold Coffee with Ice Cream", 4, "Rich and creamy cold coffee. Great refreshing sip."),
                ('siddhivinayak', "Jeera Rice with Fried Onions", 5, "Very fragrant and fluffy basmati rice with golden onions.")
            ]

            now = timezone.now()
            for u_name, item_name, rating, comment in reviews_def:
                cust = customer_map.get(u_name)
                item = menu_item_objs.get(item_name)
                if cust and item:
                    rev, _ = Review.objects.get_or_create(
                        customer=cust,
                        menu_item=item,
                        defaults={
                            'rating': rating,
                            'comment': comment,
                        }
                    )
                    # Distribute review dates over past 2 weeks
                    rand_offset = datetime.timedelta(days=(hash(item_name) % 12) + 1, hours=(hash(u_name) % 20))
                    Review.objects.filter(pk=rev.pk).update(review_date=now - rand_offset)

            # -------------------------------------------------------------
            # 7. Historical Completed Dining Sessions & Orders
            # -------------------------------------------------------------
            self.stdout.write("--> Generating Historical Completed Sessions & Payments...")

            # Helper to create an order
            def create_demo_order(session, customer, table_obj, items_with_qty, status, order_type, pay_method, pay_status, spec_note="", past_dt=None):
                t_num = table_obj.table_number if table_obj else ""
                order = Order.objects.create(
                    session=session,
                    customer=customer,
                    table=table_obj,
                    table_number=t_num,
                    status=status,
                    order_type=order_type,
                    payment_method=pay_method,
                    payment_status=pay_status,
                    special_instructions=spec_note
                )
                for item_obj, qty in items_with_qty:
                    OrderItem.objects.create(
                        order=order,
                        menu_item=item_obj,
                        quantity=qty,
                        price=item_obj.price,
                        is_cancelled=False
                    )
                order.recalculate_totals()
                if past_dt:
                    Order.objects.filter(pk=order.pk).update(order_date=past_dt)
                return order

            # History Session 1: Siddhivinayak at Table T-01 (3 days ago)
            # Highlights combined payments (Round 1 & 2 combined, Round 3 separate)
            sess1_start = now - datetime.timedelta(days=3, hours=2)
            sess1_end = now - datetime.timedelta(days=3, hours=0, minutes=45)
            sess1 = DiningSession.objects.create(
                customer=customer_map['siddhivinayak'],
                table=table_objs['T-01'],
                table_number='T-01',
                is_active=False
            )
            DiningSession.objects.filter(pk=sess1.pk).update(started_at=sess1_start, ended_at=sess1_end)

            # Round 1: Starters
            ord1_1 = create_demo_order(
                session=sess1,
                customer=customer_map['siddhivinayak'],
                table_obj=table_objs['T-01'],
                items_with_qty=[(menu_item_objs['Paneer Tikka Angara'], 1), (menu_item_objs['Virgin Mint Mojito'], 1)],
                status=Order.STATUS_COMPLETED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_ONLINE,
                pay_status=Order.PAYMENT_STATUS_PAID,
                past_dt=sess1_start + datetime.timedelta(minutes=5)
            )
            # Round 2: Mains
            ord1_2 = create_demo_order(
                session=sess1,
                customer=customer_map['siddhivinayak'],
                table_obj=table_objs['T-01'],
                items_with_qty=[(menu_item_objs['Paneer Butter Masala'], 1), (menu_item_objs['Butter Garlic Naan'], 2), (menu_item_objs['Jeera Rice with Fried Onions'], 1)],
                status=Order.STATUS_COMPLETED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_ONLINE,
                pay_status=Order.PAYMENT_STATUS_PAID,
                past_dt=sess1_start + datetime.timedelta(minutes=25)
            )
            # Round 3: Dessert
            ord1_3 = create_demo_order(
                session=sess1,
                customer=customer_map['siddhivinayak'],
                table_obj=table_objs['T-01'],
                items_with_qty=[(menu_item_objs['Sizzling Hot Brownie with Vanilla'], 1)],
                status=Order.STATUS_COMPLETED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_PAY_LATER,
                pay_status=Order.PAYMENT_STATUS_PAID,
                past_dt=sess1_start + datetime.timedelta(minutes=55)
            )
            sess1.update_totals()

            # Payments for Session 1:
            # Round 1 & Round 2 settled together via Online UPI
            common_upi_txn = "UPI/2026/9028127391"
            p1 = Payment.objects.create(
                order=ord1_1,
                method=Payment.METHOD_ONLINE_UPI,
                amount=ord1_1.total_amount,
                status=Payment.STATUS_PAID,
                transaction_id=common_upi_txn
            )
            Payment.objects.filter(pk=p1.pk).update(payment_date=sess1_start + datetime.timedelta(minutes=30))

            p2 = Payment.objects.create(
                order=ord1_2,
                method=Payment.METHOD_ONLINE_UPI,
                amount=ord1_2.total_amount,
                status=Payment.STATUS_PAID,
                transaction_id=common_upi_txn
            )
            Payment.objects.filter(pk=p2.pk).update(payment_date=sess1_start + datetime.timedelta(minutes=30))

            # Round 3 settled in cash with waiter Ramesh Kadam
            p3 = Payment.objects.create(
                order=ord1_3,
                method=Payment.METHOD_CASH_COUNTER,
                amount=ord1_3.total_amount,
                status=Payment.STATUS_PAID,
                transaction_id="CASH-RCP-4820",
                collected_by=waiter_objs[0]
            )
            Payment.objects.filter(pk=p3.pk).update(payment_date=sess1_end)

            # History Session 2: Aditi Sharma at Table T-04 (2 days ago)
            sess2_start = now - datetime.timedelta(days=2, hours=3)
            sess2_end = now - datetime.timedelta(days=2, hours=1, minutes=40)
            sess2 = DiningSession.objects.create(
                customer=customer_map['aditi_s'],
                table=table_objs['T-04'],
                table_number='T-04',
                is_active=False
            )
            DiningSession.objects.filter(pk=sess2.pk).update(started_at=sess2_start, ended_at=sess2_end)

            ord2_1 = create_demo_order(
                session=sess2,
                customer=customer_map['aditi_s'],
                table_obj=table_objs['T-04'],
                items_with_qty=[
                    (menu_item_objs['Murgh Malai Tikka'], 1),
                    (menu_item_objs['Butter Chicken Punjabi'], 1),
                    (menu_item_objs['Butter Garlic Naan'], 3),
                    (menu_item_objs['Hyderabadi Chicken Dum Biryani'], 1)
                ],
                status=Order.STATUS_COMPLETED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_ONLINE,
                pay_status=Order.PAYMENT_STATUS_PAID,
                past_dt=sess2_start + datetime.timedelta(minutes=10)
            )
            sess2.update_totals()

            p2_card = Payment.objects.create(
                order=ord2_1,
                method=Payment.METHOD_ONLINE_CARD,
                amount=ord2_1.total_amount,
                status=Payment.STATUS_PAID,
                transaction_id="CARD/2026/839210928"
            )
            Payment.objects.filter(pk=p2_card.pk).update(payment_date=sess2_end)

            # History Session 3: Rohit Verma at VIP-1 (yesterday) with a CANCELLED order demonstration!
            sess3_start = now - datetime.timedelta(days=1, hours=5)
            sess3_end = now - datetime.timedelta(days=1, hours=3, minutes=30)
            sess3 = DiningSession.objects.create(
                customer=customer_map['rohit_v'],
                table=table_objs['VIP-1'],
                table_number='VIP-1',
                is_active=False
            )
            DiningSession.objects.filter(pk=sess3.pk).update(started_at=sess3_start, ended_at=sess3_end)

            ord3_1 = create_demo_order(
                session=sess3,
                customer=customer_map['rohit_v'],
                table_obj=table_objs['VIP-1'],
                items_with_qty=[
                    (menu_item_objs['Crispy Corn Salt & Pepper'], 1),
                    (menu_item_objs['Kadai Paneer Special'], 1),
                    (menu_item_objs['Laccha Paratha'], 2)
                ],
                status=Order.STATUS_COMPLETED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_ONLINE,
                pay_status=Order.PAYMENT_STATUS_PAID,
                past_dt=sess3_start + datetime.timedelta(minutes=10)
            )

            # Cancelled Order to show cancellation tracking in order history
            ord3_cancelled = create_demo_order(
                session=sess3,
                customer=customer_map['rohit_v'],
                table_obj=table_objs['VIP-1'],
                items_with_qty=[(menu_item_objs['Hyderabadi Veg Dum Biryani'], 1)],
                status=Order.STATUS_CANCELLED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_PAY_LATER,
                pay_status=Order.PAYMENT_STATUS_PENDING,
                spec_note="Accidentally ordered double - cancelled by diner while pending",
                past_dt=sess3_start + datetime.timedelta(minutes=25)
            )

            ord3_2 = create_demo_order(
                session=sess3,
                customer=customer_map['rohit_v'],
                table_obj=table_objs['VIP-1'],
                items_with_qty=[(menu_item_objs['Gulab Jamun with Ice Cream'], 2)],
                status=Order.STATUS_COMPLETED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_ONLINE,
                pay_status=Order.PAYMENT_STATUS_PAID,
                past_dt=sess3_start + datetime.timedelta(minutes=40)
            )
            sess3.update_totals()

            p3_upi = "UPI/2026/772391024"
            p3_a = Payment.objects.create(
                order=ord3_1,
                method=Payment.METHOD_ONLINE_UPI,
                amount=ord3_1.total_amount,
                status=Payment.STATUS_PAID,
                transaction_id=p3_upi
            )
            Payment.objects.filter(pk=p3_a.pk).update(payment_date=sess3_end)

            p3_b = Payment.objects.create(
                order=ord3_2,
                method=Payment.METHOD_ONLINE_UPI,
                amount=ord3_2.total_amount,
                status=Payment.STATUS_PAID,
                transaction_id=p3_upi
            )
            Payment.objects.filter(pk=p3_b.pk).update(payment_date=sess3_end)

            # History Session 4: Takeaway Order by Arjun Mehta (6 hours ago)
            sess4_start = now - datetime.timedelta(hours=6)
            sess4_end = now - datetime.timedelta(hours=5, minutes=15)
            sess4 = DiningSession.objects.create(
                customer=customer_map['arjun_m'],
                table=None,
                table_number='Takeaway',
                is_active=False
            )
            DiningSession.objects.filter(pk=sess4.pk).update(started_at=sess4_start, ended_at=sess4_end)

            ord4_1 = create_demo_order(
                session=sess4,
                customer=customer_map['arjun_m'],
                table_obj=None,
                items_with_qty=[
                    (menu_item_objs['Hyderabadi Chicken Dum Biryani'], 2),
                    (menu_item_objs['Royal Mango Lassi'], 2)
                ],
                status=Order.STATUS_COMPLETED,
                order_type=Order.ORDER_TYPE_TAKEAWAY,
                pay_method=Order.PAYMENT_METHOD_ONLINE,
                pay_status=Order.PAYMENT_STATUS_PAID,
                spec_note="Packed for takeaway with extra onions & raita",
                past_dt=sess4_start
            )
            sess4.update_totals()

            p4 = Payment.objects.create(
                order=ord4_1,
                method=Payment.METHOD_ONLINE_UPI,
                amount=ord4_1.total_amount,
                status=Payment.STATUS_PAID,
                transaction_id="UPI/2026/663819203"
            )
            Payment.objects.filter(pk=p4.pk).update(payment_date=sess4_start + datetime.timedelta(minutes=5))

            # -------------------------------------------------------------
            # 8. ACTIVE LIVE DINING SESSIONS (Right Now!)
            # -------------------------------------------------------------
            self.stdout.write("--> Generating Active Live Dining Sessions for KDS & Waiter Floor...")

            # LIVE TABLE 1: Table T-03 (Siddhivinayak) - Active session, locked!
            # Order 1: Preparing in Kitchen
            # Order 2: Food Served on Table
            tbl_t3 = table_objs['T-03']
            tbl_t3.lock_for(customer_map['siddhivinayak'])

            live_sess1 = DiningSession.objects.create(
                customer=customer_map['siddhivinayak'],
                table=tbl_t3,
                table_number='T-03',
                is_active=True
            )
            DiningSession.objects.filter(pk=live_sess1.pk).update(started_at=now - datetime.timedelta(minutes=35))

            # Served round (Starters delivered 15 mins ago)
            live_ord1 = create_demo_order(
                session=live_sess1,
                customer=customer_map['siddhivinayak'],
                table_obj=tbl_t3,
                items_with_qty=[
                    (menu_item_objs['Paneer Tikka Angara'], 1),
                    (menu_item_objs['Virgin Mint Mojito'], 2)
                ],
                status=Order.STATUS_SERVED,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_PAY_LATER,
                pay_status=Order.PAYMENT_STATUS_PENDING,
                past_dt=now - datetime.timedelta(minutes=30)
            )
            Payment.objects.create(
                order=live_ord1,
                method=Payment.METHOD_CASH_COUNTER,
                amount=live_ord1.total_amount,
                status=Payment.STATUS_PENDING
            )

            # Preparing round (Main course cooking right now in Kitchen KDS!)
            live_ord2 = create_demo_order(
                session=live_sess1,
                customer=customer_map['siddhivinayak'],
                table_obj=tbl_t3,
                items_with_qty=[
                    (menu_item_objs['Butter Chicken Punjabi'], 1),
                    (menu_item_objs['Butter Garlic Naan'], 2),
                    (menu_item_objs['Jeera Rice with Fried Onions'], 1)
                ],
                status=Order.STATUS_PREPARING,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_PAY_LATER,
                pay_status=Order.PAYMENT_STATUS_PENDING,
                spec_note="Gravy medium spicy, less butter please",
                past_dt=now - datetime.timedelta(minutes=12)
            )
            Payment.objects.create(
                order=live_ord2,
                method=Payment.METHOD_CASH_COUNTER,
                amount=live_ord2.total_amount,
                status=Payment.STATUS_PENDING
            )
            live_sess1.update_totals()

            # Active Waiter Alert from Table T-03
            WaiterAlert.objects.create(
                table=tbl_t3,
                table_number='T-03',
                customer=customer_map['siddhivinayak'],
                message="Please bring 2 extra water glasses and napkins",
                is_resolved=False
            )

            # LIVE TABLE 2: Table T-05 (Aditi Sharma) - Ready to serve!
            tbl_t5 = table_objs['T-05']
            tbl_t5.lock_for(customer_map['aditi_s'])

            live_sess2 = DiningSession.objects.create(
                customer=customer_map['aditi_s'],
                table=tbl_t5,
                table_number='T-05',
                is_active=True
            )
            DiningSession.objects.filter(pk=live_sess2.pk).update(started_at=now - datetime.timedelta(minutes=22))

            live_ord3 = create_demo_order(
                session=live_sess2,
                customer=customer_map['aditi_s'],
                table_obj=tbl_t5,
                items_with_qty=[
                    (menu_item_objs['Hyderabadi Veg Dum Biryani'], 1),
                    (menu_item_objs['Gulab Jamun with Ice Cream'], 1),
                    (menu_item_objs['Royal Mango Lassi'], 1)
                ],
                status=Order.STATUS_READY,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_PAY_LATER,
                pay_status=Order.PAYMENT_STATUS_PENDING,
                spec_note="Include extra salan and raita with biryani",
                past_dt=now - datetime.timedelta(minutes=18)
            )
            Payment.objects.create(
                order=live_ord3,
                method=Payment.METHOD_CASH_COUNTER,
                amount=live_ord3.total_amount,
                status=Payment.STATUS_PENDING
            )
            live_sess2.update_totals()

            # LIVE TABLE 3: Table T-02 (Rohit Verma) - Pending in Kitchen queue
            tbl_t2 = table_objs['T-02']
            tbl_t2.lock_for(customer_map['rohit_v'])

            live_sess3 = DiningSession.objects.create(
                customer=customer_map['rohit_v'],
                table=tbl_t2,
                table_number='T-02',
                is_active=True
            )
            DiningSession.objects.filter(pk=live_sess3.pk).update(started_at=now - datetime.timedelta(minutes=4))

            live_ord4 = create_demo_order(
                session=live_sess3,
                customer=customer_map['rohit_v'],
                table_obj=tbl_t2,
                items_with_qty=[
                    (menu_item_objs['Crispy Corn Salt & Pepper'], 1),
                    (menu_item_objs['Kadai Paneer Special'], 1),
                    (menu_item_objs['Tandoori Butter Roti'], 2)
                ],
                status=Order.STATUS_PENDING,
                order_type=Order.ORDER_TYPE_DINE_IN,
                pay_method=Order.PAYMENT_METHOD_PAY_LATER,
                pay_status=Order.PAYMENT_STATUS_PENDING,
                spec_note="Make crispy corn extra crunchy",
                past_dt=now - datetime.timedelta(minutes=3)
            )
            Payment.objects.create(
                order=live_ord4,
                method=Payment.METHOD_CASH_COUNTER,
                amount=live_ord4.total_amount,
                status=Payment.STATUS_PENDING
            )
            live_sess3.update_totals()

        # -------------------------------------------------------------
        # Summary & Credentials Output
        # -------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("  🎉 REALISTIC DEMO DATA SEEDED SUCCESSFULLY!"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(f"  • Restaurant        : {restaurant.name}")
        self.stdout.write(f"  • Categories        : {Category.objects.count()} categories")
        self.stdout.write(f"  • Menu Items        : {MenuItem.objects.count()} dishes")
        self.stdout.write(f"  • Reviews           : {Review.objects.count()} reviews")
        self.stdout.write(f"  • Dining Tables     : {RestaurantTable.objects.count()} tables ({RestaurantTable.objects.filter(is_locked=True).count()} Locked, {RestaurantTable.objects.filter(is_locked=False).count()} Free)")
        self.stdout.write(f"  • Total Orders      : {Order.objects.count()} orders across {DiningSession.objects.count()} dining sessions")
        self.stdout.write(f"  • Payments Recorded : {Payment.objects.count()} payments (UPI, Cards, Cash)")
        self.stdout.write(f"  • Active Alerts     : {WaiterAlert.objects.filter(is_resolved=False).count()} pending waiter calls")
        self.stdout.write("-" * 70)
        self.stdout.write(self.style.NOTICE("  🔑 DEMO LOGIN CREDENTIALS:"))
        self.stdout.write("-" * 70)
        self.stdout.write("  ROLE            USERNAME        PASSWORD      NAME")
        self.stdout.write("  Superuser       admin           admin123      Restaurant Owner")
        self.stdout.write("  Manager         manager         manager123    Rajesh Sharma")
        self.stdout.write("  Waiter          waiter          waiter123     Ramesh Kadam")
        self.stdout.write("  Waiter 2        waiter2         waiter123     Pooja Patil")
        self.stdout.write("  Waiter 3        waiter3         waiter123     Anil Shinde")
        self.stdout.write("  Kitchen Chef    kitchen         kitchen123    Chef Sanjeev Patil")
        self.stdout.write("  Kitchen Chef 2  chef2           kitchen123    Chef Vikas Khanna")
        self.stdout.write("  Customer        siddhivinayak   customer123   Siddhivinayak Tidake")
        self.stdout.write("  Customer 2      aditi_s         customer123   Aditi Sharma")
        self.stdout.write("  Customer 3      rohit_v         customer123   Rohit Verma")
        self.stdout.write("=" * 70)
        self.stdout.write("")
