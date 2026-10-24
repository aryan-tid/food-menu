from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class StaffProfile(models.Model):
    """
    Role-Based Access Control profile for Restaurant Staff:
    - Kitchen Manager: Manages cooking queue (Pending -> Preparing -> Ready)
    - Waiter: Tracks tables, serves food, handles cash, unlocks tables
    - Manager: Full access to staff roles, menu, tables, revenue, emergency overrides
    """
    ROLE_MANAGER = 'MANAGER'
    ROLE_WAITER = 'WAITER'
    ROLE_KITCHEN = 'KITCHEN'

    ROLE_CHOICES = [
        (ROLE_MANAGER, 'Restaurant Manager (Admin)'),
        (ROLE_WAITER, 'Waiter / Floor Staff'),
        (ROLE_KITCHEN, 'Kitchen Manager / Chef'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_WAITER)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'staff_profile'
        verbose_name = 'Staff Profile'
        verbose_name_plural = 'Staff Profiles'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_role_display()}"

    @property
    def is_manager(self):
        return self.role == self.ROLE_MANAGER or self.user.is_superuser

    @property
    def is_waiter(self):
        return self.role == self.ROLE_WAITER or self.is_manager

    @property
    def is_kitchen(self):
        return self.role == self.ROLE_KITCHEN or self.is_manager


class Customer(models.Model):
    """
    Customer entity corresponding to ER Diagram:
    Attributes: customer_id (PK), name, email, phone, address, Google login attributes
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True, null=True, help_text="Optional contact address")
    google_id = models.CharField(max_length=120, blank=True, null=True)
    avatar_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customer'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'

    def __str__(self):
        return f"{self.name} ({self.email})"

    @property
    def name(self):
        full_name = self.user.get_full_name()
        return full_name if full_name else self.user.username

    @property
    def email(self):
        return self.user.email


@receiver(post_save, sender=User)
def create_customer_profile_on_signup(sender, instance, created, **kwargs):
    """Creates a customer profile automatically for non-staff registered users."""
    if created and not instance.is_staff and not instance.is_superuser:
        Customer.objects.get_or_create(user=instance)
