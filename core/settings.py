import os
from pathlib import Path
import environ
import dj_database_url

# ==========================================
# 1. CONFIGURACIÓN DEL ENTORNO
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Lee el archivo .env si existe (para desarrollo local)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SEGURIDAD CRÍTICA
# En producción, usa la variable de entorno. En local, usa la clave por defecto.
SECRET_KEY = env('SECRET_KEY', default='django-insecure-tu-clave-secreta-local-super-segura')

# DEBUG debe ser False en producción. 
DEBUG = env.bool('DEBUG', default=True)

# HOSTS PERMITIDOS (Dinámico y Seguro)
if not DEBUG:
    ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['.railway.app'])
    CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=['https://*.railway.app'])
else:
    ALLOWED_HOSTS = ['*']
    CSRF_TRUSTED_ORIGINS = ['https://*.railway.app', 'https://*.up.railway.app']


# ==========================================
# 2. APLICACIONES INSTALADAS
# ==========================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    
    # --- CLOUDINARY (Importante: cloudinary_storage antes de staticfiles) ---
    'cloudinary_storage',
    'django.contrib.staticfiles',
    'cloudinary',
    # -----------------------------------------------------------------------

    # Librerías de Terceros
    'whitenoise.runserver_nostatic', 
    'anymail',  # Para Resend
    
    # Mis Aplicaciones
    'expedientes',
]


# ==========================================
# 3. MIDDLEWARE (Intermediarios)
# ==========================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware", 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'


# ==========================================
# 4. TEMPLATES (Plantillas HTML)
# ==========================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'expedientes.context_processors.notificaciones_globales',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# ==========================================
# 5. BASE DE DATOS (Configuración Híbrida)
# ==========================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Si existe DATABASE_URL (Railway/Nube), sobrescribe la configuración para usar PostgreSQL
if 'DATABASE_URL' in os.environ:
    db_from_env = dj_database_url.config(conn_max_age=600, ssl_require=True)
    DATABASES['default'].update(db_from_env)


# ==========================================
# 6. AUTENTICACIÓN Y PASSWORD
# ==========================================
AUTH_USER_MODEL = 'expedientes.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Redirecciones
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'


# ==========================================
# 7. INTERNACIONALIZACIÓN
# ==========================================
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True


# ==========================================
# 8. ARCHIVOS ESTÁTICOS Y MEDIA (Whitenoise + Cloudinary)
# ==========================================
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# --- CONFIGURACIÓN DE MEDIA (CLOUDINARY) ---
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': env('CLOUDINARY_CLOUD_NAME', default=''),
    'API_KEY':    env('CLOUDINARY_API_KEY', default=''),
    'API_SECRET': env('CLOUDINARY_API_SECRET', default=''),
}

MEDIA_URL = '/media/'

# Lógica condicional Correcta: Solo usar Cloudinary si NO es Debug y hay credenciales
if not DEBUG and CLOUDINARY_STORAGE['CLOUD_NAME']:
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
else:
    # Configuración Local
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# ==========================================
# 9. SISTEMA DE CORREO (Vía API - RESEND)
# ==========================================
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"

ANYMAIL = {
    "RESEND_API_KEY": env('RESEND_API_KEY', default=''),
}

DEFAULT_FROM_EMAIL = "GESTIONES CORPAD <onboarding@resend.dev>" 
SERVER_EMAIL = "onboarding@resend.dev" 

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ==========================================
# 10. SEGURIDAD PARA PRODUCCIÓN (BLINDAJE)
# ==========================================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'


# ==========================================
# 11. FACTURAMA
# ==========================================
FACTURAMA_USER = env('FACTURAMA_USER', default='')
FACTURAMA_PASS = env('FACTURAMA_PASS', default='')
FACTURAMA_SANDBOX = True