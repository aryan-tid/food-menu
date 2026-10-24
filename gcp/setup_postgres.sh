#!/bin/bash
# ==============================================================================
# Automated PostgreSQL Setup Script for GCP Compute Engine VM / Ubuntu / Debian
# ==============================================================================
set -e

echo "=== Setting up PostgreSQL for Spice Garden Restaurant System ==="

# 1. Install PostgreSQL and client libraries if not already installed
if ! command -v psql &> /dev/null; then
    echo "--> Installing PostgreSQL and libpq-dev..."
    sudo apt-get update -y
    sudo apt-get install -y postgresql postgresql-contrib libpq-dev
fi

# 2. Ensure PostgreSQL service is active
echo "--> Starting PostgreSQL service..."
sudo systemctl enable postgresql
sudo systemctl start postgresql

# 3. Read DB configuration from .env or prompt for defaults
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="/var/www/food-menu/.env"
fi

if [ -f "$ENV_FILE" ]; then
    DB_NAME=$(grep -E "^DB_NAME=" "$ENV_FILE" | cut -d '=' -f2 | tr -d ' "\r')
    DB_USER=$(grep -E "^DB_USER=" "$ENV_FILE" | cut -d '=' -f2 | tr -d ' "\r')
    DB_PASS=$(grep -E "^DB_PASSWORD=" "$ENV_FILE" | cut -d '=' -f2 | tr -d ' "\r')
fi

DB_NAME=${DB_NAME:-food_menu_db}
DB_USER=${DB_USER:-food_user}
DB_PASS=${DB_PASS:-SpiceGarden2026!}

echo "--> Target Database: $DB_NAME"
echo "--> Database User:   $DB_USER"

# 4. Create User and Database with robust permissions
echo "--> Creating role and database in PostgreSQL..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"

# Update password in case user already existed
sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

# Grant privileges (PostgreSQL 14/15/16 public schema permissions)
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "ALTER SCHEMA public OWNER TO $DB_USER;"

# 5. Update or append database settings in .env
if [ -f "$ENV_FILE" ]; then
    echo "--> Updating $ENV_FILE with PostgreSQL credentials..."
    # Remove existing DB keys if present
    sed -i '/^DB_ENGINE=/d' "$ENV_FILE"
    sed -i '/^DB_NAME=/d' "$ENV_FILE"
    sed -i '/^DB_USER=/d' "$ENV_FILE"
    sed -i '/^DB_PASSWORD=/d' "$ENV_FILE"
    sed -i '/^DB_HOST=/d' "$ENV_FILE"
    sed -i '/^DB_PORT=/d' "$ENV_FILE"

    cat <<EOF >> "$ENV_FILE"

# PostgreSQL Configuration
DB_ENGINE=postgresql
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASS
DB_HOST=localhost
DB_PORT=5432
EOF
fi

# 6. Test connection
echo "--> Verifying database connection..."
PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "SELECT 'PostgreSQL connection successful!' as status;"

echo "=== PostgreSQL Setup Completed Successfully! ==="
echo "You can now run: ./venv/bin/python manage.py migrate"
