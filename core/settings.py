import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# SECRET_KEY: obligatoria vía .env. Solo en desarrollo (DEBUG=True) se permite un
# fallback local; en producción, si falta, el servidor NO arranca (mejor que arrancar inseguro).
SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-solo-para-desarrollo-local'
    else:
        raise RuntimeError("SECRET_KEY no está definida en el entorno (.env). Requerida en producción.")

# URL pública del backend (túnel cloudflared/ngrok) para callbacks de MercadoPago.
# Vacío en local puro; se completa vía .env cuando levantamos el túnel.
BACKEND_PUBLIC_URL = os.environ.get('BACKEND_PUBLIC_URL', '').rstrip('/')

# URL del frontend React (para redirigir tras el pago).
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173').rstrip('/')

ALLOWED_HOSTS = ['localhost', '127.0.0.1']
_extra_hosts = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS += [h.strip() for h in _extra_hosts.split(',') if h.strip()]

CSRF_TRUSTED_ORIGINS = []
if BACKEND_PUBLIC_URL:
    from urllib.parse import urlparse
    _public_host = urlparse(BACKEND_PUBLIC_URL).hostname
    if _public_host and _public_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_public_host)
    CSRF_TRUSTED_ORIGINS.append(BACKEND_PUBLIC_URL)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    
    # Local apps
    'catalog',
    'payments',
    'shipments',
    'invoicing',
    'lms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# --- CORS: solo orígenes explícitos (nunca abierto a todos) ---
# El frontend (FRONTEND_URL) siempre está permitido; en desarrollo se suman los localhost típicos.
CORS_ALLOWED_ORIGINS = [FRONTEND_URL]
if DEBUG:
    CORS_ALLOWED_ORIGINS += [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ]
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(CORS_ALLOWED_ORIGINS))  # sin duplicados

# --- Endurecimiento de producción (activo SOLO con DEBUG=False) ---
# En local con DEBUG=True nada de esto aplica: se sigue trabajando igual que siempre.
if not DEBUG:
    SECURE_SSL_REDIRECT = True                       # todo por HTTPS
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # detrás de un proxy (nginx/hosting)
    SESSION_COOKIE_SECURE = True                     # cookies solo por HTTPS
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30          # HSTS 30 días (subir a 1 año cuando esté estable)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
    SECURE_REFERRER_POLICY = 'same-origin'
    SESSION_COOKIE_HTTPONLY = True
    # El frontend en producción debe venir por HTTPS
    if FRONTEND_URL.startswith('http://'):
        import warnings
        warnings.warn('FRONTEND_URL usa http:// en producción; debería ser https://')

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# En producción se define DB_NAME (Postgres). En localhost, sin esa variable,
# se usa SQLite automáticamente (no rompe el desarrollo local).
if os.environ.get('DB_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ['DB_NAME'],
            'USER': os.environ.get('DB_USER', ''),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
# Destino de collectstatic en producción (nginx sirve esta carpeta).
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Envíos / Shipit ---
SHIPIT_API_BASE = os.environ.get('SHIPIT_API_BASE', 'https://api.shipit.cl')
# Paquete por defecto cuando el producto no trae dimensiones/peso (igual que el plugin WooCommerce).
DEFAULT_PACKAGE = {'width_cm': 10, 'height_cm': 10, 'length_cm': 10, 'weight_kg': 1}

# --- LMS: archivos protegidos (PDFs de cursos) ---
# Carpeta FUERA de static/media públicos: los archivos solo se sirven vía endpoint
# autenticado que verifica la membresía.
PROTECTED_MEDIA_ROOT = BASE_DIR / 'protected_media'
PROTECTED_MEDIA_ROOT.mkdir(exist_ok=True)

# --- Autenticación (JWT para el frontend React) + Rate limiting ---
from datetime import timedelta
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Rate limiting: protege contra fuerza bruta y abuso de la API (por IP para anónimos).
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/min',          # navegación general sin sesión
        'user': '240/min',          # usuarios logueados
        'login': '10/min',          # anti fuerza bruta de contraseñas
        'password': '10/min',       # set/change password
        'reset': '5/min',           # solicitudes de recuperación (anti spam de correos)
        'payment': '10/min',        # creación de pagos
        'quote': '30/min',          # cotizaciones de envío
    },
}

# En producción la API responde solo JSON (sin la interfaz navegable de DRF, que expone
# formularios y estructura interna). En desarrollo la interfaz navegable sigue disponible.
if not DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = (
        'rest_framework.renderers.JSONRenderer',
    )

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    # Cada refresh entrega un token nuevo y el anterior queda en lista negra:
    # un refresh token robado deja de servir apenas se usa.
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# --- Emails ---
# Desarrollo: los correos se imprimen en la consola del runserver (no se envía nada real).
# Producción: definir EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend y las
# credenciales SMTP de la clienta en el .env.
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'IngenioBlocks <no-reply@ingenioblocks.cl>')
