#!/bin/bash
# ==============================================================================
# Spice Garden Restaurant System - Database Reset & Demo Data Seeder
# Clears all old database data and seeds rich, realistic restaurant demo data
# (Staff accounts, Waiters, Chefs, Customers, 47 Menu Dishes, Reviews, Orders,
#  Payments, Tables, and Live Kitchen/Waiter floor queues).
# ==============================================================================
# Usage:
#   sudo bash /var/www/food-menu/gcp/seed_database.sh
# ==============================================================================
set -e

PROJECT_DIR="/var/www/food-menu"

echo "==================================================================="
echo "  🌱 RESETTING DATABASE & SEEDING REALISTIC DEMO DATA..."
echo "  📁 Target: $PROJECT_DIR"
echo "==================================================================="

# 1. Switch to project directory
if [ -d "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
else
    # Fallback to current repository directory if running locally or alternative path
    cd "$(dirname "$0")/.."
fi

# 2. Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
else
    echo "❌ Error: Virtual environment 'venv' not found."
    exit 1
fi

# 3. Run the database seed command with --clear flag
python manage.py seed_demo_data --clear

echo "==================================================================="
echo "  ✅ DATABASE READY! All demo data has been populated."
echo "==================================================================="
