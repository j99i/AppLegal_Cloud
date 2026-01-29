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
# Si la variable no existe en el entorno, asume True (modo desarrollo).
DEBUG = env.bool('DEBUG', default=True)

# Hosts permitidos (El '*' es útil para Railway/Render al inicio)
ALLOWED_HOSTS = ['*']

# Si usas Railway, es bueno agregar esto para evitar errores de CSRF en formularios
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
    'django.contrib.staticfiles',
    
    # Librerías de Terceros
    'whitenoise.runserver_nostatic', # Ayuda en desarrollo local
    
    # Mis Aplicaciones
    'expedientes',
]


# ==========================================
# 3. MIDDLEWARE (Intermediarios)
# ==========================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware", # <--- VITAL PARA LA NUBE
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
                # Tu procesador de notificaciones
                'expedientes.context_processors.notificaciones_globales',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# ==========================================
# 5. BASE DE DATOS (Configuración Híbrida)
# ==========================================
# Por defecto usa SQLite (Local)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Si existe DATABASE_URL (Railway/Nube), sobrescribe la configuración para usar PostgreSQL
db_from_env = dj_database_url.config(conn_max_age=600)
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
# 8. ARCHIVOS ESTÁTICOS Y MEDIA (Whitenoise)
# ==========================================
STATIC_URL = 'static/'

# Dónde buscar estáticos en desarrollo
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Dónde recolectar estáticos para producción (Railway usará esto)
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Motor de almacenamiento para producción (Comprime y optimiza)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Archivos subidos por el usuario (Media)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# core/settings.py

# ==========================================
# 9. SISTEMA DE CORREO (Configuración SSL Final)
# ==========================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'

# VOLVEMOS A PUERTO 465 (SSL DIRECTO)
# Al arreglar el bug del PDF en views.py, este puerto ya no se bloqueará.
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False
EMAIL_TIMEOUT = 20  # Tiempo de espera prudente

# Variables de entorno
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')

if EMAIL_HOST_USER:
    DEFAULT_FROM_EMAIL = f'AppLegal <{EMAIL_HOST_USER}>'
else:
    DEFAULT_FROM_EMAIL = 'AppLegal <noreply@applegal.com>'