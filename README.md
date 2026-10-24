# Spice Garden — Smart Online Food Menu & Restaurant Management System

[![Django](https://img.shields.io/badge/Django-6.1-092E20?style=flat&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Nginx](https://img.shields.io/badge/Nginx-Reverse_Proxy-009639?style=flat&logo=nginx&logoColor=white)](https://nginx.org/)
[![GCP](https://img.shields.io/badge/Google_Cloud-Compute_Engine-4285F4?style=flat&logo=googlecloud&logoColor=white)](https://cloud.google.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A production-ready, mobile-first **Smart Online Food Menu and Real-Time Restaurant Management System** built with **Django**, **PostgreSQL**, **Gunicorn**, and **Nginx**. Engineered for fine-dining restaurants, cafes, and food courts to handle QR-code table ordering, live kitchen coordination (KDS), waiter floor alerts, multi-round dining sessions, and consolidated bill settlements.

---

## 🌟 Key Features

### 📱 1. Customer Digital Dining Experience (Mobile-First)
- **Table QR Scanning & Manual Selection**: Scanning a table QR code automatically assigns the table; direct walk-ins can pick tables through a real-time status selector.
- **Dynamic Concurrency Table Lock**: Real-time table status endpoint (`/api/tables/status/`) prevents multiple diners from locking the same table simultaneously. Clear warnings guide users to notify staff if a table is held.
- **Interactive Menu**: Category-wise grouping, vegetarian/non-vegetarian toggles, dynamic live search, and curated high-resolution photography fallbacks.
- **Zero-Reload AJAX Cart**: Inline quantity steppers (`[-] 1 [+]`) update cart counts instantly without page reloads.
- **Multi-Round Dining Sessions (`DiningSession`)**: Diners can order initial starters, followed by main courses, followed by desserts across separate rounds while keeping all tickets linked to one active table visit.
- **Persistent Live Tracking**: Pinned floating glance bar and detailed order timeline showing live kitchen stages (*Queued ➔ Preparing ➔ Ready ➔ Served*).
- **Staff Assistance Alert**: Diners can call a waiter for water, cutlery, or bills directly from their phone with one tap.
- **Session History**: Order history strictly shows past dining sessions where food was ordered (excluding abandoned visits) while preserving cancelled tickets for audit trails.

### 👨‍🍳 2. Kitchen Display System (KDS)
- **Live Ticket Kanban**: Ordered tickets appear immediately on kitchen chef displays.
- **Individual Dish Checklist**: Line cooks can mark individual items as prepared and cancel specific dishes if ingredients run out.
- **One-Tap Stage Transitions**: Progress tickets from *Queued* to *In Preparation* to *Ready for Service*.

### 🧑‍💼 3. Waiter Floor Console
- **Table Occupancy Map**: Live overview of table locks, session durations, and guest counts.
- **Instant Assistance Alerts**: Real-time alerts notification center with one-click resolution.
- **Floor Service**: One-tap food delivery confirmation (*Mark Served*).
- **Counter Cash Settlement**: Settle bills with cash at the table or counter, uplifting table concurrency locks immediately.

### 🛡️ 4. Manager Administration Console
- **Executive KPI Cards**: Real-time Gross Revenue, Today's Sales, Active Tickets, Table Occupancy, and Cash vs. Online revenue splits.
- **Comprehensive Audit Breakdown**: Dedicated session inspector breaking down itemized dishes, tax calculations, customer profiles, and transaction references.
- **Combined Payment Receipts & Installments**: Automatically groups multiple orders settled together into **single combined receipts** (e.g., Rounds 1, 2, 3 in Receipt #1). Multi-installment settlements (e.g., Rounds 1–3 settled first, Rounds 4–5 settled later) are cleanly distinguished.
- **Staff Role Management**: Provision and manage Waiters, Kitchen Chefs, and Managers.
- **Customer Directory & QR Generator**: Download static printable QR codes for each physical table.

### 🔒 5. Security & Authentication
- **Dual Authentication**: Google Sign-In for diners (via Firebase Admin SDK) + Role-Based Staff Authentication.
- **Staff Self-Service Password Change**: Staff members can securely update their own passwords using their existing password. Passwords are never stored in plain text and are hashed with Django's **PBKDF2 SHA-256** algorithm. Session authentication hashes are maintained to prevent unexpected logouts.

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Django 6.1 (Python 3.14) |
| **Database** | PostgreSQL 16 (Production) / SQLite3 (Development) |
| **WSGI Server** | Gunicorn 26.2 (Systemd Managed) |
| **Web Server / Reverse Proxy** | Nginx with Gzip & 30-day Static Caching |
| **Frontend Architecture** | Mobile-First HTML5, Vanilla JavaScript (ES6+), Bootstrap 5.3, Bootstrap Icons |
| **Cloud Infrastructure** | Google Cloud Platform (GCP Compute Engine e2-micro/e2-small) |
| **SSL / HTTPS** | Let's Encrypt automated via Certbot |

---

## 📁 Project Directory Structure

```
food-menu/
├── accounts/                  # User accounts, Customer profile, StaffProfile models & views
├── core/                      # Root project configuration, settings.py, wsgi.py, urls.py
├── menu/                      # Menu items, Categories, Reviews, QR code generation
├── orders/                    # Orders, DiningSession, Payments, WaiterAlerts, Staff views
│   ├── models.py              # DiningSession, Order, OrderItem, Payment, RestaurantTable
│   ├── staff_views.py         # KDS, Waiter, Manager dashboards, Password change
│   ├── tests.py               # 22 comprehensive automated test cases
│   └── views.py               # Customer checkout, Live tracking, Cart, Invoices
├── gcp/                       # Turnkey GCP Cloud Deployment & Maintenance Scripts
│   ├── deploy_first_time.sh   # Automated first-time deployment from GitHub
│   ├── update_app.sh          # 1-command app updater from GitHub (zero-downtime reload)
│   ├── deploy.sh              # Unified deployment wrapper
│   ├── food_menu.service      # Systemd service unit for Gunicorn daemon
│   ├── nginx_food_menu.conf   # Production Nginx reverse proxy configuration
│   └── setup_postgres.sh      # Automated PostgreSQL database & user provisioner
├── templates/                 # Modular Jinja-compatible HTML templates
│   ├── base.html              # Base shell with live table modal, staff password modal
│   ├── menu/                  # Home landing page, Digital menu, Item details, Reviews
│   ├── orders/                # Cart, Live session tracking, Invoices, My Orders
│   └── staff/                 # Kitchen KDS, Waiter Floor, Manager Dashboard & Detail
├── static/ & staticfiles/     # Static CSS, JavaScript, and branding assets
├── data_seed.json             # Demo restaurant catalog fixture (Viva evaluation ready)
├── requirements.txt           # Python package dependencies
├── .env.example               # Environment variables template
└── manage.py                  # Django management CLI
```

---

## 🚀 Local Development Setup

### 1. Prerequisites
- Python 3.11+ (Python 3.12, 3.13, 3.14 fully supported)
- Git

### 2. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/aryan-tid/food-menu.git
cd food-menu

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Environment Configuration
```bash
# Copy example environment configuration
cp .env.example .env
```
*(The default `.env.example` settings work out of the box with SQLite for local testing).*

### 4. Database Setup & Data Seeding
```bash
# Run database migrations
python manage.py migrate

# Seed rich restaurant demo data (Staff, 47 dishes, Reviews, Tables, Live & Past Orders, Payments)
python manage.py seed_demo_data --clear
```

### 5. Run Automated Tests
```bash
python manage.py test
# Ran 22 tests in ~24s ... OK
```

### 6. Start Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```
Open **`http://127.0.0.1:8000/`** in your browser.

---

## 🔑 Demo Login Credentials (Staff & Customers)

| Role | Username | Password | Dashboard / Access URL |
|---|---|---|---|
| **Superuser / Master Admin** | `admin` | `admin123` | `/admin/` |
| **Restaurant Manager** | `manager` | `manager123` | `/staff/manager/` |
| **Floor Waiter (Captain)** | `waiter` | `waiter123` | `/staff/waiter/` |
| **Floor Waiter 2 (Steward)** | `waiter2` | `waiter123` | `/staff/waiter/` |
| **Floor Waiter 3 (Steward)** | `waiter3` | `waiter123` | `/staff/waiter/` |
| **Kitchen Chef (Head Chef)** | `kitchen` | `kitchen123` | `/staff/kitchen/` |
| **Kitchen Chef 2 (Sous Chef)** | `chef2` | `kitchen123` | `/staff/kitchen/` |
| **Customer (Table T-03 Active)** | `siddhivinayak` | `customer123` | `/orders/session/live/` |
| **Customer 2 (Table T-05 Ready)** | `aditi_s` | `customer123` | `/orders/session/live/` |
| **Customer 3 (Table T-02 Pending)** | `rohit_v` | `customer123` | `/orders/session/live/` |

---

## ☁️ Google Cloud Platform (GCP) Deployment

The project includes purpose-built deployment scripts designed for **GCP Compute Engine (Ubuntu / Debian)** VMs. Code is pulled directly from GitHub, and `.env` is managed securely on the server.

### 📦 A. First-Time Server Deployment

1. **Create a GCP Compute Engine VM**:
   - Machine Type: `e2-micro` (Free Tier eligible) or `e2-small`.
   - OS: **Ubuntu 22.04 LTS** or **Ubuntu 24.04 LTS**.
   - Firewall: Check **Allow HTTP traffic** and **Allow HTTPS traffic**.

2. **SSH into the VM** and download the first-time setup script:
   ```bash
   # Clone the repository
   sudo git clone https://github.com/aryan-tid/food-menu.git /var/www/food-menu
   cd /var/www/food-menu

   # Run first-time deploy script (Interactive or with domain)
   sudo bash gcp/deploy_first_time.sh
   # Or with custom domain: sudo bash gcp/deploy_first_time.sh yourdomain.com admin@yourdomain.com
   ```

3. **What `deploy_first_time.sh` Automates**:
   - Configures a 2GB Swapfile (prevents Out-Of-Memory crashes on 1GB VPS).
   - Installs PostgreSQL, Nginx, Python 3, Gunicorn, and Certbot.
   - Creates PostgreSQL database `food_menu_db` and user `food_user`.
   - Clones and links project at `/var/www/food-menu`.
   - Runs migrations, collects static files, and seeds menu fixtures.
   - Configures systemd service `/etc/systemd/system/food_menu.service`.
   - Sets up Nginx reverse proxy with static/media file caching.
   - Configures Let's Encrypt SSL (HTTPS) when domain is provided.

4. **Add / Edit Your Production `.env`**:
   The deployment script preserves your `.env` file. You can adjust production variables anytime:
   ```bash
   sudo nano /var/www/food-menu/.env
   sudo systemctl restart food_menu
   ```

---

### 🔄 B. Updating Existing Production App from GitHub

Whenever new commits are pushed to `https://github.com/aryan-tid/food-menu.git`, update your live GCP VM with a single command:

```bash
sudo bash /var/www/food-menu/gcp/update_app.sh
```

**What `update_app.sh` Executes**:
1. Pulls the latest code: `git pull origin main`.
2. Preserves your production `.env` and uploaded `/media/` files.
3. Updates Python dependencies: `pip install -r requirements.txt`.
4. Runs new migrations: `python manage.py migrate --noinput`.
5. Compiles static assets: `python manage.py collectstatic --noinput`.
6. Fixes `www-data` ownership permissions.
7. Restarts Gunicorn daemon: `sudo systemctl restart food_menu`.
8. Reloads Nginx and reports live service health.

---

### 🌱 C. Resetting & Seeding Demo Data on Production

To wipe old test database records and populate the complete realistic demo dataset (Staff accounts, Waiters, Chefs, Customers, 47 Menu dishes, Reviews, Historical & Live Orders, Combined Payments, and Table Locks):

```bash
sudo bash /var/www/food-menu/gcp/seed_database.sh
```

Or via the Django management command directly:
```bash
cd /var/www/food-menu
./venv/bin/python manage.py seed_demo_data --clear
```

---

### 🔍 Production Troubleshooting Commands

```bash
# Check Gunicorn service status
sudo systemctl status food_menu

# View live application logs
sudo journalctl -u food_menu -f

# Check Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Reload Nginx
sudo nginx -t && sudo systemctl reload nginx
```

---

## 🧪 Automated Testing

All features are covered by automated unit and integration tests:

```bash
./venv/bin/python manage.py test
```

### Verified Test Suites:
- `RealDiningFlowTests`: Complete customer ordering, QR routing, and KDS progression.
- `WaiterFlowTests`: Floor alerts resolution, table concurrency locks, cash settlement.
- `ManagerCRUDAndRevenueTests`: Financial reporting, KPI calculations, staff and menu CRUD.
- `DynamicTableCombinedPaymentAndStaffSecurityTests`: Real-time table lock API, 0-order session exclusion, combined multi-round payment receipts, and self-service PBKDF2 password change.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Developed for academic presentation and real-world restaurant deployment.
