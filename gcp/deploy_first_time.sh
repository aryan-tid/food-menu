#!/bin/bash
# ==============================================================================
# Spice Garden Restaurant System - GCP First-Time Production Deployment
# Repository: https://github.com/aryan-tid/food-menu.git
# Target OS: Ubuntu / Debian on Google Cloud Platform (Compute Engine VM)
# ==============================================================================
# Usage:
#   Interactive:     sudo bash gcp/deploy_first_time.sh
#   Non-Interactive: sudo bash gcp/deploy_first_time.sh <yourdomain.com> <your_email@example.com>
# ==============================================================================
set -e

echo "==================================================================="
echo "  🚀 Spice Garden Food Menu - First-Time GCP Production Deployer"
echo "  📦 Repository: https://github.com/aryan-tid/food-menu.git"
echo "==================================================================="

# 0. Domain & SSL Parameters
DOMAIN="$1"
SSL_EMAIL="$2"

if [ -z "$DOMAIN" ] && [ -t 0 ]; then
    echo ""
    read -p "👉 Enter your custom domain (or leave blank to use Public IP): " INPUT_DOMAIN
    DOMAIN="$INPUT_DOMAIN"
fi

# Sanitize domain: strip https://, http://, and trailing slashes or spaces
if [ -n "$DOMAIN" ]; then
    DOMAIN=$(echo "$DOMAIN" | sed -e 's|^[^/]*//||' -e 's|/.*$||' | tr -d '[:space:]')
fi

if [ -n "$DOMAIN" ] && [ -z "$SSL_EMAIL" ] && [ -t 0 ]; then
    read -p "👉 Enter email for free Let's Encrypt SSL certificate (e.g. admin@$DOMAIN): " INPUT_EMAIL
    SSL_EMAIL=$(echo "$INPUT_EMAIL" | tr -d '[:space:]')
fi

# Detect Server External IP
echo "--> Detecting server external IP..."
EXTERNAL_IP=$(curl -s -m 5 http://checkip.amazonaws.com || curl -s -m 5 ifconfig.me || echo "127.0.0.1")
echo "--> Server Public IP: $EXTERNAL_IP"

# 1. Update OS packages and install production dependencies
echo "--> Installing system packages (PostgreSQL, Nginx, Python, Git, Certbot)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv nginx git libpq-dev \
    postgresql postgresql-contrib certbot python3-certbot-nginx curl openssl

# 2. Setup 2GB Swap space (Prevents OOM on budget GCP e2-micro/e2-small VMs)
SWAP_COUNT=$(swapon --show | wc -l)
if [ "$SWAP_COUNT" -le 1 ]; then
    echo "--> Configuring 2GB Swap space to protect against memory spikes..."
    sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    if ! grep -q "/swapfile" /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    fi
    echo "--> 2GB Swap activated."
fi

# 3. Setup Project Directory from GitHub
PROJECT_DIR="/var/www/food-menu"
REPO_URL="https://github.com/aryan-tid/food-menu.git"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "--> Cloning repository from GitHub ($REPO_URL) to $PROJECT_DIR..."
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown -R $USER:$USER "$PROJECT_DIR"
    git clone "$REPO_URL" "$PROJECT_DIR"
else
    echo "--> Existing directory found at $PROJECT_DIR. Updating code from GitHub..."
    cd "$PROJECT_DIR"
    git config --global --add safe.directory "$PROJECT_DIR" 2>/dev/null || true
    git fetch origin main || true
    git pull origin main || true
fi

cd "$PROJECT_DIR"

# 4. Handle .env Configuration
# If the user already manually uploaded .env, preserve it completely!
if [ -f ".env" ]; then
    echo "--> ✅ Existing .env detected! Preserving your manual configuration."
else
    echo "--> Creating default .env from .env.example..."
    cp .env.example .env
fi

# Extract or generate database credentials
DB_NAME=$(grep -E "^DB_NAME=" .env 2>/dev/null | cut -d '=' -f2 | tr -d ' "\r' || true)
DB_USER=$(grep -E "^DB_USER=" .env 2>/dev/null | cut -d '=' -f2 | tr -d ' "\r' || true)
DB_PASS=$(grep -E "^DB_PASSWORD=" .env 2>/dev/null | cut -d '=' -f2 | tr -d ' "\r' || true)

DB_NAME=${DB_NAME:-food_menu_db}
DB_USER=${DB_USER:-food_user}
DB_PASS=${DB_PASS:-$(openssl rand -hex 12 2>/dev/null || echo 'SpiceGardenDB2026!')}

# 5. Provision PostgreSQL Database and User
echo "--> Setting up PostgreSQL database ($DB_NAME) & user ($DB_USER)..."
sudo systemctl enable postgresql
sudo systemctl start postgresql

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"

sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;" 2>/dev/null || true
sudo -u postgres psql -d "$DB_NAME" -c "ALTER SCHEMA public OWNER TO $DB_USER;" 2>/dev/null || true

# 6. Ensure Hosts, CSRF, and PostgreSQL in .env
if [ -n "$DOMAIN" ]; then
    DOT_COUNT=$(echo "$DOMAIN" | tr -cd '.' | wc -c)
    if [ "$DOT_COUNT" -eq 1 ] && [[ ! "$DOMAIN" =~ ^www\. ]] && [[ ! "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        SERVER_NAMES="$DOMAIN www.$DOMAIN $EXTERNAL_IP localhost"
        ALLOWED_HOSTS_VAL="$DOMAIN,www.$DOMAIN,$EXTERNAL_IP,localhost,127.0.0.1"
        CSRF_ORIGINS_VAL="https://$DOMAIN,https://www.$DOMAIN,http://$DOMAIN,http://www.$DOMAIN,http://$EXTERNAL_IP"
        CERTBOT_FLAGS="-d $DOMAIN -d www.$DOMAIN"
    else
        SERVER_NAMES="$DOMAIN $EXTERNAL_IP localhost"
        ALLOWED_HOSTS_VAL="$DOMAIN,$EXTERNAL_IP,localhost,127.0.0.1"
        CSRF_ORIGINS_VAL="https://$DOMAIN,http://$DOMAIN,http://$EXTERNAL_IP"
        CERTBOT_FLAGS="-d $DOMAIN"
    fi
else
    SERVER_NAMES="_ $EXTERNAL_IP localhost"
    ALLOWED_HOSTS_VAL="$EXTERNAL_IP,localhost,127.0.0.1"
    CSRF_ORIGINS_VAL="http://$EXTERNAL_IP,http://localhost:8000"
fi

# Clean and update production keys in .env
sed -i '/^DEBUG=/d' .env
sed -i '/^ALLOWED_HOSTS=/d' .env
sed -i '/^CSRF_TRUSTED_ORIGINS=/d' .env
sed -i '/^DB_ENGINE=/d' .env
sed -i '/^DB_NAME=/d' .env
sed -i '/^DB_USER=/d' .env
sed -i '/^DB_PASSWORD=/d' .env
sed -i '/^DB_HOST=/d' .env
sed -i '/^DB_PORT=/d' .env

cat <<EOF >> .env

# Production Settings (Configured by deploy_first_time.sh)
DEBUG=False
ALLOWED_HOSTS=$ALLOWED_HOSTS_VAL
CSRF_TRUSTED_ORIGINS=$CSRF_ORIGINS_VAL

# PostgreSQL Database Configuration
DB_ENGINE=postgresql
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASS
DB_HOST=localhost
DB_PORT=5432
EOF

# 7. Create Virtual Environment & Install Python Dependencies
echo "--> Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 8. Run Django Migrations & Collect Static Assets
echo "--> Running database migrations against PostgreSQL..."
./venv/bin/python manage.py migrate --noinput

echo "--> Collecting static assets..."
./venv/bin/python manage.py collectstatic --noinput

if [ -f "data_seed.json" ]; then
    echo "--> Loading catalog data from data_seed.json..."
    ./venv/bin/python manage.py loaddata data_seed.json || ./venv/bin/python manage.py seed_data || true
else
    echo "--> Seeding initial restaurant catalog, tables & roles..."
    ./venv/bin/python manage.py seed_data || true
fi

# 9. Setup Logging & File Ownership
sudo mkdir -p /var/log/gunicorn
sudo chown -R www-data:www-data /var/log/gunicorn
sudo chown -R www-data:www-data "$PROJECT_DIR"
sudo chmod -R 775 "$PROJECT_DIR/media" 2>/dev/null || true

# 10. Configure Gunicorn Systemd Service
echo "--> Configuring Gunicorn systemd service..."
sudo tee /etc/systemd/system/food_menu.service > /dev/null <<EOF
[Unit]
Description=Gunicorn daemon for Spice Garden Online Food Menu System
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/gunicorn \\
          --access-logfile /var/log/gunicorn/food_menu_access.log \\
          --error-logfile /var/log/gunicorn/food_menu_error.log \\
          --workers 3 \\
          --bind 127.0.0.1:8000 \\
          core.wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable food_menu
sudo systemctl restart food_menu

# 11. Configure Nginx Reverse Proxy
echo "--> Configuring Nginx reverse proxy..."
sudo tee /etc/nginx/sites-available/food_menu > /dev/null <<EOF
server {
    listen 80;
    server_name $SERVER_NAMES;

    client_max_body_size 25M;

    # Static Assets
    location /static/ {
        alias $PROJECT_DIR/staticfiles/;
        expires 30d;
        access_log off;
    }

    # Food Images & Uploaded Media
    location /media/ {
        alias $PROJECT_DIR/media/;
        expires 30d;
        access_log off;
    }

    # Reverse Proxy to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/food_menu /etc/nginx/sites-enabled/food_menu
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# 12. Provision Let's Encrypt Free SSL (if domain & email provided)
FINAL_URL="http://$EXTERNAL_IP"
if [ -n "$DOMAIN" ]; then
    FINAL_URL="http://$DOMAIN"
    if [ -n "$SSL_EMAIL" ]; then
        echo "--> Requesting Let's Encrypt SSL certificate for $DOMAIN..."
        if sudo certbot --nginx $CERTBOT_FLAGS --non-interactive --agree-tos -m "$SSL_EMAIL" --redirect; then
            echo "--> ✅ HTTPS certificate installed successfully!"
            FINAL_URL="https://$DOMAIN"
        else
            echo "--> ⚠️ Note: SSL certificate request could not complete automatically."
            echo "    Ensure DNS 'A' records point to $EXTERNAL_IP."
            echo "    Then run: sudo certbot --nginx $CERTBOT_FLAGS"
        fi
    fi
fi

echo ""
echo "==================================================================="
echo "  🎉 FIRST-TIME DEPLOYMENT COMPLETED SUCCESSFULLY!"
echo "==================================================================="
echo "  🌐 Live Application URL : $FINAL_URL"
echo "  🗄️ Database              : PostgreSQL ($DB_NAME on localhost:5432)"
echo "  🛡️ Web Server            : Nginx + Gunicorn (Systemd: food_menu.service)"
echo "  📁 Working Directory     : $PROJECT_DIR"
if [ -n "$DOMAIN" ]; then
    echo "  🔗 Custom Domain         : $DOMAIN"
fi
echo "==================================================================="
echo "  To inspect live logs : sudo journalctl -u food_menu -f"
echo "  To update in future  : bash $PROJECT_DIR/gcp/update_app.sh"
echo "==================================================================="
