import os
import glob
import django
from django.core.management import call_command

# Configurar Django para que funcione el script
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings') # Asegúrate que 'core' sea el nombre de tu carpeta principal
django.setup()

print("--- INICIANDO LIMPIEZA TOTAL ---")

# 1. Borrar base de datos antigua
if os.path.exists("db.sqlite3"):
    try:
        os.remove("db.sqlite3")
        print("✅ Base de datos eliminada.")
    except PermissionError:
        print("❌ ERROR: Cierra el servidor o cualquier shell abierto para poder borrar la base de datos.")
        exit()
else:
    print("ℹ️ No existía base de datos previa.")

# 2. Borrar archivos de migración viejos (Respetando __init__.py)
# Ajusta la ruta 'expedientes' si tu app se llama diferente
migration_files = glob.glob("expedientes/migrations/0*.py")
for file_path in migration_files:
    os.remove(file_path)
    print(f"🗑️ Migración borrada: {file_path}")

print("\n--- RECONSTRUYENDO SISTEMA ---")

# 3. Crear nuevas migraciones
call_command("makemigrations")
print("✅ Migraciones creadas.")

# 4. Crear nueva base de datos
call_command("migrate")
print("✅ Base de datos generada.")

# 5. Crear Superusuario Automático
from django.contrib.auth import get_user_model
User = get_user_model()

# Cambia estos datos por los tuyos
USERNAME = 'admin'
EMAIL = 'admin@example.com'
PASSWORD = 'admin' # Contraseña sencilla para desarrollo

if not User.objects.filter(username=USERNAME).exists():
    User.objects.create_superuser(USERNAME, EMAIL, PASSWORD)
    print(f"✅ Superusuario creado: {USERNAME} / {PASSWORD}")

print("\n🎉 ¡SISTEMA RESTAURADO CON ÉXITO!")