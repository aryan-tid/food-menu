from menu.management.commands.seed_demo_data import Command as SeedDemoDataCommand


class Command(SeedDemoDataCommand):
    help = 'Seeds full realistic demo data (Menu, Customers, Staff, Tables, Orders, Payments, Reviews). Alias for seed_demo_data.'
