"""
Django settings for core project.
Configured for Local Development and Production Hosting on Google Cloud Platform (GCP VM).
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file (if present)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    env_file = BASE_DIR / '.env'
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"\''))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-&qd0c#6#_=l+r4an(eb5)l*phq&&v4m01*yktikdyz!v#wa(4d'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

# Hostnames allowed to connect (includes wildcard for ngrok tunnels in development)
env_hosts = os.environ.get('ALLOWED_HOSTS', '*')
if env_hosts == '*':
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [h.strip() for h in env_hosts.split(',') if h.strip()]
    for default_h in ['127.0.0.1', 'localhost', 'testserver', '.ngrok-free.app', '.ngrok.io', '.ngrok.app']:
        if default_h not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(default_h)

# CSRF Trusted Origins for local dev, ngrok tunnels, and GCP deployment
default_trusted_origins = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://*.ngrok-free.app',
    'https://*.ngrok.io',
    'https://*.ngrok.app',
]
CSRF_TRUSTED = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = list(default_trusted_origins)
if CSRF_TRUSTED:
    for origin in CSRF_TRUSTED.split(','):
        clean_origin = origin.strip().strip('"\'')
        if clean_origin and clean_origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(clean_origin)

# Cross-Origin Opener Policy: Allow Google OAuth popup communication with window.opener
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# Firebase Authentication Configuration for Google Sign-In
FIREBASE_CONFIG = {
    'apiKey': os.environ.get('FIREBASE_API_KEY', ''),
    'authDomain': os.environ.get('FIREBASE_AUTH_DOMAIN', ''),
    'projectId': os.environ.get('FIREBASE_PROJECT_ID', ''),
    'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', ''),
    'messagingSenderId': os.environ.get('FIREBASE_MESSAGING_SENDER_ID', ''),
    'appId': os.environ.get('FIREBASE_APP_ID', ''),
}
FIREBASE_SERVICE_ACCOUNT_KEY = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY', '')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    # Project Apps
    'accounts.apps.AccountsConfig',
    'menu.apps.MenuConfig',
    'orders.apps.OrdersConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'orders.context_processors.restaurant_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database configuration
# Supports:
# 1. DATABASE_URL string (e.g. postgres://user:password@host:5432/dbname)
# 2. Individual DB environment variables (DB_ENGINE=postgresql, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
# 3. Google Cloud SQL UNIX socket (when DB_HOST starts with /cloudsql/)
# 4. Defaults to SQLite for local development
database_url = os.environ.get('DATABASE_URL')
db_engine = os.environ.get('DB_ENGINE', '').lower()

if database_url:
    import urllib.parse
    url = urllib.parse.urlparse(database_url)
    db_port = str(url.port or '') if url.port else ''
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql' if 'postgres' in url.scheme else 'django.db.backends.sqlite3',
            'NAME': url.path[1:],
            'USER': url.username or '',
            'PASSWORD': url.password or '',
            'HOST': url.hostname or '',
            'PORT': db_port,
        }
    }
elif db_engine == 'postgresql':
    db_host = os.environ.get('DB_HOST', 'localhost')
    # If using Google Cloud SQL UNIX socket (/cloudsql/PROJECT:REGION:INSTANCE), PORT must be empty
    db_port = '' if db_host.startswith('/') else os.environ.get('DB_PORT', '5432')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'food_menu_db'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
            'HOST': db_host,
            'PORT': db_port,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = 'accounts:google_login'
LOGIN_REDIRECT_URL = 'menu:menu_list'
LOGOUT_REDIRECT_URL = 'menu:menu_list'

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}
