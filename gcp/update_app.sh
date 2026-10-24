#!/bin/bash
# ==============================================================================
# Spice Garden Restaurant System - GCP App Update Script
# Repository: https://github.com/aryan-tid/food-menu.git
# Updates an existing production deployment directly from GitHub.
# Preserves existing .env, database, and uploaded media files.
# ==============================================================================
# Usage:
#   sudo bash gcp/update_app.sh
# ==============================================================================
set -e

PROJECT_DIR="/var/www/food-menu"

echo "==================================================================="
echo "  🔄 Spice Garden - Updating App from GitHub..."
echo "  📦 Repository: https://github.com/aryan-tid/food-menu.git"
echo "==================================================================="

# 1. Switch to production directory
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Error: Project directory $PROJECT_DIR does not exist."
    echo "Please run gcp/deploy_first_time.sh first!"
    exit 1
fi

cd "$PROJECT_DIR"

# 2. Pull latest code from GitHub
echo "--> Pulling latest changes from GitHub (origin/main)..."
git config --global --add safe.directory "$PROJECT_DIR" 2>/dev/null || true
git fetch origin main
git pull origin main

# 3. Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️ Warning: .env file not found in $PROJECT_DIR."
    echo "Creating from .env.example..."
    cp .env.example .env
    echo "Please configure $PROJECT_DIR/.env with your production values!"
else
    echo "--> ✅ Existing .env detected and preserved."
fi

# 4. Activate virtual environment & update dependencies
echo "--> Updating Python dependencies from requirements.txt..."
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Run Database Migrations
echo "--> Running Django database migrations..."
python manage.py migrate --noinput

# 6. Collect Static Assets
echo "--> Collecting static files..."
python manage.py collectstatic --noinput

# 7. Update Permissions
echo "--> Adjusting file permissions for www-data..."
sudo chown -R www-data:www-data "$PROJECT_DIR"
sudo chmod -R 775 "$PROJECT_DIR/media" 2>/dev/null || true
sudo mkdir -p /var/log/gunicorn
sudo chown -R www-data:www-data /var/log/gunicorn

# 8. Restart Application Daemon
echo "--> Restarting Gunicorn daemon (food_menu.service)..."
sudo systemctl daemon-reload
sudo systemctl restart food_menu

# 9. Test & Reload Nginx
echo "--> Reloading Nginx..."
sudo nginx -t
sudo systemctl reload nginx

# 10. Verify Health
echo "--> Verifying application service status..."
sleep 2
if sudo systemctl is-active --quiet food_menu; then
    echo "✅ food_menu service is ACTIVE and running smoothly!"
else
    echo "❌ food_menu service failed to start. Showing recent error logs:"
    sudo journalctl -u food_menu -n 25 --no-pager
    exit 1
fi

echo ""
echo "==================================================================="
echo "  🎉 APPLICATION UPDATED SUCCESSFULLY FROM GITHUB!"
echo "==================================================================="
echo "  To inspect live logs: sudo journalctl -u food_menu -f"
echo "==================================================================="
